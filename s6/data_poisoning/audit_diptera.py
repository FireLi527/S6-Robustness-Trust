"""Read-only audit of the classmate Diptera/Tephritidae image set (no split, no copying).

Source: external/diptera/Input_dataset/{Diptera,Tephritidae}/*.jpg, two flat folders with
bare numeric filenames. Folder names are the only labels (confirmed by the classmate); no
observation, species, or licence metadata exists. Images are referenced in place and never
copied into data/.

This step only describes the data so a split protocol can be frozen later. It records per-image decode
status, byte and decoded-pixel SHA-256, size, and a 64-bit difference hash (dHash);
lists exact-pixel duplicates and near-duplicate pairs (dHash Hamming distance <= 6, found
exhaustively via 8-band pigeonhole candidates); and summarises how often numeric IDs sit
next to each other (a possible multi-photo-observation signal). Nothing here decides a
grouping or a label.
"""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'external/diptera/Input_dataset'
DATA = ROOT / 'data/diptera_poisoning'
RESULTS = ROOT / 'results/diptera_poisoning'
CLASSES = ('Diptera', 'Tephritidae')  # label 0 = other Diptera, label 1 = Tephritidae
NAME = re.compile(r'^(\d+)( - Copy)?\.jpg$', re.I)
NEAR_DUPLICATE_MAX_DISTANCE = 6
ID_GAPS = (1, 3, 10)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def dhash(rgb):
    grey = np.asarray(rgb.convert('L').resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16)
    bits = (grey[:, 1:] > grey[:, :-1]).flatten()
    return int(''.join('1' if b else '0' for b in bits), 2)


def enumerate_files():
    rows = []
    for label, cls in enumerate(CLASSES):
        folder = SOURCE / cls
        for path in sorted(folder.iterdir()):
            if path.is_symlink() or not path.is_file():
                raise ValueError(f'Unexpected non-regular entry: {path}')
            match = NAME.match(path.name)
            if not match:
                raise ValueError(f'Unrecognised filename: {path}')
            rows.append({
                'source_relpath': f'{cls}/{path.name}',
                'label': label,
                'class_name': cls,
                'numeric_id': int(match.group(1)),
                'is_copy_suffix': bool(match.group(2)),
            })
    return rows


def audit(row):
    path = SOURCE / row['source_relpath']
    row = dict(row, sha256=sha(path))
    try:
        with Image.open(path) as im:
            im.load()
            rgb = im.convert('RGB')
            row.update(width=im.width, height=im.height, mode=im.mode,
                       pixel_sha256=hashlib.sha256(f'{im.width}x{im.height}:'.encode() + rgb.tobytes()).hexdigest(),
                       dhash=f'{dhash(rgb):016x}', status='valid', error='')
    except (OSError, ValueError) as error:
        row.update(width='', height='', mode='', pixel_sha256='', dhash='', status='invalid', error=str(error))
    return row


def near_duplicates(rows):
    valid = [r for r in rows if r['status'] == 'valid']
    hashes = np.array([int(r['dhash'], 16) for r in valid], dtype=np.uint64)
    candidates = set()
    for band in range(8):
        buckets = defaultdict(list)
        for index, value in enumerate(((hashes >> np.uint64(8 * band)) & np.uint64(0xFF)).tolist()):
            buckets[value].append(index)
        for members in buckets.values():
            candidates.update(combinations(members, 2))
    pairs = []
    for a, b in candidates:
        distance = bin(int(hashes[a]) ^ int(hashes[b])).count('1')
        if distance <= NEAR_DUPLICATE_MAX_DISTANCE:
            pairs.append({
                'a': valid[a]['source_relpath'], 'b': valid[b]['source_relpath'],
                'distance': distance, 'cross_class': valid[a]['label'] != valid[b]['label'],
                'same_pixels': valid[a]['pixel_sha256'] == valid[b]['pixel_sha256'],
            })
    return sorted(pairs, key=lambda p: (p['distance'], p['a'], p['b']))


def id_adjacency(rows):
    summary = {}
    for cls in CLASSES:
        ids = sorted({r['numeric_id'] for r in rows if r['class_name'] == cls})
        gaps = np.diff(ids)
        per_gap = {}
        for limit in ID_GAPS:
            runs, current = [], 1
            for gap in gaps:
                if gap <= limit:
                    current += 1
                else:
                    runs.append(current)
                    current = 1
            runs.append(current)
            multi = [n for n in runs if n > 1]
            per_gap[f'gap<={limit}'] = {
                'runs': len(runs), 'multi_image_runs': len(multi),
                'images_in_multi_image_runs': int(sum(multi)), 'largest_run': int(max(runs)),
            }
        summary[cls] = {'unique_ids': len(ids), 'min_id': int(ids[0]), 'max_id': int(ids[-1]), 'runs_by_max_gap': per_gap}
    return summary


def main():
    rows = enumerate_files()
    with ThreadPoolExecutor() as pool:
        rows = list(pool.map(audit, rows))
    rows.sort(key=lambda r: r['source_relpath'])

    by_pixels = defaultdict(list)
    for r in rows:
        if r['status'] == 'valid':
            by_pixels[r['pixel_sha256']].append(r)
    exact_groups = [items for items in by_pixels.values() if len(items) > 1]
    pairs = near_duplicates(rows)
    ids = defaultdict(list)
    for r in rows:
        ids[(r['class_name'], r['numeric_id'])].append(r)

    fields = ['source_relpath', 'label', 'class_name', 'numeric_id', 'is_copy_suffix', 'sha256', 'pixel_sha256',
              'dhash', 'width', 'height', 'mode', 'status', 'error']
    write_csv(DATA / 'image_audit.csv', rows, fields)
    write_csv(DATA / 'near_duplicate_pairs.csv', pairs, ['a', 'b', 'distance', 'cross_class', 'same_pixels'])

    valid = [r for r in rows if r['status'] == 'valid']
    info = SOURCE / 'info.txt'
    summary = {
        'dataset': 'Classmate Diptera vs Tephritidae field photos',
        'status': 'AUDIT_ONLY_NO_SPLIT',
        'source': 'external/diptera/Input_dataset',
        'info_txt_sha256': sha(info) if info.is_file() else None,
        'inventory_sha256': hashlib.sha256(
            '\n'.join(f"{r['source_relpath']}\t{r['sha256']}" for r in rows).encode()).hexdigest(),
        'classes': {str(i): c for i, c in enumerate(CLASSES)},
        'images_per_class': dict(Counter(r['class_name'] for r in rows)),
        'status_counts': dict(Counter(r['status'] for r in rows)),
        'invalid_files': [r['source_relpath'] for r in rows if r['status'] != 'valid'],
        'modes': dict(Counter(r['mode'] for r in valid)),
        'max_side_counts': dict(Counter(str(max(r['width'], r['height'])) for r in valid).most_common(5)),
        'copy_suffix_files': [
            {'file': r['source_relpath'],
             'original_exists': len(ids[(r['class_name'], r['numeric_id'])]) > 1,
             'identical_to_original': any(o['pixel_sha256'] == r['pixel_sha256'] for o in ids[(r['class_name'], r['numeric_id'])] if o is not r)}
            for r in rows if r['is_copy_suffix']
        ],
        'exact_pixel_duplicate_groups': len(exact_groups),
        'exact_pixel_duplicate_images': sum(len(g) for g in exact_groups),
        'exact_pixel_cross_class_groups': sum(len({r['label'] for r in g}) > 1 for g in exact_groups),
        'near_duplicates': {
            'method': f'64-bit dHash, Hamming distance <= {NEAR_DUPLICATE_MAX_DISTANCE}, exhaustive via 8-band pigeonhole',
            'pairs_by_distance': {str(d): sum(p['distance'] == d for p in pairs) for d in range(NEAR_DUPLICATE_MAX_DISTANCE + 1)},
            'cross_class_pairs_by_distance': {str(d): sum(p['distance'] == d and p['cross_class'] for p in pairs) for d in range(NEAR_DUPLICATE_MAX_DISTANCE + 1)},
            'images_in_any_pair': len({p['a'] for p in pairs} | {p['b'] for p in pairs}),
        },
        'numeric_id_adjacency': id_adjacency(rows),
        'metadata_confirmation': (
            'Classmate confirmed (2026-09-25) that the instructor supplied only these two folders: '
            'folder names are the labels; no observation IDs, species, or licence metadata exist. '
            'Future classification is expected at taxonomic ranks (order/family/genus).'
        ),
        'limitations': [
            'Audit only: no split, grouping, or poisoning manifest is frozen here.',
            'dHash near-duplicate pairs are candidates only. Visual review showed that small insects on plain '
            'backgrounds collapse to near-identical dHashes, so low-distance pairs (including cross-class ones) '
            'are mostly unrelated photos; only exact-pixel groups are confirmed duplicates. Use embedding-based '
            'near-duplicate detection before freezing a split.',
            'ID adjacency is a heuristic signal, not evidence of shared observations.',
        ],
    }
    write_json(RESULTS / 'data_audit.json', summary)
    print(json.dumps({k: summary[k] for k in ('images_per_class', 'status_counts', 'exact_pixel_duplicate_groups',
                                              'exact_pixel_cross_class_groups', 'near_duplicates')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
