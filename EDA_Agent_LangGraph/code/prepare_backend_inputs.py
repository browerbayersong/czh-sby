"""Use the already verified DC outputs as byte-identical inputs to a new ICC run."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent / 'designs/counter_backend'
saved = ROOT / 'session_queue/result_038'
record = json.loads((saved / 'result.json').read_text(encoding='utf-8'))
expected = {item['path']: item.get('sha256') for item in record['files']}
destination = ROOT / 'inputs/dc'
destination.mkdir(parents=True, exist_ok=True)
files = []
for name in ('counter_8bit.mapped.v', 'counter_8bit.sdc', 'counter_8bit.namemap'):
    relative = 'build/dc/' + name
    source = saved / relative
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != expected.get(relative):
        raise ValueError('Saved DC output hash mismatch: ' + name)
    target = destination / ('counter_8bit_namemap.tcl' if name.endswith('.namemap') else name)
    if target.exists() and target.read_bytes() != source.read_bytes():
        raise ValueError('Refusing to overwrite changed backend input: ' + name)
    if not target.exists():
        shutil.copy2(source, target)
    files.append({'path': target.relative_to(ROOT).as_posix(), 'source_path': relative, 'sha256': digest})
provenance = {'source_run': 'upload_002', 'source_result': 'session_queue/result_038',
              'byte_identical': True, 'files': files}
(destination / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
print(json.dumps(provenance))
