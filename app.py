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
from music21 import converter, note, chord

from fingering import find_best_fingering

app = Flask(__name__)
CORS(app, origins=[
    'https://shintachibana.github.io',
    'http://127.0.0.1:5001',
    'http://localhost:5001',
])

ALLOWED_EXT = {'.xml', '.mxl', '.musicxml', '.pdf'}

AUDIVERIS_BIN = os.environ.get(
    'AUDIVERIS_BIN',
    os.path.expanduser(
        '~/Desktop/ClaudeCode/Music/audiveris-master/app/build/install/app/bin/Audiveris'
    )
)
JAVA_BIN_DIR = os.environ.get('JAVA_BIN_DIR', '/opt/homebrew/opt/openjdk@25/bin')


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


# ── Fingering injection (direct XML, no music21 re-export) ───────────────────

def _add_fingering_to_note_el(note_el: ET.Element, finger_num: int) -> None:
    """Inject <notations><technical><fingering>N</fingering>...</ into a note element."""
    notations = note_el.find('notations')
    if notations is None:
        notations = ET.SubElement(note_el, 'notations')
    technical = notations.find('technical')
    if technical is None:
        technical = ET.SubElement(notations, 'technical')
    finger_el = ET.SubElement(technical, 'fingering')
    finger_el.text = str(finger_num)


def _inject_fingering_xml(xml_str: str, part_fingerings: list[list]) -> str:
    """
    Inject <fingering> elements into MusicXML.
    part_fingerings[p] is the list of {finger: int, ...}|None for part p,
    in the same order as non-rest notes appear in the XML.
    """
    # Strip XML/DOCTYPE declarations so ElementTree can parse
    header_match = re.match(r'(<\?xml[^?]*\?>)', xml_str)
    header = header_match.group(1) if header_match else '<?xml version="1.0" encoding="UTF-8"?>'
    body = re.sub(r'<\?xml[^?]*\?>', '', xml_str)
    body = re.sub(r'<!DOCTYPE\s.*?(?:\[.*?\])?\s*>', '', body, flags=re.DOTALL)
    body = body.strip()

    root = ET.fromstring(body)

    parts = root.findall('part')
    for p_idx, part_el in enumerate(parts):
        if p_idx >= len(part_fingerings):
            break
        fingerings = part_fingerings[p_idx]
        ni = 0
        for measure_el in part_el.findall('measure'):
            for note_el in measure_el.findall('note'):
                if note_el.find('rest') is not None:
                    continue            # skip rests
                if ni < len(fingerings) and fingerings[ni]:
                    f = fingerings[ni]
                    finger_num = f.get('finger')
                    if finger_num is not None and finger_num != '?':
                        _add_fingering_to_note_el(note_el, int(finger_num))
                ni += 1

    return header + '\n' + ET.tostring(root, encoding='unicode')


# ── Core processing ───────────────────────────────────────────────────────────

def _process(xml_str: str, xml_path_for_music21: str) -> tuple[str, list[dict]]:
    """
    Run fingering DP on the score, inject results into the XML.
    Returns (fingered_xml_string, per_part_note_metadata).
    """
    score = converter.parse(xml_path_for_music21)
    parts = list(score.parts) or [score]
    results = []
    part_fingerings = []   # one list of (finger_dict|None) per part

    for p_idx, part in enumerate(parts):
        part_name = getattr(part, 'partName', None) or f'Part {p_idx + 1}'
        flat = part.flatten()

        raw_notes = []
        for el in flat.notesAndRests:
            m_num = el.measureNumber
            try:
                bv = el.beat
                beat = float(bv) if bv == bv else 1.0
            except Exception:
                beat = 1.0
            dur = float(el.duration.quarterLength)

            if isinstance(el, note.Rest):
                raw_notes.append({'type': 'rest', 'measure': m_num,
                                  'beat': beat, 'duration': dur})
            elif isinstance(el, note.Note):
                tied = el.tie is not None and el.tie.type in ('continue', 'stop')
                raw_notes.append({'type': 'note', 'measure': m_num,
                                  'beat': beat, 'duration': dur,
                                  'pitch': el.nameWithOctave,
                                  'midi': el.pitch.midi, 'tied': tied})
            elif isinstance(el, chord.Chord):
                for cn in el.notes:
                    raw_notes.append({'type': 'note', 'measure': m_num,
                                      'beat': beat, 'duration': dur,
                                      'pitch': cn.nameWithOctave,
                                      'midi': cn.pitch.midi, 'tied': False})

        note_items = [d for d in raw_notes if d['type'] == 'note']
        fingerings = find_best_fingering([d['midi'] for d in note_items])
        part_fingerings.append(fingerings)

        ni = 0
        for item in raw_notes:
            if item['type'] == 'note':
                f = fingerings[ni] if ni < len(fingerings) else None
                if f:
                    item.update({'string': f['string'],
                                 'finger': f['finger_label'],
                                 'position': f['position']})
                else:
                    item.update({'string': '?', 'finger': '?', 'position': '?'})
                ni += 1

        results.append({'part_name': part_name, 'notes': raw_notes})

    fingered_xml = _inject_fingering_xml(xml_str, part_fingerings)
    return fingered_xml, results


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
            xml_path = xml_tmp_path
        else:
            xml_str = _read_xml_from_path(tmp.name)
            xml_path = tmp.name

        fingered_xml, results = _process(xml_str, xml_path)
        return jsonify({'musicxml': fingered_xml, 'results': results})

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
    print('Viola Fingering Advisor running at http://127.0.0.1:5001')
    app.run(debug=True, port=5001)
