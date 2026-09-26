"""Transfer the frozen fruit-fly grouped detector to Diptera/Tephritidae candidates.

Parameters come unchanged from `data/fruitfly_poisoning/grouped_defense_v1/detector_selection.json`
(C=10, weights (0, 1, 0), threshold 0.90) and `fruitfly_group_detector.py` must match its
frozen hash; nothing is tuned on this dataset. Because the neighbour and centroid weights
are zero, only the classifier signal is computed (`classifier_signal`, identical to column
1 of `fruitfly_group_detector.signals`, checked by a unit test); the neighbour loop would
take hours at ~35k images and contribute nothing to the score.

Detector inputs are opaque sample IDs, image hashes, candidate labels, and the frozen
split's opaque group IDs. Decisions are written to disk before any hidden truth is opened.
"""
import csv
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from audit_diptera import DATA, RESULTS, ROOT, SOURCE, sha, write_json
from fruitfly_group_detector import GroupedInput, decisions, fold_indices, group_weights
from manifest_protocol import load_candidate_manifest, load_hidden_ground_truth, validate_candidate_truth_pair
from prepare_diptera_poisoning import PROTOCOL, SCENARIOS
from semantic_detector import SemanticInputRecord, extract_embeddings

FRUITFLY_V1 = ROOT / 'data/fruitfly_poisoning/grouped_defense_v1'
OUTPUT = RESULTS / 'detection'
EMBEDDINGS = DATA / 'embeddings' / 'clip_vit_b32_embeddings.npz'


def _fit_score(features, labels, groups, c, isolated):
    """One cross-validation pass: fit each fold on its reference set minus any isolated
    samples, score the held set. `isolated` is None (round 0) or a bool mask over all
    records."""
    output = np.zeros(len(labels))
    folds = np.full(len(labels), -1)
    for fold, (reference, held) in enumerate(fold_indices(groups)):
        ref = reference if isolated is None else reference[~isolated[reference]]
        model = LogisticRegression(C=c, class_weight='balanced', max_iter=2000, random_state=2026)
        model.fit(features[ref], labels[ref], sample_weight=group_weights(groups[ref]))
        probs = model.predict_proba(features[held])
        class_index = {v: i for i, v in enumerate(model.classes_)}
        output[held] = [1 - probs[k, class_index[labels[i]]] if labels[i] in class_index else 1.0
                        for k, i in enumerate(held)]
        folds[held] = fold
    if np.any(folds < 0):
        raise ValueError('Missing held-out predictions')
    return output, folds


def _prepare(records, embeddings):
    features = np.stack([embeddings[r.sha256] for r in records]).astype(np.float64)
    features /= np.linalg.norm(features, axis=1, keepdims=True)
    labels = np.array([r.assigned_label for r in records])
    groups = np.array([r.group_id for r in records])
    return features, labels, groups


def classifier_signal(records, embeddings, c):
    """Column 1 of fruitfly_group_detector.signals: 1 - OOF probability of the candidate label."""
    features, labels, groups = _prepare(records, embeddings)
    return _fit_score(features, labels, groups, c, None)


def iterative_classifier_signal(records, embeddings, c, q, rounds):
    """cleaning_v3: round 0 is `classifier_signal`; each following round isolates the
    samples whose *previous* round's risk was >= q from every fold's reference set
    (never the held set) before refitting and rescoring everyone. Isolation is not
    cumulative across rounds - it is always taken fresh from the immediately preceding
    round's scores, per the pre-registered protocol."""
    features, labels, groups = _prepare(records, embeddings)
    isolated = None
    signal = folds = None
    for round_index in range(rounds + 1):
        signal, folds = _fit_score(features, labels, groups, c, isolated)
        if round_index < rounds:
            isolated = signal >= q
    return signal, folds


def frozen_detector():
    protocol = json.loads((FRUITFLY_V1 / 'protocol.json').read_text(encoding='utf-8'))
    detector = Path(__file__).with_name('fruitfly_group_detector.py')
    if sha(detector) != protocol['algorithm_sha256']:
        raise ValueError('fruitfly_group_detector.py differs from the frozen grouped_defense_v1 algorithm')
    chosen = json.loads((FRUITFLY_V1 / 'detector_selection.json').read_text(encoding='utf-8'))['chosen']
    if chosen['weights'][0] or chosen['weights'][2]:
        raise ValueError('Classifier-only shortcut requires zero neighbour and centroid weights')
    return chosen, protocol['algorithm_sha256']


def rates(truth_poisoned, flagged):
    tp = int(np.sum(truth_poisoned & flagged))
    fp = int(np.sum(~truth_poisoned & flagged))
    fn = int(np.sum(truth_poisoned & ~flagged))
    tn = int(np.sum(~truth_poisoned & ~flagged))
    return {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'precision': round(tp / (tp + fp), 4) if tp + fp else None,
            'recall': round(tp / (tp + fn), 4) if tp + fn else None,
            'clean_fpr': round(fp / (fp + tn), 4) if fp + tn else None}


def group_ids():
    with (DATA / 'split.csv').open(encoding='utf-8-sig', newline='') as f:
        return {r['sha256']: r['group_id'] for r in csv.DictReader(f)}


def detect_and_score(chosen, output, provenance, note, signal_fn=classifier_signal):
    """Freeze decisions for every frozen training manifest, then (only then) score them.

    `signal_fn(records, embeddings, chosen['C'])` computes the risk signal; the default
    is the plain (round-0) classifier signal. Pass a `functools.partial` of
    `iterative_classifier_signal` bound to `q`/`rounds` to run cleaning_v3 instead."""
    protocol = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    group_of = group_ids()
    manifests = {}
    for name in SCENARIOS:
        path = DATA / 'manifests' / f'{name}.csv'
        if sha(path) != protocol['manifests'][name]['sha256']:
            raise ValueError(f'{name} manifest changed after freezing')
        manifests[name] = load_candidate_manifest(path)
    embeddings = extract_embeddings([SemanticInputRecord(**r) for r in manifests['clean_subset']],
                                    SOURCE, EMBEDDINGS, ROOT / 'external/clip_cache')

    predictions = {}
    for name, rows in manifests.items():
        records = [GroupedInput(r['sample_id'], r['sha256'], r['assigned_label'], group_of[r['sha256']]) for r in rows]
        signal, folds = signal_fn(records, embeddings, chosen['C'])
        matrix = np.column_stack([np.zeros_like(signal), signal, np.zeros_like(signal)])
        predictions[name] = decisions(records, matrix, chosen['weights'], chosen['threshold'])
        for r, fold in zip(records, folds):
            predictions[name][r.sample_id]['held_out_fold'] = int(fold)
        print(name, sum(v['decision'] == 'REVIEW' for v in predictions[name].values()), 'REVIEW', flush=True)
    prediction_path = output / 'candidate_predictions.json'
    write_json(prediction_path, {'protocol_sha256': sha(PROTOCOL), **provenance,
                                 'detector': chosen, 'datasets': predictions})

    # Only after every decision is on disk: open hidden truth and score.
    summary = {}
    for name, rows in manifests.items():
        truth = load_hidden_ground_truth(DATA / 'hidden_ground_truth' / f'{name}.csv')
        validate_candidate_truth_pair(rows, truth)
        truth_by_id = {t['sample_id']: t for t in truth}
        ids = [r['sample_id'] for r in rows]
        poisoned = np.array([truth_by_id[i]['poisoned'] == 'true' for i in ids])
        original = np.array([int(truth_by_id[i]['original_label']) for i in ids])
        flagged = np.array([predictions[name][i]['decision'] == 'REVIEW' for i in ids])
        risk = np.array([predictions[name][i]['risk_score'] for i in ids])
        entry = {'overall': rates(poisoned, flagged),
                 'roc_auc': round(float(roc_auc_score(poisoned, risk)), 4) if 0 < poisoned.sum() < len(ids) else None,
                 'by_original_class': {}}
        for label in (0, 1):
            mask = original == label
            entry['by_original_class'][str(label)] = rates(poisoned[mask], flagged[mask])
        summary[name] = entry
    write_json(output / 'detection_summary.json', {
        'protocol_sha256': sha(PROTOCOL), 'predictions_sha256': sha(prediction_path),
        'detector': chosen, **provenance, 'note': note, 'results': summary,
    })
    print(json.dumps(summary, indent=1))
    return summary


def main():
    chosen, algorithm_sha = frozen_detector()
    detect_and_score(chosen, OUTPUT, {'algorithm_sha256': algorithm_sha},
                     'Frozen fruit-fly grouped_defense_v1 parameters transferred without tuning. '
                     'by_original_class splits recall by poisoning direction (original 1 = Tephritidae) '
                     'and clean FPR by true class.')


if __name__ == '__main__':
    main()
