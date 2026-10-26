"""Archive the four completed local EDA runs without credentials or virtualenvs.

Copies only explicit sources, logs and screenshots; never overwrites a package.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

from eda_analysis import _parse_sim_log


ROOT = Path(__file__).resolve().parent.parent
RUNS = (
    ('FIFO', 'designs/fifo', 'remote_runs/e8925c4673954ffd825955a1a9d908dc'),
    ('计数器生成', 'designs/counter_first_run', 'remote_runs/29eb449d00aa4602a7584fdca2a380e7'),
    ('自动纠错/第1轮_故障', 'designs/counter_autofix_demo/shadow/1266b2f2/iter_01',
     'remote_runs/cb0e5668a74148bea04ab379525defaf'),
    ('自动纠错/第2轮_修复', 'designs/counter_autofix_demo/shadow/1266b2f2/iter_02',
     'remote_runs/93946423cc7d45bab15217e9d8ffc76d'),
)
SCREENSHOTS = (
    ('FIFO_真实仿真通过.png', 'codex-clipboard-2bd4275f-6b14-49c5-8050-bd7c692b3f8d.png'),
    ('计数器_真实仿真通过.png', 'codex-clipboard-8db85f06-d664-4569-b76a-bfb80ca81f78.png'),
    ('自动纠错_两轮结果与补丁.png', 'codex-clipboard-5ce6f4e8-32e9-40dd-a366-90a8aa409464.png'),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--screenshots-dir', type=Path, required=True)
    parser.add_argument('--include-optimization', action='store_true',
                        help='Include the three completed optimization rounds')
    args = parser.parse_args()
    destination = args.out.resolve()
    zip_path = destination.with_suffix('.zip')
    if destination.exists() or zip_path.exists():
        raise SystemExit('Archive destination already exists; choose a new path.')

    copies: list[tuple[Path, str]] = []
    def add(source: Path, relative: str) -> None:
        if not source.is_file() or source.is_symlink():
            raise ValueError(f'Missing or invalid input: {source.name}')
        copies.append((source, relative))

    add(ROOT.parent.parent / 'EDA课设题目-2026秋.pdf', '00_题目要求/EDA课设题目-2026秋.pdf')
    add(ROOT / 'docs/报告素材保存清单.md', '先看这里_素材索引.md')
    for source in sorted((ROOT / 'code').iterdir()):
        if source.is_file() and source.suffix in {'.py', '.ps1', '.json'}:
            add(source, '01_项目实现/code/' + source.name)
    for name in ('requirements.txt', 'requirements-dev.txt', 'README.md', '使用说明.md', '交接说明.md'):
        add(ROOT / name, '01_项目实现/' + name)
    for name in ('gen_graph.mmd', 'gen_graph.png', 'loop_graph.mmd', 'loop_graph.png'):
        add(ROOT / 'docs' / name, '01_项目实现/架构图/' + name)

    metrics = []
    selected_runs = list(RUNS)
    optimization_rounds = (
        ('三轮优化/第1轮_初始异步复位', 'designs/counter_opt_round1',
         'remote_runs/a15ff7eb7988408a83b170273a7eb70d'),
        ('三轮优化/第2轮_边界与复位使能', 'designs/counter_opt_round2',
         'remote_runs/72f1ade39b8b4f85a62ddb2243358d97'),
        ('三轮优化/第3轮_多种子与功能覆盖', 'designs/counter_opt_round3',
         'remote_runs/242d86bdf6b447f88ba110a97abd673a'),
    )
    if args.include_optimization:
        selected_runs.extend(optimization_rounds)
        for name, workspace, _ in optimization_rounds:
            add(ROOT / workspace / 'optimization_record.json',
                f'02_本次真实实验/{name}/optimization_record.json')
        for name, filename in (
            ('优化第1轮_真实运行.png', 'codex-clipboard-dcd488cc-edf2-456e-8f4b-64b9fdebf455.png'),
            ('优化第2轮_真实运行.png', 'codex-clipboard-5c088eeb-8431-4d4e-aec2-4af2bbc4cef4.png'),
            ('优化第3轮_真实运行.png', 'codex-clipboard-d8dc04fb-8f39-448f-a84a-beb17af7ffd4.png'),
        ):
            add(args.screenshots_dir / filename, '03_截图/' + name)
    for name, workspace, run_relative in selected_runs:
        source_root = ROOT / workspace
        run = source_root / run_relative
        summary = json.loads((run / 'run_summary.json').read_text(encoding='utf-8'))
        parsed = _parse_sim_log(run / 'vcs_sim.log')
        if not parsed or parsed.get('checks') is None:
            raise ValueError(f'Incomplete simulation evidence: {name}')
        for source in sorted((source_root / 'generated').rglob('*')):
            if source.is_file() and source.suffix in {'.v', '.sv', '.vh', '.svh'}:
                add(source, f'02_本次真实实验/{name}/' + source.relative_to(source_root).as_posix())
        for filename in ('run_summary.json', 'vcs_compile.log', 'vcs_sim.log', 'coverage_dashboard.txt'):
            source = run / filename
            if source.exists():
                add(source, f'02_本次真实实验/{name}/日志/{filename}')
        metrics.append({
            'experiment': name, 'status': summary['status'],
            'compile_exit_code': summary.get('compile_exit_code'),
            'sim_exit_code': summary.get('sim_exit_code'),
            'checks': parsed['checks'], 'passed': parsed.get('passed'), 'failed': parsed.get('failed'),
            'coverage': summary.get('coverage'),
            'functional_bins_hit': parsed.get('functional_bins_hit'),
            'functional_bins_total': parsed.get('functional_bins_total'),
            'random_seeds_in_log': parsed.get('seeds', []),
            'remote_directory': summary.get('remote_directory'),
            'source_snapshot': summary.get('source_snapshot'),
            'local_log_directory': str(run),
        })

    for name in ('generation_request.txt', 'generation_review.json'):
        add(ROOT / 'designs/counter_first_run' / name, '02_本次真实实验/计数器生成/' + name)
    add(ROOT / 'designs/counter_autofix_demo/autofix.log', '02_本次真实实验/自动纠错/autofix.log')
    for name, filename in SCREENSHOTS:
        add(args.screenshots_dir / filename, '03_截图/' + name)
    if len({relative for _, relative in copies}) != len(copies):
        raise ValueError('Duplicate archive entry')

    # Read private values only in memory to prevent accidental inclusion.
    private = dotenv_values(ROOT / 'code/.env')
    secrets = [str(value).encode('utf-8') for key, value in private.items()
               if value and re.search(r'KEY|TOKEN|PASSWORD|SECRET', key, re.I)]
    for source, _ in copies:
        if any(secret in source.read_bytes() for secret in secrets):
            raise ValueError(f'Credential detected; input excluded from archival: {source.name}')

    destination.mkdir(parents=True)
    for source, relative in copies:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise ValueError(f'Copy checksum mismatch: {relative}')

    info = destination / '04_归档信息'
    info.mkdir()
    (destination / '01_项目实现/code/.env.example').write_text(
        '# Fill locally. Never share real credentials.\n'
        'DEEPSEEK_API_KEY=\nDEEPSEEK_BASE_URL=https://api.deepseek.com\n'
        'DEEPSEEK_MODEL=deepseek-flash\nEDA_SSH_HOST=192.168.142.128\n'
        'EDA_REMOTE_BASE=/home/IC/Desktop/EDA_Projects\nEDA_DATA_DIR=\n',
        encoding='utf-8')
    (info / '实验指标汇总.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    git_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    runtime = {
        'archive_date': '2026-10-24', 'python': sys.version,
        'source_repository': 'https://github.com/chenzhaoho/czh',
        'git_base_commit': git_commit, 'includes_local_changes': True,
        'installed_packages': sorted(
            [{'name': d.metadata['Name'], 'version': d.version} for d in importlib.metadata.distributions()],
            key=lambda d: d['name'].lower()),
    }
    (info / '环境版本.json').write_text(json.dumps(runtime, ensure_ascii=False, indent=2), encoding='utf-8')
    before = ROOT / RUNS[2][1] / 'generated/rtl/counter_8bit.v'
    after = ROOT / RUNS[3][1] / 'generated/rtl/counter_8bit.v'
    patch = ''.join(difflib.unified_diff(
        before.read_text(encoding='utf-8').splitlines(keepends=True),
        after.read_text(encoding='utf-8').splitlines(keepends=True),
        fromfile='iter_01/counter_8bit.v', tofile='iter_02/counter_8bit.v'))
    if not patch:
        raise ValueError('Automatic-repair experiment has no RTL change')
    before_tb = before.parent.parent / 'tb/tb_counter_8bit.v'
    after_tb = after.parent.parent / 'tb/tb_counter_8bit.v'
    if before_tb.read_bytes() != after_tb.read_bytes():
        raise ValueError('Automatic-repair testbench changed between rounds')
    (destination / '02_本次真实实验/自动纠错/模型补丁.diff').write_text(patch, encoding='utf-8')

    if args.include_optimization:
        baseline_dut = ROOT / 'designs/counter_first_run/generated/rtl/counter_8bit.v'
        previous_tb = ROOT / 'designs/counter_first_run/generated/tb/tb_counter_8bit.v'
        for name, workspace, _ in optimization_rounds:
            dut = ROOT / workspace / 'generated/rtl/counter_8bit.v'
            tb = ROOT / workspace / 'generated/tb/tb_counter_8bit.v'
            if dut.read_bytes() != baseline_dut.read_bytes():
                raise ValueError('Optimization unexpectedly changed the DUT')
            patch = ''.join(difflib.unified_diff(
                previous_tb.read_text(encoding='utf-8').splitlines(keepends=True),
                tb.read_text(encoding='utf-8').splitlines(keepends=True),
                fromfile=previous_tb.parent.parent.parent.name + '/tb_counter_8bit.v',
                tofile=Path(workspace).name + '/tb_counter_8bit.v'))
            (destination / f'02_本次真实实验/{name}/相对上一轮修改.diff').write_text(patch, encoding='utf-8')
            previous_tb = tb

    for source in destination.rglob('*'):
        if source.is_file() and (source.name == '.env' or any(secret in source.read_bytes() for secret in secrets)):
            raise ValueError('Private configuration detected; do not share this package.')
    manifest = {p.relative_to(destination).as_posix(): digest(p)
                for p in sorted(destination.rglob('*')) if p.is_file()}
    (info / 'SHA256SUMS.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    assert all(digest(destination / path) == expected for path, expected in manifest.items())
    shutil.make_archive(str(destination), 'zip', root_dir=destination.parent, base_dir=destination.name)
    print(f'Archived files: {len(manifest) + 1}')
    print('Checks: original-copy hashes, testbench unchanged, secret exclusion, archive manifest: PASS')
    print(f'Folder: {destination}')
    print(f'ZIP: {zip_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
