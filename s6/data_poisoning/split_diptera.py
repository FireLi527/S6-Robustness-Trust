"""Freeze an approximate observation-grouped train/val/test split for Diptera/Tephritidae.

Input is the frozen de-duplicated list from `dedup_diptera.py`. No observation IDs exist,
so groups are approximated by union-find over two same-class rules:

- numeric IDs within MAX_ID_GAP of each other (likely photos of one observation);
- CLIP cosine in [MERGE_COSINE, near-duplicate threshold) - same specimen, other angle
  (pairs at or above the threshold were already excluded as near duplicates).

Groups are shuffled per class with a fixed seed and assigned to test, then validation,
until each reaches its share of that class's images; the rest go to training. This is
not a verified individual- or observation-disjoint split, and the protocol says so.
"""
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict

from audit_diptera import CLASSES, DATA, RESULTS, sha, write_csv, write_json

SEED = 2026
MAX_ID_GAP = 3
MERGE_COSINE = 0.97
SHARES = (('test', 0.15), ('val', 0.15))


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    dedup = json.loads((RESULTS / 'dedup_summary.json').read_text(encoding='utf-8'))
    if dedup['retained_sha256'] != sha(DATA / 'retained_images.csv'):
        raise ValueError('retained_images.csv does not match the frozen dedup summary')
    near_threshold = dedup['near_threshold_cosine']
    rows = read_csv(DATA / 'retained_images.csv')
    index = {r['source_relpath']: i for i, r in enumerate(rows)}
    parent = list(range(len(rows)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        if rows[a]['label'] != rows[b]['label']:
            raise ValueError(f"Cross-class merge: {rows[a]['source_relpath']} / {rows[b]['source_relpath']}")
        parent[find(a)] = find(b)

    merges = Counter()
    for label in {r['label'] for r in rows}:
        members = sorted((int(r['numeric_id']), i) for i, r in enumerate(rows) if r['label'] == label)
        for (id_a, a), (id_b, b) in zip(members, members[1:]):
            if id_b - id_a <= MAX_ID_GAP:
                union(a, b)
                merges['id_gap'] += 1
    for pair in read_csv(DATA / 'near_duplicate_candidates_clip.csv'):
        cosine = float(pair['cosine'])
        if MERGE_COSINE <= cosine < near_threshold and pair['a'] in index and pair['b'] in index:
            a, b = index[pair['a']], index[pair['b']]
            if rows[a]['label'] == rows[b]['label']:
                union(a, b)
                merges['clip_same_specimen'] += 1
            else:
                merges['clip_cross_class_skipped'] += 1

    groups = defaultdict(list)
    for i in range(len(rows)):
        groups[find(i)].append(i)
    for members in groups.values():
        group_id = hashlib.sha256('\n'.join(sorted(rows[i]['source_relpath'] for i in members)).encode()).hexdigest()[:16]
        for i in members:
            rows[i]['group_id'] = group_id

    rng = random.Random(SEED)
    for label in sorted({r['label'] for r in rows}):
        class_groups = sorted((g for g in groups.values() if rows[g[0]]['label'] == label),
                              key=lambda g: rows[g[0]]['group_id'])
        rng.shuffle(class_groups)
        total = sum(len(g) for g in class_groups)
        targets = [(name, share * total) for name, share in SHARES]
        filled = Counter()
        for group in class_groups:
            split = next((name for name, target in targets if filled[name] < target), 'train')
            filled[split] += len(group)
            for i in group:
                rows[i]['split'] = split

    fields = ['source_relpath', 'label', 'class_name', 'numeric_id', 'sha256', 'group_id', 'split']
    rows.sort(key=lambda r: r['source_relpath'])
    write_csv(DATA / 'split.csv', rows, fields)
    sizes = [len(g) for g in groups.values()]
    summary = {
        'status': 'FROZEN_SPLIT',
        'seed': SEED,
        'dedup_summary_sha256': sha(RESULTS / 'dedup_summary.json'),
        'retained_images_sha256': dedup['retained_sha256'],
        'grouping': {
            'max_id_gap_same_class': MAX_ID_GAP,
            'clip_same_specimen_cosine': [MERGE_COSINE, near_threshold],
            'merge_edges': dict(merges),
            'groups': len(groups),
            'multi_image_groups': sum(s > 1 for s in sizes),
            'largest_group': max(sizes),
        },
        'split_policy': 'per class, shuffled groups fill test then val to 15% of images each; rest train',
        'images': {split: {CLASSES[int(k)]: v for k, v in sorted(Counter(r['label'] for r in rows if r['split'] == split).items())}
                   for split in ('train', 'val', 'test')},
        'groups_per_split': dict(Counter(r['split'] for r in {r['group_id']: r for r in rows}.values())),
        'split_sha256': sha(DATA / 'split.csv'),
        'limitations': [
            'No observation or specimen IDs exist; grouping is approximate (ID adjacency + CLIP similarity).',
            'Distant-ID photos of the same individual below the CLIP merge band may still cross splits.',
            'Folder labels are unverified citizen-science identifications.',
        ],
    }
    write_json(RESULTS / 'split_summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('grouping', 'images', 'groups_per_split')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
