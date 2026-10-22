"""结果分析数据汇总：从会话历史 + 本地 run 目录提取每轮指标。

只读本地文件，不连虚拟机；供 Streamlit 的「结果分析」面板使用。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

FAIL_DETAIL = re.compile(r'\[FAIL\][^\n]*?exp=(\w+)\s+got=(\w+)')
TOTAL = re.compile(r'total checks = (\d+)')
FINISH = re.compile(r'\$finish at simulation time\s+(\d+)')
PASS_LINE = re.compile(r'^\[PASS\]', re.MULTILINE)
OK_LINE = re.compile(r'^OK at time', re.MULTILINE)
FAIL_LINE = re.compile(r'^\[FAIL\]', re.MULTILINE)


def _parse_sim_log(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding='utf-8', errors='replace')
    passed = len(PASS_LINE.findall(text)) + len(OK_LINE.findall(text))
    failed = len(FAIL_LINE.findall(text))
    total = TOTAL.search(text)
    finish = FINISH.search(text)

    counts: dict[tuple[str, str], int] = {}
    for exp, got in FAIL_DETAIL.findall(text):
        counts[(exp, got)] = counts.get((exp, got), 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]

    return {
        'checks': int(total.group(1)) if total else (passed + failed or None),
        'failed': failed,
        'finish_ps': int(finish.group(1)) if finish else None,
        'top_fail': [f'exp={e} got={g}（{n} 次）' for (e, g), n in top],
    }


def collect_run_metrics(chat: dict) -> list[dict[str, Any]]:
    """按时间顺序返回本对话的 VCS 运行指标。"""
    rows: list[dict[str, Any]] = []
    for entry in chat.get('remote_history', []):
        if entry.get('mode') != 'vcs':
            continue
        local = entry.get('local_directory')
        log = _parse_sim_log(Path(local) / 'vcs_sim.log') if local else {}
        coverage = (entry.get('coverage') or {}).get('score')
        rows.append({
            '运行': entry.get('run_label', '?'),
            '状态': entry.get('status', '?'),
            '检查点': log.get('checks'),
            '失败数': log.get('failed'),
            '覆盖率(%)': coverage,
            '仿真结束(µs)': (log['finish_ps'] / 1e6) if log.get('finish_ps') else None,
            '编译码': entry.get('compile_exit_code'),
            '仿真码': entry.get('sim_exit_code'),
            '失败模式': '；'.join(log.get('top_fail') or []),
        })
    return rows


def build_markdown(rows: list[dict[str, Any]], summary: dict[str, Any],
                   title: str = '运行分析') -> str:
    """把面板里的表格与指标导出成可直接粘进报告的 Markdown。"""
    if not rows:
        return ''

    def fmt(value: Any, suffix: str = '') -> str:
        return '—' if value is None else f'{value}{suffix}'

    lines: list[str] = [f'### {title}（自动生成）', '']
    lines.append(
        f"**汇总**：运行 {summary['runs']} 次 · 通过 {summary['pass_rate']:.0%} · "
        f"最新覆盖率 {fmt(summary.get('latest_coverage'), '%')}"
        + (f"（较基线 {summary['coverage_delta']:+.2f} pp）" if summary.get('coverage_delta') is not None else '')
        + f" · 检查点 {fmt(summary.get('latest_checks'))}"
        + (f"（较基线 {summary['checks_delta']:+d}）" if summary.get('checks_delta') else '')
    )
    lines.append('')

    lines.append('#### 逐轮指标')
    lines.append('')
    lines.append('| 运行 | 状态 | 检查点 | 失败数 | 覆盖率 | 仿真结束(µs) | 编译码 | 仿真码 |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- | --- |')
    for r in rows:
        lines.append('| {运行} | {状态} | {c} | {f} | {cov} | {t} | {cc} | {sc} |'.format(
            **{
                '运行': r['运行'], '状态': r['状态'],
                'c': fmt(r.get('检查点')), 'f': fmt(r.get('失败数')),
                'cov': fmt(r.get('覆盖率(%)'), '%'), 't': fmt(r.get('仿真结束(µs)')),
                'cc': fmt(r.get('编译码')), 'sc': fmt(r.get('仿真码')),
            }
        ))
    lines.append('')

    covered = [r for r in rows if r.get('覆盖率(%)') is not None]
    if covered:
        lines.append('#### 覆盖率趋势')
        lines.append('')
        lines.append('| 运行 | 覆盖率 |')
        lines.append('| --- | --- |')
        for r in covered:
            lines.append(f"| {r['运行']} | {r['覆盖率(%)']:.2f}% |")
        lines.append('')

    failed = [r for r in rows if (r.get('失败数') or 0) > 0]
    if failed:
        lines.append('#### 失败轮次')
        lines.append('')
        lines.append('| 运行 | 失败模式 |')
        lines.append('| --- | --- |')
        for r in failed:
            lines.append(f"| {r['运行']} | {r.get('失败模式') or '日志中无 exp/got 明细'} |")
        lines.append('')

    lines.append('> 说明：覆盖率仅统计接入 urg 的运行；失败轮次的覆盖率可能因错误分支被执行而虚高，不计入迭代收益。')
    return '\n'.join(lines) + '\n'


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """给面板用的汇总指标。"""
    if not rows:
        return {}
    covered = [r for r in rows if r.get('覆盖率(%)') is not None]
    passed = [r for r in rows if r.get('状态') == 'passed_by_marker']
    latest = rows[-1]
    baseline = covered[0] if covered else None
    last_cov = covered[-1] if covered else None

    return {
        'runs': len(rows),
        'pass_rate': len(passed) / len(rows),
        'latest_status': latest.get('状态'),
        'latest_checks': latest.get('检查点'),
        'baseline_coverage': baseline.get('覆盖率(%)') if baseline else None,
        'latest_coverage': last_cov.get('覆盖率(%)') if last_cov else None,
        'coverage_delta': (
            round(last_cov['覆盖率(%)'] - baseline['覆盖率(%)'], 2)
            if baseline and last_cov else None
        ),
        'checks_delta': (
            (latest.get('检查点') or 0) - (baseline.get('检查点') or 0)
            if baseline else None
        ),
        'failed_runs': [r for r in rows if (r.get('失败数') or 0) > 0],
        'coverage_series': [
            {'运行': r['运行'], '覆盖率(%)': r['覆盖率(%)']}
            for r in covered
        ],
        'checks_series': [
            {'运行': r['运行'], '检查点': r['检查点']}
            for r in rows if r.get('检查点')
        ],
    }
