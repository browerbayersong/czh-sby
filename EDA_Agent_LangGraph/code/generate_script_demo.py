"""Generate the missing simulation script through the real DeepSeek/LangGraph graph."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from eda_script_demo import RTL, SCRIPT, TB, digest, validate_script
import eda_agent_v8_core as core


REQUEST = """为现有的、已通过真实 VCS 验证的计数器工程生成仿真脚本。
只输出一个文件 scripts/run_vcs.sh，不修改或复制 RTL 和 Testbench。
参考已有 generated/rtl/counter_8bit.v 和 generated/tb/tb_counter_8bit.v。
目标顶层 tb_counter_8bit；目标环境为 Linux bash、VCS I-2014.03。
运行器会先创建独立快照 src/ 和相邻的 build/，并从 src/ 启动本脚本。
脚本本身不要 cd、mkdir、导出环境变量、清理文件或打印仿真通过标记。
首行 #!/bin/bash，随后 set -euo pipefail。允许注释、空行、反斜杠续行。
之后必须只有三个工具命令，依次编译、仿真、覆盖率报告；不可使用变量或函数。
1. 编译命令以 timeout 300s /opt/Synopsys/VCS2014/bin/vcs 开头。
参数必须含 -full64 -sverilog -timescale=1ns/1ps，
-cm line+cond+fsm+tgl+branch -cm_dir ../build/cov.vdb，
-top tb_counter_8bit -o ../build/simv，以及两个已有 Verilog 源文件的完整相对路径。
可选 +incdir+generated/rtl 或 +incdir+generated/tb，不得加入其他参数。
编译日志重定向 > ../build/vcs_compile.log 2>&1。
2. 仿真命令以 timeout 120s ../build/simv 开头，参数只有
-cm line+cond+fsm+tgl+branch -cm_dir ../build/cov.vdb，
日志重定向 > ../build/vcs_sim.log 2>&1。
3. 报告命令以 timeout 120s /opt/Synopsys/VCS2014/bin/urg 开头，参数只有
-dir ../build/cov.vdb -format text -report ../build/covReport，
日志重定向 > ../build/urg.log 2>&1。
参数顺序可以按工具惯例组织。不要增加 echo、cat、rm、联网命令或 shell 分支。
本轮只生成文本；运行是否通过必须以后续真实 EDA 日志为准。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=False)
    for relative in (RTL, TB):
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.source / relative, target)
    (workspace / 'generation_request.txt').write_text(REQUEST, encoding='utf-8', newline='\n')
    traces = workspace / 'llm_trace.jsonl'
    original = core.llm_text
    count = 0

    def traced(system: str, user: str) -> str:
        nonlocal count
        count += 1
        print(f'DeepSeek 文本生成调用 {count}…', flush=True)
        response = original(system, user)
        # Only application prompts and responses; never HTTP headers or API keys.
        with traces.open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps({'call': count, 'system': system, 'user': user,
                                     'response': response}, ensure_ascii=False) + '\n')
        return response

    core.llm_text = traced
    try:
        result = core.run_task(REQUEST, '', workspace)
    finally:
        core.llm_text = original
    (workspace / 'generation_result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    drafts = result.get('drafts') or []
    if result.get('error') or len(drafts) != 1 or drafts[0]['name'] != 'scripts/run_vcs.sh':
        raise ValueError('模型未生成约定的唯一脚本；原始响应已保留，不执行')
    script = drafts[0]['code']
    review = validate_script(script)
    target = workspace / SCRIPT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(script, encoding='utf-8', newline='\n')
    bash = Path('C:/Program Files/Git/bin/bash.exe')
    if bash.is_file():
        checked = subprocess.run([str(bash), '-n', SCRIPT], cwd=workspace,
                                 text=True, capture_output=True, timeout=20)
        (workspace / 'local_bash_syntax.log').write_text(
            checked.stdout + checked.stderr, encoding='utf-8')
        review['local_bash_syntax_exit_code'] = checked.returncode
        if checked.returncode:
            raise ValueError('生成脚本未通过本地 bash 语法检查')
    manifest = {
        'when': datetime.now().isoformat(timespec='seconds'),
        'origin': 'real DeepSeek API through eda_agent_v8_core.run_task / LangGraph',
        'model': os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-pro'),
        'traced_text_calls': count,
        'trace_scope': 'llm_text file-generation calls only; JSON planning/review results are in generation_result.json',
        'graph_review_status': result.get('review_status'),
        'script_review': review,
        'hdl_source': str(args.source.resolve()),
        'hdl_changes': False, 'remote_execution_status': 'pending',
        'files_sha256': {rel: digest((workspace / rel).read_bytes()) for rel in (RTL, TB, SCRIPT)},
    }
    (workspace / 'generation_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('真实 API 生成完毕；脚本审阅通过，等待虚拟机实跑。', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
