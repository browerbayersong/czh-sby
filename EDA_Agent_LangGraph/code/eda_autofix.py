"""仿真反馈驱动的自动纠错闭环（P0）。

设计约束（对齐交接文档 §9 P0）：
* 不覆盖用户已审批的 ``generated/``：所有改动先写入 ``shadow/iter_NN`` 影子目录，
  每轮都是一份完整快照，跑 VCS 用的也是影子目录。
* 不执行模型生成的任意 shell：远程调用仍然只走 ``remote_job`` 的固定命令模板。
* 环境类错误（license/网络/磁盘）不触发改代码，直接中止并上报。
* 有明确上限：最多 ``max_iterations`` 轮、单轮 LLM 只改必要的文件、补丁必须完整文件。
* 全程留痕：每轮的 run_label、退出码、错误类型、日志摘录、覆盖率、改动文件。

对外只暴露 :func:`run_autofix`，返回结构化结果，供 Streamlit 展示与人工采纳。
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from eda_remote_v8 import RemoteError, local_source_files, remote_job

SOURCE_SUFFIXES = {'.v', '.sv', '.vh', '.svh'}
MAX_PATCH_FILES = 4
MAX_PATCH_BYTES = 200_000
MAX_LLM_SOURCE_CHARS = 12_000
LOG_EXCERPT_CHARS = 4_000
SYNTAX_ERROR = re.compile(r'Error-\[(?:SE|VA|PA|CL)\b|syntax error|parse error', re.IGNORECASE)
# 只匹配真正的环境失败信息。不能用裸 'license'：VCS 每次启动都会打印
# “authorized in a license agreement” 的版权声明，会被误判。
ENV_PATTERNS = re.compile(
    r'unable to (?:check ?out|obtain|find) (?:a )?licen[cs]e'
    r'|licen[cs]e (?:error|checkout|expired|has expired|not available|unavailable)'
    r'|cannot find licen[cs]e|flexlm error'
    r'|no space left on device'
    r'|connection (?:refused|reset)'
    r'|permission denied'
    r'|timed out',
    re.IGNORECASE,
)


def _iter_text(working: dict[str, str], limit: int = MAX_LLM_SOURCE_CHARS) -> str:
    chunks, used = [], 0
    for rel, text in sorted(working.items()):
        remain = limit - used
        if remain <= 0:
            break
        body = text if len(text) <= remain else text[:remain] + '\n// [TRUNCATED]'
        chunks.append(f'=== {rel} ===\n{body}')
        used += len(body)
    return '\n\n'.join(chunks)


SIM_CRASH = re.compile(
    r'fatal signal|unexpected termination|Segmentation fault|core dumped'
    r'|out of memory|virtual memory exhausted',
    re.IGNORECASE,
)


def classify_failure(status: str, compile_log: str = '', sim_log: str = '') -> str:
    """把失败归类，决定是改代码还是中止。"""
    blob = f'{compile_log}\n{sim_log}'
    # 仿真器自身崩溃属于工具/资源问题，改 RTL 没有意义
    if SIM_CRASH.search(sim_log or ''):
        return 'simulator_crash'
    # 语法/解析错误优先：这类一定能改代码，不能被版权声明里的关键字带偏
    if SYNTAX_ERROR.search(blob):
        return 'compile'
    if ENV_PATTERNS.search(blob):
        return 'environment'
    if status == 'compile_failed':
        return 'compile'
    if status == 'failed':
        return 'assertion'
    if status == 'finished_unverified':
        return 'no_marker'
    return 'unknown'


def _tail(text: str, limit: int = LOG_EXCERPT_CHARS) -> str:
    if not text:
        return ''
    text = text.strip()
    return text if len(text) <= limit else '…\n' + text[-limit:]


def _excerpt(text: str, limit: int = LOG_EXCERPT_CHARS) -> str:
    """保留头部和尾部：首个失败点常在开头，汇总在结尾。"""
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    head = int(limit * 0.45)
    return text[:head] + '\n…[中间省略]…\n' + text[-(limit - head):]


def _load_json(raw: str) -> dict:
    text = (raw or '').strip()
    fenced = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError('模型没有返回 JSON 对象')
    return json.loads(text[start:end + 1])


def _validated_patches(data: dict, working: dict[str, str],
                       error_type: str = '') -> list[tuple[str, str]]:
    files = data.get('files')
    if not isinstance(files, list) or not files:
        raise ValueError('补丁里没有 files 列表')
    if len(files) > MAX_PATCH_FILES:
        raise ValueError(f'一次最多修改 {MAX_PATCH_FILES} 个文件')
    out: list[tuple[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError('files 元素必须是对象')
        path = str(item.get('path', '')).replace('\\', '/').strip()
        content = item.get('content', '')
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f'{path} 的内容为空')
        if not path.startswith('generated/'):
            raise ValueError(f'只允许修改 generated/ 下的文件：{path}')
        if '..' in path.split('/') or path.startswith('/'):
            raise ValueError(f'非法路径：{path}')
        if Path(path).suffix.lower() not in SOURCE_SUFFIXES:
            raise ValueError(f'只允许改 .v/.sv 源文件：{path}')
        if path not in working:
            raise ValueError(f'补丁引用了不存在的文件：{path}')
        if error_type == 'assertion' and path.replace('\\', '/').startswith('generated/tb/'):
            raise ValueError(
                '断言失败时不允许修改 Testbench，防止通过放宽检查掩盖 RTL 缺陷：' + path
            )
        if len(content.encode('utf-8')) > MAX_PATCH_BYTES:
            raise ValueError(f'{path} 超过单文件上限')
        if not re.search(r'\b(module|interface|package)\b', content):
            raise ValueError(f'{path} 里没有 module/interface/package 声明')
        out.append((path, content.rstrip() + '\n'))
    return out


FAIL_LINE = re.compile(r'\[FAIL\][^\n]*?exp=(\w+)\s+got=(\w+)')


def summarize_failures(log: str, top: int = 5) -> str:
    """把 [FAIL] 行聚合成典型模式，帮助模型定位根因。"""
    hits = FAIL_LINE.findall(log or '')
    if not hits:
        return ''
    counts: dict[tuple[str, str], int] = {}
    for pair in hits:
        counts[pair] = counts.get(pair, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:top]
    detail = '；'.join(f'exp={e} got={g}（{n} 次）' for (e, g), n in ranked)
    return f'共 {len(hits)} 处 [FAIL]。最常见：{detail}'


def _propose_patch(working: dict[str, str], error_type: str, excerpt: str,
                   summary: str, log: Callable[[str], None]) -> list[tuple[str, str]]:
    from langchain_core.messages import HumanMessage, SystemMessage

    from first_do import llm

    system = (
        '你是 Verilog/SystemVerilog 修复助手。根据编译或仿真日志定位缺陷，'
        '只修改真正有问题的文件，其余保持原样。'
        '只输出一个 JSON 对象，形如 '
        '{"reason":"一句话说明改了什么、为什么","files":[{"path":"generated/rtl/x.v","content":"完整文件内容"}]}。'
        'content 必须是可独立编译的完整文件，不是 diff、不是片段。'
        '不要修改模块名、文件名和端口列表，除非日志明确说明它们不一致。'
        'Testbench 是验证依据：禁止通过放宽检查、删除断言、修改期望值来让测试通过；'
        '断言失败时优先修改 RTL 的逻辑错误。'
        '不得输出任何命令、脚本或与 JSON 无关的解释。'
    )
    user = (
        f'失败类型：{error_type}\n\n'
        + (f'失败模式统计：{summary}\n\n' if summary else '')
        + f'日志摘录：\n{excerpt}\n\n'
        f'当前源文件：\n{_iter_text(working)}\n\n'
        '请给出最小必要修改。'
    )
    log(f'调用 DeepSeek 生成补丁（{error_type}）…')
    raw = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content
    data = _load_json(raw if isinstance(raw, str) else str(raw))
    reason = str(data.get('reason', '')).strip()
    if reason:
        log(f'模型说明：{reason}')
    return _validated_patches(data, working, error_type)


def _stage(dst: Path, approved: list[tuple[str, Path]], working: dict[str, str]) -> Path:
    dst.mkdir(parents=True, exist_ok=True)
    for rel, src in approved:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel in working:
            target.write_text(working[rel], encoding='utf-8', newline='\n')
        else:
            shutil.copy2(src, target)
    return dst


def _diff(original: str, patched: str, rel: str) -> str:
    return '\n'.join(difflib.unified_diff(
        original.splitlines(), patched.splitlines(),
        fromfile=f'{rel}（已批准）', tofile=f'{rel}（建议）', lineterm='',
    ))


def run_autofix(cfg, workspace: Path, chat_id: str, tb_top: str,
                remote_base: str, project_name: str,
                max_iterations: int = 3,
                log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """保持原接口：内部执行 StateGraph 闭环（eda_graph.build_loop_graph）。

    图结构：stage → simulate → analyze ─(条件边)→ patch → stage，
    终止条件统一汇入 finalize。不改动已批准文件，补丁只写入 shadow/iter_NN。
    """
    from eda_graph import run_loop
    return run_loop(
        cfg, Path(workspace), chat_id, tb_top, remote_base, project_name,
        max_iterations=max_iterations, log=log,
    )


def adopt_result(workspace: Path, result: dict[str, Any],
                 log: Callable[[str], None] | None = None) -> list[str]:
    """把最终建议写回已批准目录（由用户在界面确认后调用）。"""
    log = log or (lambda _m: None)
    workspace = Path(workspace)
    written: list[str] = []
    for rel, content in sorted(result.get('proposed', {}).items()):
        if not rel.startswith('generated/'):
            continue
        target = workspace / rel
        # 只在内容确实变化时写入，避免覆盖用户批准后的手工修改
        if target.is_file():
            current = target.read_text(encoding='utf-8', errors='replace')
            if current == content:
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8', newline='\n')
        written.append(rel)
        log(f'已写入 {rel}')
    return written
