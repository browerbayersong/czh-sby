"""对指定工作空间执行一次 VCS（上传 + 编译 + 仿真 + 覆盖率）。

用途：验证流水线的工程通用性——换一个设计（如 FIFO）仍能独立建项目并留下完整记录。
密码运行时输入，不落盘。

用法：
    .\\venv\\Scripts\\python.exe -u run_vcs_once.py --workspace E:\\LangGraph\\sandbox_fifo --project fifo_sync_v1 --tb tb_fifo_sync
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from eda_remote_v8 import SSHSettings, remote_job

if not sys.stdout.isatty():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()


def main() -> int:
    p = argparse.ArgumentParser(description='单次 VCS 运行（上传 + 编译 + 仿真 + 覆盖率）')
    p.add_argument('--workspace', required=True, help='含 generated/ 或 inputs/ 的工作空间')
    p.add_argument('--project', required=True, help='远端工程名（新建，不要与已有工程重名）')
    p.add_argument('--tb', required=True, help='Testbench 顶层模块名')
    p.add_argument('--host', default=None)
    p.add_argument('--user', default='IC')
    p.add_argument('--port', type=int, default=22)
    p.add_argument('--remote-base', default='/home/IC/Desktop/EDA_Projects')
    p.add_argument('--chat-id', default='f' * 32)
    args = p.parse_args()

    host = args.host or '192.168.81.128'
    password = getpass.getpass(f'{args.user}@{host} 的 SSH 密码（不回显）: ')
    cfg = SSHSettings(host=host, user=args.user, port=args.port, password=password)

    run = remote_job(
        cfg, Path(args.workspace), args.chat_id,
        mode='vcs', tb_top=args.tb,
        remote_base=args.remote_base, project_name=args.project,
    )

    print('\n===== 结果 =====')
    print(f"状态        : {run.get('status')}")
    print(f"工程目录    : {run.get('project_directory')}")
    print(f"运行目录    : {run.get('remote_directory')}")
    print(f"编译/仿真码 : {run.get('compile_exit_code')} / {run.get('sim_exit_code')}")
    sources = run.get('sources') or []
    print(f"编译源文件  : {len(sources)} 个")
    for s in sources:
        print(f"   - {s}")
    cov = run.get('coverage') or {}
    if cov:
        print(f"覆盖率      : 总分 {cov.get('score')} · 行 {cov.get('line')} · "
              f"分支 {cov.get('branch')} · 翻转 {cov.get('toggle')}")
    if run.get('coverage_error'):
        print(f"覆盖率错误  : {run['coverage_error']}")
    sim_log = (run.get('sim_log') or '')
    if sim_log:
        summary_tokens = ('total checks', 'TEST ', 'functional coverage',
                          'functional bins hit', 'random phase')
        tail = [ln for ln in sim_log.splitlines()
                if any(token in ln for token in summary_tokens)]
        for ln in tail:
            print(f"仿真摘要    : {ln.strip()}")
    print(f"本地日志    : {run.get('local_directory')}")
    return 0 if run.get('status') == 'passed_by_marker' else 1


if __name__ == '__main__':
    raise SystemExit(main())
