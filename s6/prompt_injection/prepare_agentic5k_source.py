"""Download pinned public data; inspect validation only, keep test unscored."""
import hashlib
import json
import urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
REVISION = 'e658d94dcafc133e3a4483f9f9aa13507f3848c4'
REPOSITORY = '3nesdeniz/agentic-prompt-injection-5k'


def main():
    dest = ROOT / 'external/agentic-prompt-injection-5k'
    output = ROOT / 'data/bipia/repo_file_v2/agentic5k_source_manifest.json'
    if output.exists():
        raise FileExistsError('Pinned source manifest already exists')
    dest.mkdir(parents=True, exist_ok=True)
    records = {}
    for name in ('README.md', 'data/train.parquet', 'data/validation.parquet', 'data/test.parquet'):
        path = dest / name
        if path.exists():
            raise FileExistsError(f'Download destination exists: {path}')
        url = f'https://huggingface.co/datasets/{REPOSITORY}/resolve/{REVISION}/{name}'
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        records[name] = {'url':url, 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}
    frame = pd.read_parquet(dest / 'data/validation.parquet')
    manifest = {'repository':REPOSITORY,'revision':REVISION,'license':'CC-BY-4.0',
                'author':'Enes Deniz', 'files':records,
                'validation_count':len(frame),'validation_columns':list(frame.columns),
                'validation_labels':{str(k):int(v) for k,v in frame['label'].value_counts().items()},
                'test_status':'DOWNLOADED_BYTES_ONLY_NOT_INSPECTED_OR_SCORED',
                'usage':'Additional validation source for exploratory work; no training on this source yet.',
                'limitations':['Synthetic template-expanded mixed agentic domains, not repository-only.',
                               'Publisher labels, not labels adjudicated by this project.',
                               'Data-card scenario-isolation claim requires local audit before using splits.',
                               'The same-source test is not an independent source from its validation set.']}
    output.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
