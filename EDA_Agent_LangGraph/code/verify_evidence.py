"""只读复核归档实验；无需模型、SSH、EDA 工具或第三方依赖。

在任意目录运行：python <项目>/code/verify_evidence.py
这些是仓库历史实验的归档核验，不代表本机重新完成了 VCS 仿真。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from eda_analysis import _parse_sim_log


LABELS = ('vcs_004', 'vcs_006', 'vcs_007', 'vcs_015', 'vcs_016', 'vcs_017')


def verify_run(directory: Path) -> dict:
    errors = []
    required = ('snapshot_manifest.json', 'run_summary.json', 'vcs_compile.log',
                'vcs_sim.log', 'coverage_dashboard.txt')
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        return {'run': directory.name, 'ok': False, 'errors': ['missing: ' + ', '.join(missing)]}

    manifest = json.loads((directory / 'snapshot_manifest.json').read_text(encoding='utf-8'))
    summary = json.loads((directory / 'run_summary.json').read_text(encoding='utf-8'))
    hashes = manifest.get('files_sha256', {})
    if not hashes:
        errors.append('empty source manifest')
    source_root = (directory / 'src').resolve()
    for relative, expected in hashes.items():
        source = (source_root / relative).resolve()
        if not source.is_relative_to(source_root) or not source.is_file():
            errors.append(f'missing or invalid source: {relative}')
        elif hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            errors.append(f'SHA-256 mismatch: {relative} (check Git newline conversion)')

    metrics = _parse_sim_log(directory / 'vcs_sim.log')
    if summary.get('status') != 'passed_by_marker':
        errors.append(f'unexpected run status: {summary.get("status")}')
    if metrics.get('ended') != 'TEST PASSED' or metrics.get('failed') != 0:
        errors.append('simulation log does not confirm a passing run')

    dashboard = (directory / 'coverage_dashboard.txt').read_text(encoding='utf-8')
    score_match = re.search(
        r'Total Coverage Summary\s+SCORE\s+LINE\s+COND\s+TOGGLE\s+FSM\s+BRANCH\s+([\d.]+)',
        dashboard,
    )
    score = (summary.get('coverage') or {}).get('score')
    if not score_match or score is None or float(score_match.group(1)) != score:
        errors.append('coverage summary does not match the archived URG dashboard')

    return {
        'run': directory.name, 'ok': not errors, 'source_files': len(hashes),
        'checks': metrics.get('checks'),
        'coverage_score': score,
        'functional_bins_hit': metrics.get('functional_bins_hit'),
        'functional_bins_total': metrics.get('functional_bins_total'),
        'errors': errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path,
                        default=Path(__file__).resolve().parent.parent / 'evidence' / 'counter_v82')
    parser.add_argument('--json', action='store_true', help='Print machine-readable results')
    args = parser.parse_args()
    results = []
    for label in LABELS:
        try:
            results.append(verify_run(args.evidence / label))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            results.append({'run': label, 'ok': False, 'errors': [str(exc)]})
    if args.json:
        print(json.dumps(results, ensure_ascii=True, indent=2))
    else:
        print('Archive verification only; no VCS or model calls were made.')
        for item in results:
            print(f'{"PASS" if item["ok"] else "FAIL"}: {item["run"]} '
                  f'sources={item.get("source_files", "?")} checks={item.get("checks", "?")} '
                  f'coverage={item.get("coverage_score", "?")}%')
            for error in item['errors']:
                print(f'  {error}')
    return 0 if all(item['ok'] for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
