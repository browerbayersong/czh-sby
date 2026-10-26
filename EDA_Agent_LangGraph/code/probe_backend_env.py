"""Collect bounded, read-only DC/ICC/PT and technology-library inventory over SSH.

Passwords stay in memory. This does not run synthesis, alter libraries, or inspect
license contents, shell histories, SSH files, or unrelated user documents.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from eda_remote_v8 import SSHSettings, exec_checked, ssh_connect


PROBES = (
    ('identity_and_resources', 'id -un; uname -srmo; df -h /home/IC /tmp; free -m', 25),
    ('tool_paths',
     'for t in dc_shell dct_shell design_vision icc_shell pt_shell lc_shell vcs urg; '
     'do command -v "$t" || true; done', 25),
    ('technology_candidates',
     'ls -l /opt/Foundary_Library/TSMC90/aci/sc-x/synopsys/typical.db '
     '/opt/Foundary_Library/TSMC90/aci/sc-x/astro/tf/*.tf 2>/dev/null', 25),
    ('reference_flow_candidates',
     'for p in /home/IC/.synopsys_dc.setup /home/IC/.synopsys_icc.setup; '
     'do if test -f "$p"; then printf "\\nSETUP_PATH %s\\n" "$p"; '
     'grep -E "(target_library|link_library|search_path|mw_reference|tech_file|tlu|[.]db|[.]tf)" "$p" | head -n 35; fi; done', 50),
    ('physical_library_candidates',
     'ls -ld /opt/Foundary_Library/TSMC90/aci/sc-x/astro/tsmc090g_fram '
     '/opt/Foundary_Library/TSMC90/aci/sc-x/astro/tsmc090g_fram/FRAM 2>/dev/null', 25),
)


def main() -> int:
    load_dotenv(Path(__file__).with_name('.env'))
    parser = argparse.ArgumentParser(description='检查 DC/ICC/PT 与工艺库，仅收集环境信息')
    parser.add_argument('--host', default=os.getenv('EDA_SSH_HOST', '192.168.142.128'))
    parser.add_argument('--user', default='IC')
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parent.parent / 'designs/counter_backend')
    args = parser.parse_args()
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    folder = args.workspace.resolve() / 'environment_checks' / stamp
    folder.mkdir(parents=True, exist_ok=False)
    password = getpass.getpass(f'{args.user}@{args.host} 的 SSH 密码（不回显）: ')
    cfg = SSHSettings(host=args.host, user=args.user, password=password)
    results = {}
    ssh = ssh_connect(cfg)
    try:
        for index, (name, command, seconds) in enumerate(PROBES, 1):
            print(f'[{index}/{len(PROBES)}] 检查 {name}…', flush=True)
            code, out, err = exec_checked(ssh, command, timeout_seconds=seconds)
            (folder / (name + '.txt')).write_text(out + ('\nSTDERR:\n' + err if err else ''), encoding='utf-8')
            results[name] = {'exit_code': code, 'command': command, 'log': name + '.txt'}
        record = {'when': datetime.now().isoformat(timespec='seconds'), 'host': args.host,
                  'user': args.user, 'status': 'inventory_collected', 'sections': results,
                  'scope': 'bounded inventory only; executable paths do not prove licenses or usable process libraries'}
        (folder / 'environment_summary.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print('\n===== 后端环境检查完成 =====')
        paths = (folder / 'tool_paths.txt').read_text(encoding='utf-8').strip()
        print(paths or '未找到工具路径；请核对环境变量或安装目录。')
        count = len((folder / 'technology_candidates.txt').read_text(encoding='utf-8').splitlines())
        print(f'工艺库候选记录：{count} 条（还需核对是否匹配）')
        print(f'本地检查结果：{folder}')
        print('请回到聊天告诉我“检查好了”；我会读取这些文件继续配置，不需要发送密码。')
    finally:
        ssh.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
