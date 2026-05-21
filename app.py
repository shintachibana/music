"""Viola Fingering Advisor — Flask web app."""

import os
import tempfile
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
ALLOWED_EXT = {'.xml', '.mxl', '.musicxml'}


def _parse_score(path: str) -> list[dict]:
    """Parse MusicXML and return per-part note lists."""
    score = converter.parse(path)
    parts = list(score.parts) or [score]
    results = []

    for p_idx, part in enumerate(parts):
        part_name = getattr(part, 'partName', None) or f'Part {p_idx + 1}'
        flat = part.flatten()

        raw_notes = []
        for el in flat.notesAndRests:
            m_num = el.measureNumber
            try:
                beat_val = el.beat
                beat = float(beat_val) if beat_val == beat_val else 1.0  # nan check
            except Exception:
                beat = 1.0
            dur = float(el.duration.quarterLength)

            if isinstance(el, note.Rest):
                raw_notes.append({'type': 'rest', 'measure': m_num,
                                   'beat': beat, 'duration': dur})
            elif isinstance(el, note.Note):
                tied = (el.tie is not None and el.tie.type in ('continue', 'stop'))
                raw_notes.append({'type': 'note', 'measure': m_num,
                                   'beat': beat, 'duration': dur,
                                   'pitch': el.nameWithOctave,
                                   'midi': el.pitch.midi,
                                   'tied': tied})
            elif isinstance(el, chord.Chord):
                for cn in el.notes:
                    raw_notes.append({'type': 'note', 'measure': m_num,
                                       'beat': beat, 'duration': dur,
                                       'pitch': cn.nameWithOctave,
                                       'midi': cn.pitch.midi,
                                       'tied': False})

        # Run DP only on sounding notes
        note_items = [d for d in raw_notes if d['type'] == 'note']
        fingerings = find_best_fingering([d['midi'] for d in note_items])

        ni = 0
        for item in raw_notes:
            if item['type'] == 'note':
                f = fingerings[ni] if ni < len(fingerings) else None
                if f:
                    item.update({
                        'string': f['string'],
                        'finger': f['finger_label'],
                        'position': f['position'],
                    })
                else:
                    item.update({'string': '?', 'finger': '?', 'position': '?'})
                ni += 1

        results.append({'part_name': part_name, 'notes': raw_notes})

    return results


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
                                  'Upload a .xml, .mxl or .musicxml file.'}), 400

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        f.save(tmp.name)
        tmp.close()
        results = _parse_score(tmp.name)
        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


if __name__ == '__main__':
    print('Viola Fingering Advisor running at http://127.0.0.1:5001')
    app.run(debug=True, port=5001)
