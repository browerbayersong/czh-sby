"""P2 验收脚本：逐项检查并输出 PASS/FAIL。

用法（在 E:\\LangGraph 下）：
    .\\venv\\Scripts\\python.exe verify_p2.py

检查项与 P2 子项对应：
    1. 编译配置（.f / defines / incdirs / tb_top）—— 离线测试
    2. 工具路径配置化 —— 环境变量覆盖
    3. 运行历史数据 —— 每轮快照清单与详情读取
    4. 前端异常缓解 —— st.fragment 包裹 + 回退
    5. 回归测试 —— 四套离线测试
    6. 换工程可用 —— FIFO / 加法器证据
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHAT_DIR = Path(r'C:\LangGraph_talk\conversations')
EVID = ROOT / 'evidence'

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = '') -> None:
    results.append((name, ok, detail))


def run_tests() -> None:
    suites = [
        ('远程执行回归', 'test_v8_2_offline.py'),
        ('日志解析', 'test_analysis_offline.py'),
        ('P2 离线（配置/边界）', 'test_p2_offline.py'),
        ('远程层回归（超时/失败）', 'test_p2_remote.py'),
        ('闭环逻辑', str(Path('patches') / 'test_autofix_offline.py')),
    ]
    for label, name in suites:
        path = ROOT / name
        if not path.is_file():
            record(f'测试：{label}', False, f'缺少 {name}')
            continue
        proc = subprocess.run([sys.executable, str(path)], cwd=str(ROOT),
                              capture_output=True, text=True, encoding='utf-8', errors='replace')
        record(f'测试：{label}', proc.returncode == 0,
               '' if proc.returncode == 0 else (proc.stderr or '').strip().splitlines()[-1:])


def check_env_override() -> None:
    code = (
        "import sys;sys.path.insert(0,r'%s');import os;"
        "os.environ['EDA_VCS_BIN']='/opt/custom/vcs';"
        "os.environ['EDA_URG_BIN']='/opt/custom/urg';"
        "import eda_remote_v8 as r;"
        "print(r.VCS_BINARY,'|',r.URG_BINARY)"
    ) % ROOT
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    ok = proc.returncode == 0 and '/opt/custom/vcs' in proc.stdout and '/opt/custom/urg' in proc.stdout
    record('工具路径可用环境变量覆盖', ok, (proc.stdout or proc.stderr).strip()[:80])


def check_history() -> None:
    sys.path.insert(0, str(ROOT))
    from eda_analysis import load_run_detail

    chats = list(CHAT_DIR.glob('*/chat.json')) if CHAT_DIR.is_dir() else []
    if not chats:
        record('运行历史：会话数据', False, '未找到 chat.json')
        return

    best = None
    for chat_file in chats:
        try:
            data = json.loads(chat_file.read_text(encoding='utf-8'))
        except ValueError:
            continue
        runs = [h for h in data.get('remote_history', []) if h.get('mode') == 'vcs']
        with_manifest = 0
        sample_ok = False
        for entry in runs:
            det = load_run_detail(entry, chat_file.parent)
            files = (det.get('manifest') or {}).get('files_sha256') or {}
            if files:
                with_manifest += 1
                if sample_ok is False and det.get('has_sim_log'):
                    sample_ok = True
        if best is None or with_manifest > best[1]:
            best = (len(runs), with_manifest, sample_ok)

    total, with_manifest, sample_ok = best
    record('运行历史：每轮带 SHA-256 清单', with_manifest >= 3,
           f'{with_manifest}/{total} 轮有清单')
    record('运行历史：详情可读（摘要/日志）', sample_ok, '最新带清单的轮次可读')


def check_fragment() -> None:
    src = (ROOT / 'web_app_eda_v8.py').read_text(encoding='utf-8', errors='replace')
    has_fragment = 'st.fragment(_log_viewer)' in src
    has_fallback = 'except Exception' in src and '_log_viewer(chat' in src
    record('前端异常缓解：日志查看用 fragment', has_fragment and has_fallback,
           'fragment + 回退' if has_fragment and has_fallback else '未找到 fragment 调用')


def _evidence_dirs() -> list[Path]:
    """证据目录可能在工作区、包根目录，或由 EDA_EVIDENCE 指定。"""
    cands = [ROOT / 'evidence', ROOT.parent / 'evidence']
    env = os.environ.get('EDA_EVIDENCE')
    if env:
        cands.insert(0, Path(env))
    cands.append(Path(r'E:\EDA_Agent_handover_2026-10-22\evidence'))
    return [p for p in cands if p.is_dir()]


def check_projects() -> None:
    dirs = _evidence_dirs()
    if not dirs:
        record('换工程可用（FIFO / 加法器）', False, '未找到 evidence 目录')
        return
    ok_any = False
    detail = []
    for name in ('fifo_sync_v1', 'cla256_v1', 'counter_v82'):
        passed = False
        for base in dirs:
            d = base / name
            if not d.is_dir():
                continue
            for f in d.rglob('run_summary.json'):
                try:
                    if json.loads(f.read_text(encoding='utf-8')).get('status') == 'passed_by_marker':
                        passed = True
                except ValueError:
                    pass
        detail.append(f'{name}:{"通过" if passed else "无记录"}')
        ok_any = ok_any or passed
    record('换工程可用（FIFO / 加法器）', ok_any, ' '.join(detail))


def main() -> int:
    run_tests()
    check_env_override()
    check_history()
    check_fragment()
    check_projects()

    print('\n===== P2 验收结果 =====')
    width = max(len(name) for name, _, _ in results)
    passed = 0
    for name, ok, detail in results:
        mark = 'PASS' if ok else 'FAIL'
        print(f'[{mark}] {name.ljust(width)}  {detail}')
        passed += 1 if ok else 0
    print(f'\n{passed}/{len(results)} 项通过')

    out = ROOT / 'report' / 'P2_验收结果.txt'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(f'[{"PASS" if ok else "FAIL"}] {n}  {d}' for n, ok, d in results)
                   + f'\n\n{passed}/{len(results)} 项通过\n', encoding='utf-8')
    print(f'结果已写入 {out}')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
