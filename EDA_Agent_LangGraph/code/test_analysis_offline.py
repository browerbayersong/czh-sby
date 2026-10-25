"""Testbench 汇总解析的离线测试（不连虚拟机）。

覆盖：v1 风格（只有 OK at time）、v5 风格（total/passed/failed + 场景 + 种子 + bins）、
失败轮（[FAIL] 与 TEST FAILED）、以及缺字段时的降级行为。
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'patches' else Path(__file__).resolve().parent))
from eda_analysis import _parse_sim_log, build_markdown, summarize  # noqa: E402

V5 = """\
[INFO] tb_counter_8bit v5 start
[PASS] #1 t=3000 count=00
[PASS] #2 t=16000 count=00
[XFAIL] #3 t=45000 exp=01 got=00 (intentional)
[INFO] negative check injected error count = 1 (expect 1)
[INFO] random phase 0 start, seed=12648430
[INFO] random phase 1 start, seed=12648687
[INFO] random phase 2 start, seed=12648944
[INFO] functional coverage = 11/11 bins
======================================
 total checks = 1032, passed = 1032, failed = 0
 scenarios: reset, hold, increment, wrap, async_reset,
            en_edge, reset_narrow, negative_check, random x3
 functional bins hit = 11/11
 TEST PASSED
======================================
$finish at simulation time 10266000
CPU Time: 0.28 seconds
"""

V1 = """\
[INFO] tb_counter_8bit v1 start
OK at time 3000: count = 00
OK at time 16000: count = 00
======================================
 TEST PASSED
======================================
$finish at simulation time 2686000
"""

FAILED = """\
[PASS] #1 t=3000 count=00
[FAIL] #2 t=16000 exp=05 got=06
[FAIL] #3 t=26000 exp=06 got=07
======================================
 total checks = 851, passed = 849, failed = 2
 scenarios: reset, hold
 TEST FAILED (2 errors)
======================================
$finish at simulation time 8636000
"""


def parse(text: str) -> dict:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'vcs_sim.log'
        p.write_text(text, encoding='utf-8', newline='\n')
        return _parse_sim_log(p)


def main() -> int:
    v5 = parse(V5)
    assert v5['checks'] == 1032 and v5['passed'] == 1032 and v5['failed'] == 0, v5
    assert v5['functional_bins_hit'] == 11 and v5['functional_bins_total'] == 11, v5
    assert v5['ended'] == 'TEST PASSED', v5
    assert len(v5['seeds']) == 3 and 12648430 in v5['seeds'], v5
    assert 'negative_check' in v5['scenario_list'], v5
    assert v5['scenario_count'] >= 8, v5
    print('PASS: v5 汇总解析（checks/passed/failed/scenarios/seeds/bins/ended）')

    v1 = parse(V1)
    assert v1['checks'] == 2 and v1['passed'] == 2 and v1['failed'] == 0, v1
    assert v1['functional_bins_hit'] is None, v1
    assert v1['ended'] == 'TEST PASSED', v1
    print('PASS: v1 降级解析（无汇总行时按 OK at time 计数）')

    bad = parse(FAILED)
    assert bad['failed'] == 2 and bad['checks'] == 851, bad
    assert bad['ended'].startswith('TEST FAILED'), bad
    assert bad['top_fail'], bad
    print('PASS: 失败轮解析（failed 计数 / TEST FAILED / exp-got 模式）')

    rows = [{
        '运行': 'vcs_017', '状态': 'passed_by_marker', '检查点': v5['checks'],
        '通过数': v5['passed'], '失败数': v5['failed'], '场景数': v5['scenario_count'],
        '种子数': len(v5['seeds']), '功能覆盖': '11/11', '覆盖率(%)': 93.05,
        '仿真结束(µs)': 10.266, '编译码': 0, '仿真码': 0,
        '结束标记': v5['ended'], '失败模式': '',
        '_scenarios': v5['scenario_list'], '_seeds': v5['seeds'],
    }]
    summary = summarize(rows)
    assert summary['latest_passed'] == 1032 and summary['latest_bins'] == '11/11'
    md = build_markdown(rows, summary, '解析测试')
    for token in ('1032', '11/11', 'TEST PASSED', 'negative_check'):
        assert token in md, token
    print('PASS: 汇总指标与 Markdown 导出包含新增字段')

    print('全部解析测试通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
