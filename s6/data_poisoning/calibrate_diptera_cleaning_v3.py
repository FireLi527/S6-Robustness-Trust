"""Pre-registered iterative-cleaning recalibration of the grouped classifier detector
(cleaning_v3), addressing calibration_v2's recall collapse as poisoning rate rises.

Round 0 is the plain classifier signal (identical to `classifier_signal`). Each following
round isolates the samples whose *previous* round's risk was >= q from every fold's
reference set (never its held set), refits, and rescores everyone; isolation is taken
fresh from the immediately preceding round each time, not accumulated across rounds. See
`DIPTERA_PROTOCOL_ZH.md`'s "cleaning_v3" section for the design this implements.

Uses only the frozen *validation* split, the same development attacks as calibration_v2
(seeds 52026/52027, 8 cases + clean), and the same criterion (maximise mean development F1
subject to clean development FPR <= 5%; ties: lower FPR, then higher threshold). C is fixed
at 10 (calibration_v2's choice on this same validation split, not re-tuned here); only q in
{0.5, 0.6, 0.7, 0.8}, rounds in {1, 2, 3}, and the calibration_v2 threshold grid are
searched. Training candidates and the test split play no part in selection; training-
manifest hidden truth is opened only after the chosen decisions are frozen (via
`detect_and_score`).
"""
import csv
import json
from functools import partial
from pathlib import Path

import numpy as np

from audit_diptera import DATA, RESULTS, ROOT, SOURCE, sha, write_json
from calibrate_diptera_detector import MAX_CLEAN_FPR, THRESHOLDS, development_cases, f1
from evaluate_diptera_detection import EMBEDDINGS, detect_and_score, frozen_detector, iterative_classifier_signal
from fruitfly_group_detector import GroupedInput
from semantic_detector import SemanticInputRecord, extract_embeddings

CALIBRATION = DATA / 'cleaning_v3'
OUTPUT = RESULTS / 'detection_v3_iterative'
CALIBRATION_V2 = DATA / 'calibration_v2'
QS = (0.5, 0.6, 0.7, 0.8)
ROUNDS = (1, 2, 3)


def fixed_c():
    selection = json.loads((CALIBRATION_V2 / 'detector_selection.json').read_text(encoding='utf-8'))
    c = selection['chosen']['C']
    if c != 10.0:
        raise ValueError(f'expected calibration_v2 C=10 per the pre-registered plan, found {c}')
    return c, sha(CALIBRATION_V2 / 'detector_selection.json')


def freeze_protocol(algorithm_sha, validation_sha, c, calibration_v2_selection_sha):
    protocol = {
        'status': 'FROZEN_BEFORE_SELECTION',
        'script_sha256': sha(Path(__file__)),
        'evaluation_sha256': sha(Path(__file__).with_name('evaluate_diptera_detection.py')),
        'algorithm_sha256': algorithm_sha,
        'split_sha256': sha(DATA / 'split.csv'),
        'validation_rows_sha256': validation_sha,
        'calibration_v2_selection_sha256': calibration_v2_selection_sha,
        'classifier_C': c,
        'weights': [0.0, 1.0, 0.0],
        'q': list(QS),
        'rounds': list(ROUNDS),
        'thresholds': THRESHOLDS,
        'criterion': f'max mean development F1 over 8 attack cases s.t. clean development FPR <= {MAX_CLEAN_FPR}; '
                     'ties: lower FPR, then higher threshold',
        'uses': 'validation split only; training candidates and test split not used for selection; '
                'C fixed from calibration_v2 (same validation split), not re-tuned here',
        'isolation': 'per round, isolate samples with the immediately preceding round\'s risk >= q from every '
                     'fold\'s reference set only; not cumulative across rounds',
    }
    path = CALIBRATION / 'protocol.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != protocol:
            raise SystemExit('cleaning_v3 protocol already frozen with different content; refusing to overwrite')
    else:
        write_json(path, protocol)
    return path


def main():
    _, algorithm_sha = frozen_detector()
    c, calibration_v2_selection_sha = fixed_c()
    with (DATA / 'split.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = sorted((r for r in csv.DictReader(f) if r['split'] == 'val'), key=lambda r: r['source_relpath'])
    validation_sha = __import__('hashlib').sha256(
        '\n'.join(f"{r['source_relpath']}\t{r['sha256']}\t{r['label']}\t{r['group_id']}" for r in rows).encode()).hexdigest()
    protocol_path = freeze_protocol(algorithm_sha, validation_sha, c, calibration_v2_selection_sha)

    embeddings = extract_embeddings(
        [SemanticInputRecord(r['source_relpath'], r['source_relpath'], r['sha256'], r['label']) for r in rows],
        SOURCE, EMBEDDINGS, ROOT / 'external/clip_cache')
    cases = development_cases(rows)

    trials, best = [], None
    for q in QS:
        for rounds in ROUNDS:
            risks = {}
            for name, (assigned, _) in cases.items():
                records = [GroupedInput(r['source_relpath'], r['sha256'], str(label), r['group_id'])
                           for r, label in zip(rows, assigned)]
                risks[name], _ = iterative_classifier_signal(records, embeddings, c, q, rounds)
            print(f'q={q} rounds={rounds}: development signals computed', flush=True)
            for threshold in THRESHOLDS:
                clean_fpr = float(np.mean(risks['clean'] >= threshold))
                case_f1 = {n: f1(p, risks[n] >= threshold) for n, (_, p) in cases.items() if n != 'clean'}
                value = float(np.mean(list(case_f1.values())))
                trial = {'C': c, 'weights': [0.0, 1.0, 0.0], 'q': q, 'rounds': rounds, 'threshold': threshold,
                         'development_mean_f1': value, 'clean_fpr': clean_fpr, 'case_f1': case_f1}
                trials.append(trial)
                if clean_fpr <= MAX_CLEAN_FPR:
                    key = (value, -clean_fpr, threshold)
                    if best is None or key > best[0]:
                        best = (key, trial)
    chosen = best[1]
    selection_path = CALIBRATION / 'detector_selection.json'
    write_json(selection_path, {'protocol_sha256': sha(protocol_path), 'chosen': chosen, 'trials': trials})
    print('SELECTED', json.dumps({k: chosen[k] for k in ('C', 'q', 'rounds', 'threshold', 'development_mean_f1', 'clean_fpr')}), flush=True)

    signal_fn = partial(iterative_classifier_signal, q=chosen['q'], rounds=chosen['rounds'])
    detect_and_score(
        {k: chosen[k] for k in ('C', 'weights', 'threshold')}, OUTPUT,
        {'algorithm_sha256': algorithm_sha, 'cleaning_protocol_sha256': sha(protocol_path),
         'cleaning_selection_sha256': sha(selection_path), 'q': chosen['q'], 'rounds': chosen['rounds']},
        'Pre-registered iterative-cleaning (cleaning_v3) parameters re-selected on the Diptera validation split; '
        'C fixed from calibration_v2, q/rounds/threshold re-selected here. Training candidates and test split '
        'unused for selection. by_original_class splits recall by poisoning direction (original 1 = Tephritidae) '
        'and clean FPR by true class.',
        signal_fn=signal_fn)


if __name__ == '__main__':
    main()
