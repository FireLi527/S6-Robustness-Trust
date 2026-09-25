"""Freeze Diptera/Tephritidae candidate manifests and separate hidden scoring truth.

Candidates are the frozen training split only (validation/test are never poisoned or read
by the detector). Scenarios, all seed 2026 and label-only (images are never modified):

- clean_subset: no change.
- pest_evasion: 20% of training Tephritidae (1) relabelled as other Diptera (0).
- false_alarm: the same number of training Diptera (0) relabelled as Tephritidae (1).
- label_flip_05 / label_flip_10: 5% / 10% of all training images flipped at random.

`sample_id` is an opaque hash. `source_relpath` still names the source folder (the images
are referenced in place), so candidate files are blind to the detector, which never reads
paths, but not to a human reader.
"""
import csv
import hashlib
import json
import random
from collections import Counter

from audit_diptera import DATA, RESULTS, sha, write_csv, write_json
from manifest_protocol import CANDIDATE_FIELDS, HIDDEN_GROUND_TRUTH_FIELDS

SEED = 2026
TARGETED_RATE = 0.20
SCENARIOS = ('clean_subset', 'pest_evasion', 'false_alarm', 'label_flip_05', 'label_flip_10')
PROTOCOL = DATA / 'protocol.json'


def sample_id(relpath):
    return 'diptera_' + hashlib.sha256(relpath.encode()).hexdigest()[:20]


def main():
    split = json.loads((RESULTS / 'split_summary.json').read_text(encoding='utf-8'))
    if split['split_sha256'] != sha(DATA / 'split.csv'):
        raise ValueError('split.csv does not match the frozen split summary')
    with (DATA / 'split.csv').open(encoding='utf-8-sig', newline='') as f:
        train = sorted((r for r in csv.DictReader(f) if r['split'] == 'train'), key=lambda r: r['source_relpath'])
    clean = [dict(sample_id=sample_id(r['source_relpath']), source_relpath=r['source_relpath'], sha256=r['sha256'],
                  assigned_label=int(r['label'])) for r in train]
    tephritid = [i for i, r in enumerate(clean) if r['assigned_label'] == 1]
    other = [i for i, r in enumerate(clean) if r['assigned_label'] == 0]
    targeted_count = round(TARGETED_RATE * len(tephritid))
    selections = {
        'clean_subset': set(),
        'pest_evasion': set(random.Random(SEED).sample(tephritid, targeted_count)),
        'false_alarm': set(random.Random(SEED).sample(other, targeted_count)),
        'label_flip_05': set(random.Random(SEED).sample(range(len(clean)), round(0.05 * len(clean)))),
        'label_flip_10': set(random.Random(SEED).sample(range(len(clean)), round(0.10 * len(clean)))),
    }

    manifests = {}
    for name in SCENARIOS:
        selected = selections[name]
        candidate, truth = [], []
        for i, r in enumerate(clean):
            original = r['assigned_label']
            candidate.append(dict(r, assigned_label=1 - original if i in selected else original))
            truth.append(dict(sample_id=r['sample_id'], original_label=original, poisoned=str(i in selected).lower(),
                              poison_type=name if i in selected else 'clean'))
        path = DATA / 'manifests' / f'{name}.csv'
        write_csv(path, candidate, CANDIDATE_FIELDS)
        write_csv(DATA / 'hidden_ground_truth' / f'{name}.csv', truth, HIDDEN_GROUND_TRUTH_FIELDS)
        manifests[name] = {
            'sha256': sha(path), 'samples': len(candidate), 'poisoned': len(selected),
            'poisoned_by_direction': {f'{o}->{1 - o}': n for o, n in
                                      sorted(Counter(clean[i]['assigned_label'] for i in selected).items())},
            'assigned_label_counts': dict(sorted(Counter(str(c['assigned_label']) for c in candidate).items())),
        }

    protocol = {
        'status': 'FROZEN',
        'seed': SEED,
        'split_sha256': split['split_sha256'],
        'preparation_sha256': sha(__import__('pathlib').Path(__file__)),
        'candidate_split': 'train only; val/test untouched',
        'labels': {'0': 'Diptera (non-Tephritidae)', '1': 'Tephritidae'},
        'targeted_rate_of_source_class': TARGETED_RATE,
        'manifests': manifests,
        'blindness_note': 'sample_id is opaque; source_relpath names the source folder, so manifests are detector-blind, not human-blind.',
    }
    if PROTOCOL.exists():
        frozen = json.loads(PROTOCOL.read_text(encoding='utf-8'))
        if frozen != protocol:
            raise SystemExit('protocol.json already frozen with different content; refusing to overwrite')
    write_json(PROTOCOL, protocol)
    print(json.dumps(manifests, indent=2))


if __name__ == '__main__':
    main()
