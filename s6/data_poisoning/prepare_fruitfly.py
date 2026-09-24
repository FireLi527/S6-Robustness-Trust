"""Import classmates' five archives, audit pixels, group splits and freeze label-flip inputs."""
import csv
import hashlib
import io
import json
import os
import random
import re
import stat
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
from PIL import Image
from manifest_protocol import CANDIDATE_FIELDS,HIDDEN_GROUND_TRUTH_FIELDS

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/fruitfly_poisoning'
IMAGES=DATA/'images'
RESULTS=ROOT/'results/fruitfly_poisoning'
CLASSES=('1001Bactrocera_correcta','1002Bactrocera_zonata','1003Bactrocera_dorsalis','1006Bactrocera_tryoni','1018Ceratitis_capitata')
SEED=2026

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

def write_csv(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def safe_name(name):
    p=PurePosixPath(name.replace('\\','/'))
    if p.is_absolute() or '..' in p.parts or len(p.parts)!=1 or ':' in name:
        raise ValueError(f'Unsafe or unexpected ZIP path: {name}')
    if not re.match(r'^\d{15}_.*\.jpg$',name,re.I):
        raise ValueError(f'Unrecognised filename grouping: {name}')
    return p.name

def audit_image(label,name,raw):
    row=dict(label=label,filename=name,filename_group=name[:9],sha256=hashlib.sha256(raw).hexdigest())
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.load();rgb=im.convert('RGB')
            row.update(width=im.width,height=im.height,mode=im.mode,
                       pixel_sha256=hashlib.sha256(f'{im.width}x{im.height}:'.encode()+rgb.tobytes()).hexdigest())
        target=IMAGES/'source'/str(label)/name
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if sha(target)!=row['sha256']:raise ValueError('Existing imported bytes changed')
        else:target.write_bytes(raw)
        row.update(status='valid',error='')
    except (OSError,ValueError) as error:
        row.update(status='invalid',error=str(error))
    return row

def group_split(rows):
    parent={r['filename_group']:r['filename_group'] for r in rows}
    def find(a):
        while parent[a]!=a:
            parent[a]=parent[parent[a]];a=parent[a]
        return a
    bypixel=defaultdict(list)
    for r in rows:bypixel[r['pixel_sha256']].append(r)
    retained=[]
    for items in bypixel.values():
        if len({r['label'] for r in items})>1:
            for r in items:r['status']='conflicting_label'
            continue
        for r in items[1:]:
            parent[find(r['filename_group'])]=find(items[0]['filename_group'])
            r['status']='duplicate_pixels'
        retained.append(items[0])
    for r in retained:r['group']=find(r['filename_group'])
    assignment={}
    for label in range(5):
        groups=sorted({r['group'] for r in retained if r['label']==label})
        if len(groups)<7:raise ValueError('Too few groups for three-way split')
        random.Random(SEED+label).shuffle(groups)
        n=max(1,round(.15*len(groups)))
        for i,g in enumerate(groups):assignment[g]='test' if i<n else ('val' if i<2*n else 'train')
    for r in retained:r['split']=assignment[r['group']]
    return retained

def main():
    if (DATA/'protocol.json').exists():
        raise RuntimeError('Dataset already frozen; use existing protocol rather than overwrite')
    rows=[];archives={}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for label,name in enumerate(CLASSES):
            archive=ROOT/'资料'/f'{name}_Crop.zip'
            archives[archive.name]=sha(archive)
            with ZipFile(archive) as z:
                entries=[e for e in z.infolist() if not e.is_dir()]
                names=[safe_name(e.filename) for e in entries]
                if len(set(names))!=len(names):raise ValueError('Duplicate ZIP members')
                for start in range(0,len(entries),32):
                    tasks=[]
                    for e in entries[start:start+32]:
                        if stat.S_ISLNK(e.external_attr>>16):raise ValueError('ZIP symlink rejected')
                        tasks.append(pool.submit(audit_image,label,safe_name(e.filename),z.read(e)))
                    rows.extend(t.result() for t in tasks)
            print(name,'audited',len(entries),flush=True)
    valid=[r for r in rows if r['status']=='valid']
    retained=group_split(valid)
    for split in ('train','val','test'):
        subset=[r for r in retained if r['split']==split]
        index=[]
        for r in subset:
            target=IMAGES/'classification'/split/str(r['label'])/r['filename']
            target.parent.mkdir(parents=True,exist_ok=True)
            source=IMAGES/'source'/str(r['label'])/r['filename']
            if not target.exists():os.link(source,target)
            if sha(target)!=r['sha256']:raise ValueError('Linked image hash mismatch')
            r['source_relpath']=target.relative_to(IMAGES).as_posix()
            index.append(f"{r['filename']} {r['label']}")
        (IMAGES/f'{split}.txt').write_text('\n'.join(index)+'\n',encoding='utf-8')
    (IMAGES/'classes.txt').write_text('\n'.join(f'{i} {name}' for i,name in enumerate(CLASSES))+'\n',encoding='utf-8')
    train=sorted([r for r in retained if r['split']=='train'],key=lambda r:(r['label'],r['filename']))
    clean=[dict(sample_id=f"fruitfly_{r['label']}_{Path(r['filename']).stem}",source_relpath=r['source_relpath'],sha256=r['sha256'],assigned_label=r['label']) for r in train]
    manifests={}
    for name,rate in (('clean_subset',0),('label_flip_05',.05),('label_flip_10',.1),('targeted_0_to_1',.2)):
        rng=random.Random(SEED)
        eligible=[i for i,r in enumerate(clean) if name!='targeted_0_to_1' or r['assigned_label']==0]
        selected=set(rng.sample(eligible,round(rate*len(eligible))))
        candidate=[];truth=[]
        for i,r in enumerate(clean):
            original=r['assigned_label'];assigned=original
            if i in selected:assigned=1 if name=='targeted_0_to_1' else rng.choice([l for l in range(5) if l!=original])
            candidate.append(dict(r,assigned_label=assigned))
            truth.append(dict(sample_id=r['sample_id'],original_label=original,poisoned=str(i in selected).lower(),poison_type=name if i in selected else 'clean'))
        file=DATA/'manifests'/f'{name}.csv';write_csv(file,candidate,CANDIDATE_FIELDS)
        write_csv(DATA/'hidden_ground_truth'/f'{name}.csv',truth,HIDDEN_GROUND_TRUTH_FIELDS)
        manifests[name]=dict(sha256=sha(file),samples=len(candidate),poisoned=len(selected))
    fields=sorted({k for r in rows for k in r});write_csv(DATA/'image_audit.csv',rows,fields)
    protocol=dict(dataset='Classmate fruit-fly crops',seed=SEED,classes=list(CLASSES),archives=archives,
                  total_archive_images=len(rows),status_counts=dict(Counter(r['status'] for r in rows)),
                  split_counts={s:dict(Counter(str(r['label']) for r in retained if r['split']==s)) for s in ('train','val','test')},
                  group_counts={s:len({r['group'] for r in retained if r['split']==s}) for s in ('train','val','test')},
                  split_policy='70/15/15 by per-class inferred first-9-digit filename groups; duplicate-pixel groups merged before split',
                  grouping_limitation='Filename prefix is inferred, NOT confirmed specimen identity. No official or classmate split supplied; near duplicates may remain.',
                  label_source='Archive names supplied by user, not independently verified species annotations',
                  manifests=manifests,split_hashes={s:sha(IMAGES/f'{s}.txt') for s in ('train','val','test')},
                  audit_sha256=sha(DATA/'image_audit.csv'),preparation_sha256=sha(Path(__file__)))
    write_json(DATA/'protocol.json',protocol);write_json(RESULTS/'data_audit.json',protocol)
    print(json.dumps(protocol,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
