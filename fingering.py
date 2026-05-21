"""Viola fingering algorithm using dynamic programming."""

# Viola open string MIDI notes (C3, G3, D4, A4)
STRINGS = [('C', 48), ('G', 55), ('D', 62), ('A', 69)]
STRING_ORDER = {s: i for i, (s, _) in enumerate(STRINGS)}

# Semitone offset of 1st finger from open string, per position
POSITIONS = [
    ('½',   1),
    ('1st', 2),
    ('2nd', 4),
    ('3rd', 5),
    ('4th', 7),
    ('5th', 9),
    ('6th', 11),
    ('7th', 12),
]

# Semitone offset from finger-1 note → (finger, label)
# Multiple entries allow chromatic notes in a given hand frame
FINGER_MAP = [
    (-1, 1, '1 (low)'),
    ( 0, 1, '1'),
    ( 1, 2, '2 (low)'),
    ( 2, 2, '2'),
    ( 3, 3, '3'),
    ( 4, 3, '3 (high)'),
    ( 5, 4, '4'),
    ( 6, 4, '4 (high)'),
]


def get_options(midi):  # int -> list[dict]
    """Return all viable fingering options for a MIDI pitch."""
    options = []

    for str_name, open_midi in STRINGS:
        diff = midi - open_midi
        if diff < 0:
            continue

        # Open string
        if diff == 0:
            options.append({
                'string': str_name,
                'finger': 0,
                'finger_label': '0 (open)',
                'position': 'open',
                'pos_idx': 0,
                'str_idx': STRING_ORDER[str_name],
            })
            continue

        # Fingered notes — try every position
        for pos_name, f1_offset in POSITIONS:
            offset_from_f1 = diff - f1_offset
            for interval, finger, finger_label in FINGER_MAP:
                if offset_from_f1 == interval:
                    options.append({
                        'string': str_name,
                        'finger': finger,
                        'finger_label': finger_label,
                        'position': pos_name,
                        'pos_idx': f1_offset,
                        'str_idx': STRING_ORDER[str_name],
                    })

    return options


def _position_preference(opt: dict) -> float:
    """Static cost reflecting how 'unusual' a position is.
    1st position is canonical (lowest cost); half position is penalised.
    """
    pi = opt['pos_idx']
    if pi == 1:          # half position — uncommon, avoid unless necessary
        return 1.5
    # Distance from 1st position (pos_idx=2), with gentle scaling
    return abs(pi - 2) * 0.25


def _transition_cost(a: dict, b: dict) -> float:
    """Cost of moving from option a to option b."""
    pos_change = abs(a['pos_idx'] - b['pos_idx'])
    str_change = abs(a['str_idx'] - b['str_idx'])

    # Same string, same position = free
    if str_change == 0 and pos_change == 0:
        return 0.0

    # Same string, shift position
    if str_change == 0:
        return float(pos_change)

    # Different string: penalty per string crossed + position shift
    return str_change * 2.0 + pos_change * 0.5


def find_best_fingering(midi_notes):  # list[int] -> list[dict | None]
    """DP: return optimal fingering for each MIDI note in sequence.

    Notes outside the instrument range (empty options) get None in the result.
    """
    if not midi_notes:
        return []

    all_opts = [get_options(m) for m in midi_notes]
    n = len(midi_notes)

    # Separate notes that have no playable options (out-of-range pitches).
    # Run DP only on the valid subsequence, then reconstruct the full result.
    valid_idx = [i for i in range(n) if all_opts[i]]
    if not valid_idx:
        return [None] * n

    v_opts = [all_opts[i] for i in valid_idx]
    nv = len(v_opts)
    INF = float('inf')

    prev = [[None] * len(v_opts[i]) for i in range(nv)]

    # Seed: prefer 1st position and lower strings for first note
    dp_cur = [
        _position_preference(opt) + opt['str_idx'] * 0.05
        for opt in v_opts[0]
    ]

    for i in range(1, nv):
        dp_next = [INF] * len(v_opts[i])
        for j, opt_j in enumerate(v_opts[i]):
            for k, opt_k in enumerate(v_opts[i - 1]):
                cost = dp_cur[k] + _transition_cost(opt_k, opt_j)
                cost += _position_preference(opt_j)
                if cost < dp_next[j]:
                    dp_next[j] = cost
                    prev[i][j] = k
        dp_cur = dp_next

    # Backtrack through valid notes
    best_j = min(range(len(dp_cur)), key=lambda j: dp_cur[j])
    valid_result = [None] * nv
    j = best_j
    for i in range(nv - 1, -1, -1):
        valid_result[i] = v_opts[i][j]
        if i > 0 and prev[i][j] is not None:
            j = prev[i][j]

    # Map back to original indices; out-of-range notes stay None
    result = [None] * n
    for vi, orig_i in enumerate(valid_idx):
        result[orig_i] = valid_result[vi]

    return result
