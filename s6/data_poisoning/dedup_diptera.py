"""Exclude duplicate Diptera/Tephritidae images before any split (source files untouched).

Duplicates are removed from the experiment, never deleted from external/diptera:

1. Exact decoded-pixel groups from `audit_diptera.py`: within one class keep the lowest
   numeric ID; groups spanning both classes are label conflicts and are excluded entirely.
2. Near duplicates by CLIP ViT-B/32 cosine similarity (the audit showed dHash is unusable
   here). Without `--near-threshold` this only extracts embeddings and writes candidate
   pairs (cosine >= CANDIDATE_FLOOR) for visual review. With a reviewed threshold it
   merges pairs at or above it into connected components and applies the same rule:
   keep the lowest ID of a single-class component, drop every image of a mixed one.

Labels are only the folder names; no poisoning truth exists at this stage.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from audit_diptera import DATA, RESULTS, ROOT, SOURCE, sha, write_csv, write_json
from semantic_detector import SemanticInputRecord, embedding_metadata, extract_embeddings

EMBEDDINGS = DATA / 'embeddings' / 'clip_vit_b32_embeddings.npz'
MODEL_CACHE = ROOT / 'external' / 'clip_cache'
CANDIDATE_FLOOR = 0.95


def read_audit():
    with (DATA / 'image_audit.csv').open(encoding='utf-8-sig', newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['status'] == 'valid']
    for r in rows:
        r['label'], r['numeric_id'] = int(r['label']), int(r['numeric_id'])
    return rows


def resolve(groups, reason_single, reason_mixed):
    """Return {relpath: reason} for images to exclude from a list of duplicate groups."""
    excluded = {}
    for group in groups:
        if len({r['label'] for r in group}) > 1:
            excluded.update({r['source_relpath']: reason_mixed for r in group})
        else:
            keep = min(group, key=lambda r: (r['numeric_id'], r['source_relpath']))
            excluded.update({r['source_relpath']: reason_single for r in group if r is not keep})
    return excluded


def cosine_pairs(rows, vectors, floor):
    unit = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    pairs = []
    for start in range(0, len(rows), 2048):
        block = unit[start:start + 2048] @ unit.T
        for i, j in zip(*np.nonzero(block >= floor)):
            a, b = start + int(i), int(j)
            if a < b:
                pairs.append((a, b, float(block[i, j])))
    return pairs


def components(n, pairs):
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, _ in pairs:
        parent[find(a)] = find(b)
    groups = defaultdict(list)
    for index in range(n):
        groups[find(index)].append(index)
    return [g for g in groups.values() if len(g) > 1]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--near-threshold', type=float, help='reviewed CLIP cosine threshold; omit to only list candidates')
    args = parser.parse_args()

    rows = read_audit()
    by_pixels = defaultdict(list)
    for r in rows:
        by_pixels[r['pixel_sha256']].append(r)
    exact = resolve([g for g in by_pixels.values() if len(g) > 1], 'exact_duplicate', 'exact_duplicate_label_conflict')
    kept = [r for r in rows if r['source_relpath'] not in exact]

    records = [SemanticInputRecord(r['source_relpath'], r['source_relpath'], r['sha256'], r['label']) for r in kept]
    embeddings = extract_embeddings(records, SOURCE, EMBEDDINGS, MODEL_CACHE)
    vectors = np.stack([embeddings[r['sha256']] for r in kept]).astype(np.float32)
    pairs = cosine_pairs(kept, vectors, CANDIDATE_FLOOR)
    write_csv(DATA / 'near_duplicate_candidates_clip.csv', [
        {'a': kept[a]['source_relpath'], 'b': kept[b]['source_relpath'], 'cosine': round(c, 5),
         'cross_class': kept[a]['label'] != kept[b]['label'],
         'id_gap': abs(kept[a]['numeric_id'] - kept[b]['numeric_id'])}
        for a, b, c in sorted(pairs, key=lambda p: -p[2])
    ], ['a', 'b', 'cosine', 'cross_class', 'id_gap'])
    bands = [(0.99, 1.01), (0.98, 0.99), (0.97, 0.98), (0.96, 0.97), (0.95, 0.96)]
    candidate_summary = {
        f'{low:.2f}-{min(high, 1):.2f}': {
            'pairs': sum(low <= c < high for _, _, c in pairs),
            'cross_class': sum(low <= c < high and kept[a]['label'] != kept[b]['label'] for a, b, c in pairs),
        }
        for low, high in bands
    }
    print(json.dumps(candidate_summary, indent=2))
    if args.near_threshold is None:
        print('Candidates written; review them and rerun with --near-threshold to freeze exclusions.')
        return

    near_groups = components(len(kept), [p for p in pairs if p[2] >= args.near_threshold])
    near = resolve([[kept[i] for i in g] for g in near_groups], 'near_duplicate', 'near_duplicate_label_conflict')
    excluded = {**exact, **near}
    retained = [r for r in rows if r['source_relpath'] not in excluded]
    write_csv(DATA / 'dedup_exclusions.csv',
              [{'source_relpath': k, 'reason': v} for k, v in sorted(excluded.items())], ['source_relpath', 'reason'])
    write_csv(DATA / 'retained_images.csv',
              [{k: r[k] for k in ('source_relpath', 'label', 'class_name', 'numeric_id', 'sha256')} for r in retained],
              ['source_relpath', 'label', 'class_name', 'numeric_id', 'sha256'])
    write_json(RESULTS / 'dedup_summary.json', {
        'status': 'FROZEN_DEDUP_NO_SPLIT',
        'audit_sha256': sha(DATA / 'image_audit.csv'),
        'embedding_model': embedding_metadata(),
        'near_threshold_cosine': args.near_threshold,
        'rules': [
            'Exact-pixel or near-duplicate component within one class: keep lowest numeric ID.',
            'Component spanning both classes: label conflict, exclude all members.',
            'Source files are never modified or deleted.',
        ],
        'candidate_bands': candidate_summary,
        'exclusions_by_reason': dict(Counter(excluded.values())),
        'retained_per_class': dict(Counter(r['class_name'] for r in retained)),
        'retained_sha256': sha(DATA / 'retained_images.csv'),
    })
    print(json.dumps({'excluded': dict(Counter(excluded.values())),
                      'retained': dict(Counter(r['class_name'] for r in retained))}, indent=2))


if __name__ == '__main__':
    main()
