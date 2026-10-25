"""自动纠错闭环的 StateGraph 实现。

把原先 `eda_autofix.run_autofix` 里的 while 循环改成显式图：

    START → stage → simulate → analyze ─┬─(通过/到上限/环境错误)→ finalize → END
                       ↑                 └─(可修)→ patch ─┬─(有补丁)→ stage
                       └──────────────────────────────────┴─(补丁失败)→ finalize

节点职责：
* stage    ：把当前源码写入 shadow/iter_NN 快照（不改动已批准文件）
* simulate ：调用 remote_job 跑 VCS（编译 + 仿真 + urg）
* analyze  ：分类失败、抽取日志摘要、把本轮写入 history
* patch    ：调用 DeepSeek 生成补丁并校验
* finalize ：汇总 diff 与最终状态

条件边由 `route_after_analyze` / `route_after_patch` 决定，不再靠 Python 控制流。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

import eda_autofix as fa
from eda_remote_v8 import RemoteError, local_source_files


class LoopState(TypedDict, total=False):
    # 运行配置
    cfg: Any
    workspace: str
    chat_id: str
    tb_top: str
    remote_base: str
    project_name: str
    max_iterations: int
    log: Callable[[str], None]

    # 迭代状态
    iteration: int
    base_dir: str
    stage_dir: str
    approved: list
    originals: dict
    working: dict

    # 单轮结果
    run: dict
    status: str
    error_type: str
    log_excerpt: str
    failure_summary: str
    history: list

    # 收尾
    error: str
    ok: bool
    final_status: str
    diffs: list


def _record(state: LoopState) -> dict:
    run = state.get('run') or {}
    working = state.get('working') or {}
    originals = state.get('originals') or {}
    return {
        'index': state.get('iteration', 0),
        'run_id': run.get('run_id', ''),
        'run_label': run.get('run_label', ''),
        'status': run.get('status', 'unknown'),
        'error_type': state.get('error_type', ''),
        'compile_exit_code': run.get('compile_exit_code'),
        'sim_exit_code': run.get('sim_exit_code'),
        'coverage': run.get('coverage') or {},
        'remote_directory': run.get('remote_directory', ''),
        'local_directory': run.get('local_directory', ''),
        'sources': run.get('sources') or [],
        'changed_files': [rel for rel in sorted(working) if working[rel] != originals.get(rel)],
        'log_excerpt': state.get('log_excerpt', ''),
        'failure_summary': state.get('failure_summary', ''),
    }


def stage_node(state: LoopState) -> dict:
    iteration = int(state.get('iteration', 0)) + 1
    log = state.get('log') or (lambda _m: None)
    stage = fa._stage(
        Path(state['base_dir']) / f'iter_{iteration:02d}',
        state['approved'],
        state['working'],
    )
    log(f"第 {iteration} 轮：上传 {len(state['working'])} 个源文件并运行 VCS…")
    return {'iteration': iteration, 'stage_dir': str(stage)}


def simulate_node(state: LoopState) -> dict:
    run = fa.remote_job(
        state['cfg'], Path(state['stage_dir']), state['chat_id'], mode='vcs',
        tb_top=state['tb_top'], remote_base=state['remote_base'],
        project_name=state['project_name'],
    )
    return {
        'run': {
            'run_id': run.get('run_id', ''),
            'run_label': run.get('run_label', ''),
            'status': run.get('status', 'unknown'),
            'compile_exit_code': run.get('compile_exit_code'),
            'sim_exit_code': run.get('sim_exit_code'),
            'coverage': run.get('coverage') or {},
            'remote_directory': run.get('remote_directory', ''),
            'local_directory': run.get('local_directory', ''),
            'sources': run.get('sources') or [],
            'compile_log': run.get('compile_log', '') or '',
            'sim_log': run.get('sim_log', '') or '',
        },
        'status': run.get('status', 'unknown'),
    }


def analyze_node(state: LoopState) -> dict:
    run = state['run']
    status = run['status']
    log = state.get('log') or (lambda _m: None)

    if status == 'passed_by_marker':
        error_type, excerpt, summary, note = '', '', '', None
    else:
        error_type = fa.classify_failure(status, run.get('compile_log', ''), run.get('sim_log', ''))
        raw = run.get('compile_log', '') if status == 'compile_failed' else run.get('sim_log', '')
        excerpt = fa._excerpt(raw)
        summary = fa.summarize_failures(run.get('sim_log', ''))
        if summary:
            log(summary)
        note = None
        if error_type == 'environment':
            note = '环境类错误（license/网络/磁盘），按约定不修改 RTL，已中止。'
        elif error_type == 'simulator_crash':
            note = ('仿真器崩溃（fatal signal），不是设计错误；'
                    '疑似资源不足或工具缺陷，已中止。请检查 df -h 与 free -m。')
        if note:
            log(note)

    patch = {
        'error_type': error_type,
        'log_excerpt': excerpt,
        'failure_summary': summary,
        'history': state.get('history', []),
    }
    if note:
        patch['error'] = note
    # history 需要带上本轮的分类结果，所以先合并再取记录
    merged = dict(state)
    merged.update(patch)
    patch['history'] = state.get('history', []) + [_record(merged)]
    log(f"第 {state['iteration']} 轮结果：{status}" + (f"（{error_type}）" if error_type else ''))
    return patch


def route_after_analyze(state: LoopState) -> str:
    if state.get('status') == 'passed_by_marker':
        return 'done'
    if state.get('error_type') in ('environment', 'simulator_crash'):
        return 'abort'
    if int(state.get('iteration', 0)) >= int(state.get('max_iterations', 3)):
        return 'stop'
    return 'patch'


def patch_node(state: LoopState) -> dict:
    log = state.get('log') or (lambda _m: None)
    try:
        patches = fa._propose_patch(
            state['working'], state['error_type'],
            state.get('log_excerpt', ''), state.get('failure_summary', ''), log,
        )
    except (ValueError, RemoteError, OSError) as exc:
        return {'error': f'补丁生成失败：{exc}'}

    working = dict(state['working'])
    applied = 0
    for rel, content in patches:
        if content != working.get(rel):
            working[rel] = content
            applied += 1
    if applied == 0:
        return {'error': '模型给出的补丁与现有内容一致，停止迭代以避免空转。'}
    return {'working': working}


def route_after_patch(state: LoopState) -> str:
    return 'finalize' if state.get('error') else 'stage'


def finalize_node(state: LoopState) -> dict:
    originals = state.get('originals') or {}
    working = state.get('working') or {}
    diffs = [
        {'path': rel, 'diff': fa._diff(originals[rel], working[rel], rel)}
        for rel in sorted(working)
        if working[rel] != originals.get(rel) and rel in originals
    ]
    status = state.get('status', 'not_run')
    return {
        'ok': status == 'passed_by_marker',
        'final_status': status,
        'diffs': diffs,
        'history': state.get('history', []),
    }


def build_loop_graph():
    builder = StateGraph(LoopState)
    builder.add_node('stage', stage_node)
    builder.add_node('simulate', simulate_node)
    builder.add_node('analyze', analyze_node)
    builder.add_node('patch', patch_node)
    builder.add_node('finalize', finalize_node)

    builder.add_edge(START, 'stage')
    builder.add_edge('stage', 'simulate')
    builder.add_edge('simulate', 'analyze')
    builder.add_conditional_edges('analyze', route_after_analyze, {
        'patch': 'patch', 'done': 'finalize', 'abort': 'finalize', 'stop': 'finalize',
    })
    builder.add_conditional_edges('patch', route_after_patch, {
        'stage': 'stage', 'finalize': 'finalize',
    })
    builder.add_edge('finalize', END)
    return builder.compile()


def run_loop(cfg, workspace: Path, chat_id: str, tb_top: str,
             remote_base: str, project_name: str,
             max_iterations: int = 3,
             log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """构建初态、执行图、把终态整理成与原 run_autofix 一致的结构。"""
    log = log or (lambda _m: None)
    max_iterations = max(1, min(int(max_iterations), 5))
    workspace = Path(workspace)

    approved = local_source_files(workspace)
    originals = {
        rel: path.read_text(encoding='utf-8', errors='replace')
        for rel, path in approved
        if Path(rel).suffix.lower() in fa.SOURCE_SUFFIXES
    }
    if not originals:
        raise RemoteError('没有可迭代的 .v/.sv 源文件')

    initial: LoopState = {
        'cfg': cfg,
        'workspace': str(workspace),
        'chat_id': chat_id,
        'tb_top': tb_top,
        'remote_base': remote_base,
        'project_name': project_name,
        'max_iterations': max_iterations,
        'log': log,
        'iteration': 0,
        'base_dir': str(workspace / 'shadow' / uuid4().hex[:8]),
        'approved': approved,
        'originals': originals,
        'working': dict(originals),
        'history': [],
        'error': '',
    }

    graph = build_loop_graph()
    final: LoopState = graph.invoke(
        initial,
        config={'recursion_limit': max_iterations * 4 + 10},
    )

    return {
        'ok': bool(final.get('ok')),
        'final_status': final.get('final_status', 'not_run'),
        'iterations': final.get('history', []),
        'error': final.get('error') or None,
        'diffs': final.get('diffs', []),
        'proposed': final.get('working', {}),
        'shadow_dir': final.get('base_dir', ''),
        'max_iterations': max_iterations,
    }
