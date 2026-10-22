"""从 Linux 虚拟机归档指定轮次的快照清单与源码，用于离线复核 SHA-256。

会把 runs/<label>/snapshot_manifest.json、src/、build/*.log、covReport/dashboard.txt
下载到本地 evidence/<project>/<label>/，并按清单逐个校验哈希。

用法：
    .\\venv\\Scripts\\python.exe -u fetch_evidence.py --labels vcs_004,vcs_006,vcs_007,vcs_015,vcs_017
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import posixpath
import stat
import sys
from pathlib import Path

import paramiko
from dotenv import load_dotenv

if not sys.stdout.isatty():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()


def connect(host: str, user: str, port: int, password: str) -> paramiko.SSHClient:
    known = Path.home() / '.ssh' / 'known_hosts'
    if not known.is_file():
        raise SystemExit(f'缺少 {known}，先手工 ssh 一次接受主机指纹')
    client = paramiko.SSHClient()
    client.load_host_keys(str(known))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(host, port=port, username=user, password=password or None,
                   timeout=20, auth_timeout=25, banner_timeout=25)
    return client


def fetch_tree(sftp, remote_dir: str, local_dir: Path, suffixes=('.log', '.json', '.txt', '.v', '.sv')) -> int:
    """递归下载目录下的普通文件（跳过符号链接）。"""
    count = 0
    for entry in sftp.listdir_attr(remote_dir):
        remote = posixpath.join(remote_dir, entry.filename)
        local = local_dir / entry.filename
        if stat.S_ISDIR(entry.st_mode):
            count += fetch_tree(sftp, remote, local, suffixes)
        elif stat.S_ISREG(entry.st_mode):
            if suffixes and not entry.filename.endswith(suffixes):
                continue
            if entry.st_size > 8_000_000:
                print(f'  跳过超大文件 {remote} ({entry.st_size} bytes)')
                continue
            local.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(remote, str(local))
            count += 1
    return count


def main() -> int:
    p = argparse.ArgumentParser(description='归档 VCS 轮次快照与清单')
    p.add_argument('--host', default='192.168.81.128')
    p.add_argument('--user', default='IC')
    p.add_argument('--port', type=int, default=22)
    p.add_argument('--remote-base', default='/home/IC/Desktop/EDA_Projects')
    p.add_argument('--project', default='counter_v82')
    p.add_argument('--labels', required=True, help='逗号分隔，如 vcs_004,vcs_006')
    p.add_argument('--out', default=r'E:\EDA_Agent_handover_2026-10-22\evidence')
    args = p.parse_args()

    password = getpass.getpass(f'{args.user}@{args.host} 的 SSH 密码（不回显）: ')
    client = connect(args.host, args.user, args.port, password)
    sftp = client.open_sftp()
    out_root = Path(args.out) / args.project
    ok_all = True

    try:
        for label in [x.strip() for x in args.labels.split(',') if x.strip()]:
            run_dir = posixpath.join(args.remote_base, args.project, 'runs', label)
            local = out_root / label
            local.mkdir(parents=True, exist_ok=True)
            print(f'== {label}')
            try:
                sftp.get(posixpath.join(run_dir, 'snapshot_manifest.json'),
                         str(local / 'snapshot_manifest.json'))
            except OSError as exc:
                print(f'  清单缺失: {exc}')
                ok_all = False
                continue

            n_src = fetch_tree(sftp, posixpath.join(run_dir, 'src'), local / 'src', suffixes=())
            for name in ('vcs_compile.log', 'vcs_sim.log'):
                try:
                    sftp.get(posixpath.join(run_dir, 'build', name), str(local / name))
                except OSError:
                    pass
            try:
                sftp.get(posixpath.join(run_dir, 'build', 'covReport', 'dashboard.txt'),
                         str(local / 'coverage_dashboard.txt'))
            except OSError:
                pass

            manifest = json.loads((local / 'snapshot_manifest.json').read_text(encoding='utf-8'))
            expected = manifest.get('files_sha256', {})
            bad = []
            for rel, want in expected.items():
                f = local / 'src' / rel
                if not f.is_file():
                    bad.append(f'{rel}: 文件缺失')
                    continue
                got = hashlib.sha256(f.read_bytes()).hexdigest()
                if got != want:
                    bad.append(f'{rel}: 哈希不符')
            status = 'OK' if not bad else f'失败 {len(bad)} 项'
            print(f'  下载 {n_src} 个源码文件，清单 {len(expected)} 条 → {status}')
            for b in bad[:5]:
                print('   ', b)
            ok_all = ok_all and not bad
    finally:
        sftp.close()
        client.close()

    print('\n全部轮次哈希校验通过' if ok_all else '\n存在缺失或哈希不符，见上')
    return 0 if ok_all else 1


if __name__ == '__main__':
    raise SystemExit(main())
