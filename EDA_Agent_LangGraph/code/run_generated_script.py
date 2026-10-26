"""Run the reviewed model-generated counter script and collect its real EDA evidence."""
from __future__ import annotations

import argparse
import getpass
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from eda_remote_v8 import SSHSettings
from eda_script_demo import archive_script_demo, run_script_demo


def main() -> int:
    load_dotenv(Path(__file__).with_name('.env'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--project', default='counter_script_demo')
    parser.add_argument('--host', default=os.getenv('EDA_SSH_HOST', '192.168.142.128'))
    parser.add_argument('--user', default='IC')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--remote-base', default='/home/IC/Desktop/EDA_Projects')
    parser.add_argument('--chat-id', default='f' * 32)
    parser.add_argument('--archive-dir', type=Path,
                        default=Path(__file__).resolve().parents[3] / '报告素材')
    args = parser.parse_args()
    password = getpass.getpass(f'{args.user}@{args.host} 的 SSH 密码（不回显）: ')
    settings = SSHSettings(args.host, args.user, args.port, password)
    result = run_script_demo(settings, args.workspace, project=args.project,
                             remote_base=args.remote_base, chat_id=args.chat_id)
    archive = archive_script_demo(args.workspace, result,
        args.archive_dir / ('EDA_模型生成脚本_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')))
    print('\n===== 模型生成脚本：真实执行结果 =====')
    print(f"最终状态    : {result['status']}")
    print('脚本来源    : DeepSeek + LangGraph')
    print(f"脚本返回码  : {result.get('script_exit_code')}")
    print(f"远端目录    : {result['remote_directory']}")
    metrics = result.get('metrics') or {}
    print(f"检查点      : 总计 {metrics.get('checks')}，通过 {metrics.get('passed')}，失败 {metrics.get('failed')}")
    print(f"功能覆盖    : {metrics.get('functional_bins_hit')}/{metrics.get('functional_bins_total')}")
    cov = result.get('coverage') or {}
    print(f"代码覆盖率  : 总分 {cov.get('score')} · 行 {cov.get('line')} · 分支 {cov.get('branch')} · 翻转 {cov.get('toggle')}")
    if result.get('error'):
        print(f"运行提示    : {result['error']}")
    print(f"本地日志    : {result['local_directory']}")
    print(f'报告素材    : {archive}（同时生成 ZIP）')
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
