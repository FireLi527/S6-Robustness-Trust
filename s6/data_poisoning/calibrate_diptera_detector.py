"""Pre-registered recalibration of the grouped classifier detector on Diptera validation data.

The inherited fruit-fly threshold (0.90) ranks poisoned samples well here but recalls few,
so parameters are re-selected with the same development protocol as fruit-fly
grouped_defense_v1, using only the frozen *validation* split:

- development attacks built on validation images with seeds 52026 and 52027: pest evasion
  (20% of validation Tephritidae -> other Diptera), false alarm (same count, reverse), and
  random 5% / 10% flips - 8 attack cases plus the clean validation set;
- candidates: classifier C in {1, 10}; thresholds 0.30-0.975 step 0.025 plus allow-all;
  classifier signal only (the neighbour signal takes hours at this scale and was already
  weighted 0 on fruit fly);
- criterion: maximise mean development F1 over the 8 attack cases subject to clean
  development FPR <= 5%; ties prefer lower FPR, then higher threshold.

The protocol is written before selection and never overwritten. Training candidates and
the test split play no part in selection; training-manifest hidden truth is opened only
after the calibrated decisions are frozen (via `detect_and_score`). Validation labels are
used to build and score development attacks - explicit supervised calibration.
"""
import csv
import json
import random
from pathlib import Path

import numpy as np

from audit_diptera import DATA, RESULTS, ROOT, SOURCE, sha, write_json
from evaluate_diptera_detection import EMBEDDINGS, classifier_signal, detect_and_score, frozen_detector
from fruitfly_group_detector import GroupedInput
from semantic_detector import SemanticInputRecord, extract_embeddings

CALIBRATION = DATA / 'calibration_v2'
OUTPUT = RESULTS / 'detection_v2_calibrated'
DEV_SEEDS = (52026, 52027)
CS = (1.0, 10.0)
THRESHOLDS = [round(float(t), 3) for t in np.arange(0.30, 0.9751, 0.025)] + [1.000001]
MAX_CLEAN_FPR = 0.05
TARGETED_RATE = 0.20


def development_cases(rows):
    """Return {name: (assigned_labels, poisoned_mask)} built only from validation rows."""
    labels = np.array([int(r['label']) for r in rows])
    tephritid = np.flatnonzero(labels == 1).tolist()
    other = np.flatnonzero(labels == 0).tolist()
    count = round(TARGETED_RATE * len(tephritid))
    cases = {'clean': (labels.copy(), np.zeros(len(rows), bool))}
    for seed in DEV_SEEDS:
        selections = {
            'pest_evasion': random.Random(seed).sample(tephritid, count),
            'false_alarm': random.Random(seed).sample(other, count),
            'label_flip_05': random.Random(seed).sample(range(len(rows)), round(0.05 * len(rows))),
            'label_flip_10': random.Random(seed).sample(range(len(rows)), round(0.10 * len(rows))),
        }
        for name, selected in selections.items():
            poisoned = np.zeros(len(rows), bool)
            poisoned[selected] = True
            cases[f'{name}_seed{seed}'] = (np.where(poisoned, 1 - labels, labels), poisoned)
    return cases


def f1(poisoned, flagged):
    tp = np.sum(poisoned & flagged)
    precision = tp / flagged.sum() if flagged.sum() else 0.0
    recall = tp / poisoned.sum() if poisoned.sum() else 0.0
    return float(2 * precision * recall / (precision + recall)) if precision + recall else 0.0


def freeze_protocol(algorithm_sha, validation_sha):
    protocol = {
        'status': 'FROZEN_BEFORE_SELECTION',
        'script_sha256': sha(Path(__file__)),
        'evaluation_sha256': sha(Path(__file__).with_name('evaluate_diptera_detection.py')),
        'algorithm_sha256': algorithm_sha,
        'split_sha256': sha(DATA / 'split.csv'),
        'validation_rows_sha256': validation_sha,
        'development_seeds': list(DEV_SEEDS),
        'development_cases': ['clean'] + [f'{n}_seed{s}' for s in DEV_SEEDS
                                          for n in ('pest_evasion', 'false_alarm', 'label_flip_05', 'label_flip_10')],
        'classifier_C': list(CS),
        'weights': [0.0, 1.0, 0.0],
        'thresholds': THRESHOLDS,
        'criterion': f'max mean development F1 over 8 attack cases s.t. clean development FPR <= {MAX_CLEAN_FPR}; '
                     'ties: lower FPR, then higher threshold',
        'uses': 'validation split only; training candidates and test split not used for selection',
    }
    path = CALIBRATION / 'protocol.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != protocol:
            raise SystemExit('calibration protocol already frozen with different content; refusing to overwrite')
    else:
        write_json(path, protocol)
    return path


def main():
    _, algorithm_sha = frozen_detector()
    with (DATA / 'split.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = sorted((r for r in csv.DictReader(f) if r['split'] == 'val'), key=lambda r: r['source_relpath'])
    validation_sha = __import__('hashlib').sha256(
        '\n'.join(f"{r['source_relpath']}\t{r['sha256']}\t{r['label']}\t{r['group_id']}" for r in rows).encode()).hexdigest()
    protocol_path = freeze_protocol(algorithm_sha, validation_sha)

    embeddings = extract_embeddings(
        [SemanticInputRecord(r['source_relpath'], r['source_relpath'], r['sha256'], r['label']) for r in rows],
        SOURCE, EMBEDDINGS, ROOT / 'external/clip_cache')
    cases = development_cases(rows)
    trials, best = [], None
    for c in CS:
        risks = {}
        for name, (assigned, _) in cases.items():
            records = [GroupedInput(r['source_relpath'], r['sha256'], str(label), r['group_id'])
                       for r, label in zip(rows, assigned)]
            risks[name], _ = classifier_signal(records, embeddings, c)
        print(f'C={c}: development signals computed', flush=True)
        for threshold in THRESHOLDS:
            clean_fpr = float(np.mean(risks['clean'] >= threshold))
            case_f1 = {n: f1(p, risks[n] >= threshold) for n, (_, p) in cases.items() if n != 'clean'}
            value = float(np.mean(list(case_f1.values())))
            trial = {'C': c, 'weights': [0.0, 1.0, 0.0], 'threshold': threshold, 'development_mean_f1': value,
                     'clean_fpr': clean_fpr, 'case_f1': case_f1}
            trials.append(trial)
            if clean_fpr <= MAX_CLEAN_FPR:
                key = (value, -clean_fpr, threshold)
                if best is None or key > best[0]:
                    best = (key, trial)
    chosen = best[1]
    selection_path = CALIBRATION / 'detector_selection.json'
    write_json(selection_path, {'protocol_sha256': sha(protocol_path), 'chosen': chosen, 'trials': trials})
    print('SELECTED', json.dumps({k: chosen[k] for k in ('C', 'threshold', 'development_mean_f1', 'clean_fpr')}), flush=True)

    detect_and_score(
        {k: chosen[k] for k in ('C', 'weights', 'threshold')}, OUTPUT,
        {'algorithm_sha256': algorithm_sha, 'calibration_protocol_sha256': sha(protocol_path),
         'calibration_selection_sha256': sha(selection_path)},
        'Parameters re-selected on the Diptera validation split under the pre-registered calibration_v2 protocol; '
        'training candidates and test split unused for selection. by_original_class splits recall by poisoning '
        'direction (original 1 = Tephritidae) and clean FPR by true class.')


if __name__ == '__main__':
    main()
