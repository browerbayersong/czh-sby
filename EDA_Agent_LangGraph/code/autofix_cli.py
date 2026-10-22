"""命令行跑一次自动纠错闭环，用于验收与演示。

不动网页里的对话，也不需要把密码写进任何文件（运行时交互输入）。

用法：
    cd E:\\LangGraph
    .\\venv\\Scripts\\python.exe autofix_cli.py
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from eda_autofix import run_autofix
from eda_remote_v8 import SSHSettings

if not sys.stdout.isatty():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()


def main() -> int:
    p = argparse.ArgumentParser(description='仿真反馈驱动的自动纠错闭环')
    p.add_argument('--host', default='192.168.81.128')
    p.add_argument('--user', default='IC')
    p.add_argument('--port', type=int, default=22)
    p.add_argument('--workspace', default=r'E:\LangGraph\sandbox_autofix')
    p.add_argument('--project', default='counter_autofix')
    p.add_argument('--remote-base', default='/home/IC/Desktop/EDA_Projects')
    p.add_argument('--tb', default='tb_counter_8bit')
    p.add_argument('--rounds', type=int, default=3)
    p.add_argument('--chat-id', default='f' * 32, help='隔离用的伪 chat id，避免和网页对话抢工程')
    p.add_argument('--log-file', default=r'E:\LangGraph\sandbox_autofix\autofix.log',
                   help='进度同时写入该文件；控制台被选中/阻塞时可从这里查看')
    args = p.parse_args()

    password = getpass.getpass(f'{args.user}@{args.host} 的 SSH 密码（不回显）: ')
    cfg = SSHSettings(host=args.host, user=args.user, port=args.port, password=password)

    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(f'=== {datetime.now():%Y-%m-%d %H:%M:%S} 开始 ===\n', encoding='utf-8')

    def log(msg: str) -> None:
        line = f"[{datetime.now():%H:%M:%S}] {msg}"
        # 先落盘：控制台若进入选择模式会阻塞 print，但文件仍然可查
        with log_path.open('a', encoding='utf-8') as fh:
            fh.write(line + '\n')
        print(line, flush=True)

    result = run_autofix(
        cfg, Path(args.workspace), args.chat_id, args.tb,
        args.remote_base, args.project,
        max_iterations=args.rounds, log=log,
    )

    print('\n===== 结果 =====')
    print(f"最终状态: {result['final_status']}  成功: {result['ok']}")
    for it in result['iterations']:
        print(f"  第 {it['index']} 轮 {it['run_label']}: {it['status']}"
              f"  编译码={it['compile_exit_code']} 仿真码={it['sim_exit_code']}"
              f"  类型={it['error_type'] or '-'}")
    if result['error']:
        print(f"备注: {result['error']}")
    for d in result['diffs']:
        print(f"\n--- 补丁 {d['path']} ---")
        print(d['diff'])
    print(f"\n影子目录: {result['shadow_dir']}")
    print('已批准文件未被改动；如需采纳，可在网页里点「采纳」或手工复制。')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
