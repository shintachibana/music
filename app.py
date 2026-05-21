"""Viola Fingering Advisor — Flask web app."""

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_compress import Compress

from fingering import find_best_fingering

app = Flask(__name__)
CORS(app, origins=[
    'https://shintachibana.github.io',
    'http://127.0.0.1:5001',
    'http://localhost:5001',
])
Compress(app)

ALLOWED_EXT = {'.xml', '.mxl', '.musicxml', '.pdf'}

AUDIVERIS_BIN = os.environ.get(
    'AUDIVERIS_BIN',
    os.path.expanduser(
        '~/Desktop/ClaudeCode/Music/audiveris-master/app/build/install/app/bin/Audiveris'
    )
)
JAVA_BIN_DIR = os.environ.get('JAVA_BIN_DIR', '/opt/homebrew/opt/openjdk@25/bin')

_STEP_SEMITONE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def _pitch_to_midi(step: str, alter: float, octave: int) -> int:
    return (octave + 1) * 12 + _STEP_SEMITONE[step.upper()] + int(alter)


# ── PDF conversion ────────────────────────────────────────────────────────────

def _pdf_to_musicxml(pdf_path: str) -> str:
    """Convert a PDF score to MusicXML string using Audiveris."""
    if not os.path.isfile(AUDIVERIS_BIN):
        raise RuntimeError(
            'PDF conversion requires Audiveris installed locally. '
            'Please convert your PDF to MusicXML first, then upload the .xml file.'
        )
    out_dir = tempfile.mkdtemp()
    try:
        env = dict(os.environ)
        env['PATH'] = f"{JAVA_BIN_DIR}:{env.get('PATH', '')}"
        proc = subprocess.run(
            [AUDIVERIS_BIN, '-batch', '-transcribe', '-export',
             '-output', out_dir, pdf_path],
            capture_output=True, text=True, timeout=300, env=env,
        )
        for fname in os.listdir(out_dir):
            fpath = os.path.join(out_dir, fname)
            if fname.endswith('.mxl'):
                with zipfile.ZipFile(fpath) as z:
                    xml_names = [n for n in z.namelist()
                                 if n.endswith('.xml') and not n.startswith('META')]
                    if xml_names:
                        return z.read(xml_names[0]).decode('utf-8')
            elif fname.endswith('.xml'):
                with open(fpath, encoding='utf-8') as f:
                    return f.read()
        raise RuntimeError(
            f'Audiveris produced no XML output.\n{(proc.stderr or "")[-600:]}')
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _read_xml_from_path(path: str) -> str:
    """Read MusicXML string from an .xml or .mxl file."""
    _, ext = os.path.splitext(path.lower())
    if ext == '.mxl':
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist()
                     if n.endswith('.xml') and not n.startswith('META')]
            return z.read(names[0]).decode('utf-8')
    with open(path, encoding='utf-8') as f:
        return f.read()


# ── Fingering injection ───────────────────────────────────────────────────────

def _add_fingering_to_note_el(note_el: ET.Element, finger_num: int) -> None:
    """Inject <notations><technical><fingering>N</fingering> into a note element."""
    notations = note_el.find('notations')
    if notations is None:
        notations = ET.SubElement(note_el, 'notations')
    technical = notations.find('technical')
    if technical is None:
        technical = ET.SubElement(notations, 'technical')
    ET.SubElement(technical, 'fingering').text = str(finger_num)


def _process(xml_str: str) -> str:
    """
    Parse MusicXML with ElementTree, run fingering DP, inject results.
    Returns fingered MusicXML string. No music21 dependency.
    """
    header_match = re.match(r'(<\?xml[^?]*\?>)', xml_str)
    header = header_match.group(1) if header_match else '<?xml version="1.0" encoding="UTF-8"?>'
    body = re.sub(r'<\?xml[^?]*\?>', '', xml_str)
    body = re.sub(r'<!DOCTYPE\s.*?(?:\[.*?\])?\s*>', '', body, flags=re.DOTALL).strip()

    root = ET.fromstring(body)

    for part_el in root.findall('part'):
        midi_list = []
        note_els = []
        for measure_el in part_el.findall('measure'):
            for note_el in measure_el.findall('note'):
                if note_el.find('rest') is not None:
                    continue
                pitch_el = note_el.find('pitch')
                if pitch_el is None:
                    continue
                step = pitch_el.findtext('step', 'C')
                alter = float(pitch_el.findtext('alter', '0') or '0')
                octave = int(pitch_el.findtext('octave', '4'))
                try:
                    midi_list.append(_pitch_to_midi(step, alter, octave))
                    note_els.append(note_el)
                except (KeyError, ValueError):
                    pass

        if not midi_list:
            continue

        fingerings = find_best_fingering(midi_list)
        for note_el, f in zip(note_els, fingerings):
            if f:
                finger_num = f.get('finger')
                if finger_num is not None and finger_num != '?':
                    _add_fingering_to_note_el(note_el, int(finger_num))

    return header + '\n' + ET.tostring(root, encoding='unicode')


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided.'}), 400

    f = request.files['file']
    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED_EXT:
        return jsonify({'error': f'Unsupported file type "{ext}". '
                                  'Upload .pdf, .xml, .mxl, or .musicxml.'}), 400

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    xml_tmp_path = None
    try:
        f.save(tmp.name)
        tmp.close()

        if ext == '.pdf':
            xml_str = _pdf_to_musicxml(tmp.name)
            xml_tmp = tempfile.NamedTemporaryFile(
                suffix='.xml', delete=False, mode='w', encoding='utf-8')
            xml_tmp.write(xml_str)
            xml_tmp.close()
            xml_tmp_path = xml_tmp.name
        else:
            xml_str = _read_xml_from_path(tmp.name)

        fingered_xml = _process(xml_str)
        return jsonify({'musicxml': fingered_xml})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        if xml_tmp_path:
            try:
                os.unlink(xml_tmp_path)
            except OSError:
                pass


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug = port == 5001
    print(f'Viola Fingering Advisor running at http://127.0.0.1:{port}')
    app.run(host='0.0.0.0', port=port, debug=debug)
