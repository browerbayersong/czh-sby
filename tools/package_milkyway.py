"""Package the Windows-copied DRC case with Linux Milkyway filenames restored.

The source folder is never changed. The archive is a backup prepared from copied
bytes, not proof that ICC has reopened that archive successfully.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile


def linux_relative(path: str) -> str:
    parts=path.split('/')
    name=parts[-1]
    if '^%' in name:
        if len(parts)<2 or parts[-2] not in {'CEL','err'} or not re.fullmatch(r'counter_8bit(?:_lvs)?\^%\d+(?:_\d+)?',name):
            raise ValueError('Unrecognized escaped filename: '+path)
        parts[-1]=name.replace('^%',':')
    return '/'.join(parts)


def package(source: Path, output: Path, manifest_path: Path):
    source=source.resolve()
    output=output.resolve()
    manifest_path=manifest_path.resolve()
    if not source.is_dir() or output.is_relative_to(source) or manifest_path.is_relative_to(source):
        raise ValueError('Source must exist; outputs must stay outside it')
    if output.exists() or manifest_path.exists():
        raise FileExistsError('Refusing to overwrite an existing archive or manifest')
    entries=[]
    names=set()
    excluded=[]
    for p in sorted(source.rglob('*')):
        if p.is_symlink():raise ValueError('Symlinks are not supported: '+str(p))
        if not p.is_file():continue
        rel=p.relative_to(source).as_posix()
        if p.name=='.lock':
            excluded.append(rel)
            continue
        name=source.name+'/'+linux_relative(rel)
        if name in names:raise ValueError('Restored path collision: '+name)
        names.add(name)
        data=p.read_bytes()
        entries.append((p,name,data))
    output.parent.mkdir(parents=True,exist_ok=True)
    manifest_path.parent.mkdir(parents=True,exist_ok=True)
    # Fixed timestamps produce a reproducible archive without changing source.
    with output.open('xb') as raw, gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as gz:
        with tarfile.open(fileobj=gz,mode='w',format=tarfile.PAX_FORMAT) as tar:
            for p,name,data in entries:
                info=tarfile.TarInfo(name)
                info.size=len(data)
                info.mode=0o664
                info.mtime=0
                tar.addfile(info,io.BytesIO(data))
    rows=[{'copied_path':p.relative_to(source).as_posix(),'linux_archive_path':name,
           'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
          for p,name,data in entries]
    with tarfile.open(output,'r:gz') as tar:
        for row in rows:
            data=tar.extractfile(row['linux_archive_path']).read()
            assert hashlib.sha256(data).hexdigest()==row['sha256']
    manifest={'format':'windows-copy-to-linux-milkyway-v1','source_directory':source.name,
        'source_modified':False,'restoration':'Recognized CEL/err ^% version separators restored to colon',
        'scope':'Prepared backup only; not reopened in ICC after extraction',
        'excluded_transient_locks':excluded,'files':rows,
        'archive_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
    with manifest_path.open('x',encoding='utf-8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
    print(json.dumps({'archive':str(output),'files':len(rows),
                      'restored_names':sum('^%' in r['copied_path'] for r in rows)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    args=parser.parse_args()
    package(args.source,args.output,args.manifest)
