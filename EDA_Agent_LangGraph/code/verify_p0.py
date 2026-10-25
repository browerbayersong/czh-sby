"""P0 验收脚本：闭环能力逐项判定。

用法：
    .\\venv\\Scripts\\python.exe verify_p0.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import eda_autofix as fa  # noqa: E402
import eda_graph as eg  # noqa: E402

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = '') -> None:
    results.append((name, ok, detail))


def check_graph() -> None:
    g = eg.build_loop_graph().get_graph()
    nodes = {n for n in g.nodes if not n.startswith('__')}
    expect = {'stage', 'simulate', 'analyze', 'patch', 'finalize'}
    record('闭环是 StateGraph（5 节点）', nodes == expect, ','.join(sorted(nodes)))

    fields = set(eg.LoopState.__annotations__)
    need = {'iteration', 'max_iterations', 'error_type', 'log_excerpt', 'history', 'working'}
    record('状态字段齐备', need <= fields, f'{len(need & fields)}/{len(need)}')


def check_routes() -> None:
    cases = [
        ({'status': 'passed_by_marker'}, 'done'),
        ({'status': 'failed', 'error_type': 'environment', 'iteration': 1, 'max_iterations': 3}, 'abort'),
        ({'status': 'failed', 'error_type': 'simulator_crash', 'iteration': 1, 'max_iterations': 3}, 'abort'),
        ({'status': 'failed', 'error_type': 'assertion', 'iteration': 3, 'max_iterations': 3}, 'stop'),
        ({'status': 'failed', 'error_type': 'assertion', 'iteration': 1, 'max_iterations': 3}, 'patch'),
    ]
    ok = all(eg.route_after_analyze(c) == want for c, want in cases)
    record('条件边：通过/中止/到上限/继续修复', ok, f'{len(cases)} 种')

    ok2 = (eg.route_after_patch({'error': ''}) == 'stage'
           and eg.route_after_patch({'error': 'x'}) == 'finalize')
    record('条件边：补丁失败不再重跑', ok2)


def check_classify() -> None:
    checks = [
        (('compile_failed', "Error-[SE] Syntax error", ''), 'compile'),
        (('failed', '', '[FAIL] #1 exp=00 got=01'), 'assertion'),
        (('failed', '', 'An unexpected termination has occurred ... fatal signal'), 'simulator_crash'),
        (('compile_failed', 'Unable to checkout a license for VCS', ''), 'environment'),
        (('finished_unverified', '', 'no marker'), 'no_marker'),
    ]
    ok = all(fa.classify_failure(*args) == want for args, want in checks)
    record('失败分类（语法/断言/崩溃/环境/无标记）', ok, f'{len(checks)} 类')


def check_no_overwrite() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / 'generated/rtl').mkdir(parents=True)
        target = ws / 'generated/rtl/a.v'
        target.write_text('module a; endmodule\n', encoding='utf-8')
        other = ws / 'generated/rtl/b.v'
        other.write_text('module b; endmodule\n', encoding='utf-8')

        result = {'proposed': {
            'generated/rtl/a.v': 'module a; endmodule\n',       # 未变化
            'generated/rtl/b.v': 'module b; wire x; endmodule\n',  # 有变化
        }}
        written = fa.adopt_result(ws, result)
        record('采纳只写真正变化的文件', written == ['generated/rtl/b.v'], ','.join(written))
        # 未采纳前，源文件保持原样（由 shadow 机制保证，此处验证 adopt 的边界）
        record('未采纳文件不被改动', target.read_text(encoding='utf-8') == 'module a; endmodule\n')


def _summary(path: Path) -> dict:
    f = path / 'run_summary.json'
    if not f.is_file():
        return {}
    try:
        return json.loads(f.read_text(encoding='utf-8'))
    except ValueError:
        return {}


def find_evidence() -> list[Path]:
    cands = [ROOT / 'evidence', ROOT.parent / 'evidence',
             Path(r'E:\EDA_Agent_handover_2026-10-22\evidence')]
    return [p for p in cands if p.is_dir()]


def check_cases() -> None:
    dirs = find_evidence()
    if not dirs:
        record('验收案例①：语法错自动修复', False, '未找到 evidence')
        record('验收案例②：断言失败自动修复', False, '未找到 evidence')
        return

    def status(group: str) -> str:
        for base in dirs:
            d = base / group
            if d.is_dir():
                return (_summary(d).get('status') or '').strip()
        return ''

    s1_bad, s1_ok = status('case1_compile_failed'), status('case1_fixed')
    record('验收案例①：编译失败 → 修复通过', s1_bad == 'compile_failed' and s1_ok == 'passed_by_marker',
           f'{s1_bad or "缺失"} → {s1_ok or "缺失"}')

    s2_bad, s2_ok = status('case2_assert_failed'), status('case2_fixed')
    record('验收案例②：断言失败 → 修复通过', s2_bad == 'failed' and s2_ok == 'passed_by_marker',
           f'{s2_bad or "缺失"} → {s2_ok or "缺失"}')


def check_rounds_recorded() -> None:
    # 直接调用真实的 _record()，而不是拿一个手写的样例字典自我验证
    state = {
        'iteration': 1,
        'run': {'run_label': 'vcs_001', 'status': 'compile_failed', 'compile_exit_code': 1},
        'status': 'compile_failed',
        'error_type': 'compile',
        'log_excerpt': 'Error-[SE] Syntax error',
        'failure_summary': '',
        'working': {'generated/rtl/a.v': 'module a; endmodule\n'},
        'originals': {'generated/rtl/a.v': 'module a;\n'},
        'history': [],
    }
    rec = eg._record(state)
    need = {'index', 'run_label', 'status', 'error_type', 'changed_files', 'log_excerpt'}
    record('每轮记录字段完整（_record 实测）', need <= set(rec),
           ','.join(sorted(need & set(rec))))
    record('改动文件被正确识别', rec.get('changed_files') == ['generated/rtl/a.v'],
           ','.join(rec.get('changed_files') or []))


def main() -> int:
    check_graph()
    check_routes()
    check_classify()
    check_no_overwrite()
    check_cases()
    check_rounds_recorded()

    print('\n===== P0 验收结果 =====')
    width = max(len(n) for n, _, _ in results)
    passed = 0
    for name, ok, detail in results:
        print(f'[{"PASS" if ok else "FAIL"}] {name.ljust(width)}  {detail}')
        passed += 1 if ok else 0
    print(f'\n{passed}/{len(results)} 项通过')

    out = ROOT / 'report' / 'P0_验收结果.txt'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(f'[{"PASS" if ok else "FAIL"}] {n}  {d}' for n, ok, d in results)
                   + f'\n\n{passed}/{len(results)} 项通过\n', encoding='utf-8')
    print(f'结果已写入 {out}')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
