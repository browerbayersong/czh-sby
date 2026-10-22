"""结果分析数据汇总：从会话历史 + 本地 run 目录提取每轮指标。

只读本地文件，不连虚拟机；供 Streamlit 的「结果分析」面板与 Markdown 导出使用。

解析的 Testbench 汇总字段：
    total checks / passed / failed、scenarios、随机种子、功能覆盖 bins、结束标记
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

TOTAL = re.compile(r'total checks\s*=\s*(\d+)\s*,\s*passed\s*=\s*(\d+)\s*,\s*failed\s*=\s*(\d+)')
FINISH = re.compile(r'\$finish at simulation time\s+(\d+)')
PASS_LINE = re.compile(r'^\[PASS\]', re.MULTILINE)
OK_LINE = re.compile(r'^OK at time', re.MULTILINE)
FAIL_LINE = re.compile(r'^\[FAIL\]', re.MULTILINE)
FAIL_DETAIL = re.compile(r'\[FAIL\][^\n]*?exp=(\w+)\s+got=(\w+)')
SCENARIOS = re.compile(r'scenarios:\s*(.+?)(?:\n\s*\n|\n\s*functional|\n\s*[=-]{5})', re.DOTALL)
BINS = re.compile(r'functional coverage\s*=\s*(\d+)\s*/\s*(\d+)\s*bins')
SEED = re.compile(r'seed\s*=\s*(\d+)')
ENDED = re.compile(r'^\s*(TEST PASSED|TEST FAILED[^\n]*)', re.MULTILINE)


def _parse_sim_log(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding='utf-8', errors='replace')

    total = TOTAL.search(text)
    if total:
        checks, passed, failed = (int(g) for g in total.groups())
    else:
        passed = len(PASS_LINE.findall(text)) + len(OK_LINE.findall(text))
        failed = len(FAIL_LINE.findall(text))
        checks = passed + failed or None

    finish = FINISH.search(text)
    raw_scenarios = SCENARIOS.search(text)
    scenarios = []
    if raw_scenarios:
        scenarios = [s.strip() for s in re.split(r'[,\n]+', raw_scenarios.group(1)) if s.strip()]
    seeds = sorted({int(s) for s in SEED.findall(text)})
    bins = BINS.search(text)
    ended = ENDED.search(text)

    counts: dict[tuple[str, str], int] = {}
    for exp, got in FAIL_DETAIL.findall(text):
        counts[(exp, got)] = counts.get((exp, got), 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]

    return {
        'checks': checks,
        'passed': passed or None,
        'failed': failed,
        'scenario_list': scenarios,
        'scenario_count': len(scenarios) or None,
        'seeds': seeds,
        'functional_bins_hit': int(bins.group(1)) if bins else None,
        'functional_bins_total': int(bins.group(2)) if bins else None,
        'ended': ended.group(1).strip() if ended else None,
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
        bins_hit = log.get('functional_bins_hit')
        bins_total = log.get('functional_bins_total')
        rows.append({
            '运行': entry.get('run_label', '?'),
            '状态': entry.get('status', '?'),
            '检查点': log.get('checks'),
            '通过数': log.get('passed'),
            '失败数': log.get('failed'),
            '场景数': log.get('scenario_count'),
            '种子数': len(log.get('seeds') or []) or None,
            '功能覆盖': (f'{bins_hit}/{bins_total}' if bins_hit is not None else None),
            '覆盖率(%)': coverage,
            '仿真结束(µs)': (log['finish_ps'] / 1e6) if log.get('finish_ps') else None,
            '编译码': entry.get('compile_exit_code'),
            '仿真码': entry.get('sim_exit_code'),
            '结束标记': log.get('ended'),
            '失败模式': '；'.join(log.get('top_fail') or []),
            '_scenarios': log.get('scenario_list') or [],
            '_seeds': log.get('seeds') or [],
        })
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """给面板用的汇总指标。"""
    if not rows:
        return {}
    covered = [r for r in rows if r.get('覆盖率(%)') is not None]
    passed_runs = [r for r in rows if r.get('状态') == 'passed_by_marker']
    latest = rows[-1]
    baseline = covered[0] if covered else None
    last_cov = covered[-1] if covered else None

    return {
        'runs': len(rows),
        'pass_rate': len(passed_runs) / len(rows),
        'latest_status': latest.get('状态'),
        'latest_checks': latest.get('检查点'),
        'latest_passed': latest.get('通过数'),
        'latest_scenarios': latest.get('场景数'),
        'latest_bins': latest.get('功能覆盖'),
        'latest_seeds': latest.get('种子数'),
        'latest_ended': latest.get('结束标记'),
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
        'scenario_detail': latest.get('_scenarios') or [],
        'seed_detail': latest.get('_seeds') or [],
    }


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
    latest_line = []
    if summary.get('latest_passed') is not None:
        latest_line.append(f"通过 {summary['latest_passed']}/{summary.get('latest_checks')}")
    if summary.get('latest_bins'):
        latest_line.append(f"功能覆盖 {summary['latest_bins']}")
    if summary.get('latest_scenarios'):
        latest_line.append(f"场景 {summary['latest_scenarios']} 类")
    if summary.get('latest_seeds'):
        latest_line.append(f"随机种子 {summary['latest_seeds']} 个")
    if summary.get('latest_ended'):
        latest_line.append(f"结束标记 `{summary['latest_ended']}`")
    if latest_line:
        lines.append('最新一轮：' + ' · '.join(latest_line))
    lines.append('')

    lines.append('#### 逐轮指标')
    lines.append('')
    lines.append('| 运行 | 状态 | 检查点 | 通过 | 失败 | 场景 | 功能覆盖 | 覆盖率 | 结束标记 |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for r in rows:
        lines.append('| {运行} | {状态} | {c} | {p} | {f} | {s} | {b} | {cov} | {e} |'.format(
            **{
                '运行': r['运行'], '状态': r['状态'],
                'c': fmt(r.get('检查点')), 'p': fmt(r.get('通过数')),
                'f': fmt(r.get('失败数')), 's': fmt(r.get('场景数')),
                'b': fmt(r.get('功能覆盖')), 'cov': fmt(r.get('覆盖率(%)'), '%'),
                'e': r.get('结束标记') or '—',
            }
        ))
    lines.append('')

    if summary.get('scenario_detail'):
        lines.append('#### 最新一轮验证场景')
        lines.append('')
        lines.append('、'.join(summary['scenario_detail']))
        lines.append('')
    if summary.get('seed_detail'):
        lines.append('随机种子：' + '、'.join(str(s) for s in summary['seed_detail']))
        lines.append('')

    failed = [r for r in rows if (r.get('失败数') or 0) > 0]
    if failed:
        lines.append('#### 失败轮次')
        lines.append('')
        lines.append('| 运行 | 失败数 | 失败模式 |')
        lines.append('| --- | --- | --- |')
        for r in failed:
            lines.append(f"| {r['运行']} | {r.get('失败数')} | {r.get('失败模式') or '日志中无 exp/got 明细'} |")
        lines.append('')

    lines.append('> 说明：覆盖率仅统计接入 urg 的运行；功能覆盖 bins 来自 Testbench 自身的场景统计，不等于代码覆盖率。')
    return '\n'.join(lines) + '\n'
