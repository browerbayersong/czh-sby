"""P2 验收脚本：逐项检查并输出 PASS/FAIL。

设计原则（针对外部核查意见修正）：
* 测试脚本按仓库相对路径定位，不依赖 E:\\LangGraph；
* 换工程要求 FIFO / 加法器 / 计数器**同时**有通过记录，不再用 OR；
* 历史检查要求**每一轮**都有快照清单，缺一轮即 FAIL 并给出补齐命令；
* 前端只声明「缓解代码存在」，不宣称缺陷已修复。

用法（仓库内 code 目录或本机工作目录均可）：
    python verify_p2.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = '') -> None:
    results.append((name, ok, detail))


def _find_test(name: str) -> Path | None:
    """测试可能位于同目录或上级 patches/，按仓库布局与本地布局都能找到。"""
    for cand in (ROOT / name, ROOT / 'patches' / name, ROOT.parent / 'patches' / name):
        if cand.is_file():
            return cand
    return None


def run_tests() -> None:
    suites = [
        ('远程执行回归', 'test_v8_2_offline.py'),
        ('日志解析', 'test_analysis_offline.py'),
        ('P2 离线（配置/边界）', 'test_p2_offline.py'),
        ('远程层回归（超时/失败）', 'test_p2_remote.py'),
        ('闭环逻辑', 'test_autofix_offline.py'),
    ]
    for label, name in suites:
        path = _find_test(name)
        if path is None:
            record(f'测试：{label}', False, f'缺少 {name}')
            continue
        proc = subprocess.run([sys.executable, str(path)], cwd=str(path.parent),
                              capture_output=True, text=True, encoding='utf-8', errors='replace')
        tail = (proc.stderr or proc.stdout or '').strip().splitlines()[-1:]
        record(f'测试：{label}', proc.returncode == 0, '' if proc.returncode == 0 else str(tail))


def check_env_override() -> None:
    code = (
        "import sys;sys.path.insert(0, r'%s');import os;"
        "os.environ['EDA_VCS_BIN']='/opt/custom/vcs';"
        "os.environ['EDA_URG_BIN']='/opt/custom/urg';"
        "import eda_remote_v8 as r;"
        "print(r.VCS_BINARY,'|',r.URG_BINARY)"
    ) % ROOT
    proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    ok = (proc.returncode == 0 and '/opt/custom/vcs' in proc.stdout
          and '/opt/custom/urg' in proc.stdout)
    record('工具路径可用环境变量覆盖', ok, (proc.stdout or proc.stderr).strip()[:80])


def _chat_dir() -> Path | None:
    env = os.environ.get('EDA_CHAT_DIR')
    if env and Path(env).is_dir():
        return Path(env)
    default = Path(r'C:\LangGraph_talk\conversations')
    return default if default.is_dir() else None


def check_history() -> None:
    sys.path.insert(0, str(ROOT))
    from eda_analysis import load_run_detail

    base = _chat_dir()
    if base is None:
        record('运行历史：会话数据', False,
               '未找到会话目录；请设置 EDA_CHAT_DIR 指向 conversations 目录')
        return

    chats = list(base.glob('*/chat.json'))
    if not chats:
        record('运行历史：会话数据', False, f'{base} 下没有 chat.json')
        return

    total = with_manifest = 0
    sample_ok = False
    missing: list[str] = []
    for chat_file in chats:
        try:
            data = json.loads(chat_file.read_text(encoding='utf-8'))
        except ValueError:
            continue
        runs = [h for h in data.get('remote_history', []) if h.get('mode') in ('vcs', 'autofix')]
        total += len(runs)
        for entry in runs:
            det = load_run_detail(entry, chat_file.parent)
            files = (det.get('manifest') or {}).get('files_sha256') or {}
            if files:
                with_manifest += 1
                if det.get('has_sim_log'):
                    sample_ok = True
            else:
                missing.append(str(entry.get('run_label') or entry.get('run_id')))

    # 每一轮都要有清单，缺一轮就不算完整历史
    record('运行历史：每轮都有 SHA-256 清单', total > 0 and with_manifest == total,
           f'{with_manifest}/{total}'
           + (f'；缺：{", ".join(missing[:6])}' if missing else ''))
    record('运行历史：详情可读（摘要/日志）', sample_ok, '至少一轮可读')


def check_fragment() -> None:
    src = (ROOT / 'web_app_eda_v8.py').read_text(encoding='utf-8', errors='replace')
    has_fragment = 'st.fragment(_log_viewer)' in src
    has_fallback = 'except Exception' in src and '_log_viewer(chat' in src
    record('前端：日志查看已用 fragment 缓解（不证明已修复）',
           has_fragment and has_fallback,
           'fragment + 回退' if has_fragment and has_fallback else '未找到 fragment 调用')


def _evidence_dirs() -> list[Path]:
    cands = [ROOT / 'evidence', ROOT.parent / 'evidence']
    env = os.environ.get('EDA_EVIDENCE')
    if env:
        cands.insert(0, Path(env))
    cands.append(Path(r'E:\EDA_Agent_handover_2026-10-22\evidence'))
    return [p for p in cands if p.is_dir()]


def check_projects() -> None:
    dirs = _evidence_dirs()
    if not dirs:
        record('换工程可用（FIFO / 加法器 / 计数器）', False, '未找到 evidence 目录')
        return

    status: dict[str, bool] = {}
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
        status[name] = passed

    detail = ' '.join(f'{k}:{"通过" if v else "缺失"}' for k, v in status.items())
    record('换工程可用（FIFO / 加法器 / 计数器）', all(status.values()), detail)


def check_compile_config_run() -> None:
    """真实跑过一次带 compile_cfg.json 的 VCS（宏/include/SV package 顺序）。"""
    for base in _evidence_dirs():
        f = base / 'p2cfg_v1' / 'run_summary.json'
        if f.is_file():
            try:
                s = json.loads(f.read_text(encoding='utf-8'))
            except ValueError:
                continue
            ok = s.get('compile_config_used') is True and s.get('status') == 'passed_by_marker'
            record('配置工程实机运行（宏/include/package）', ok,
                   f"status={s.get('status')} defines={s.get('defines')} sources={len(s.get('sources') or [])}")
            return
    record('配置工程实机运行（宏/include/package）', False, '未找到 evidence/p2cfg_v1')


def main() -> int:
    run_tests()
    check_env_override()
    check_history()
    check_fragment()
    check_projects()
    check_compile_config_run()

    print('\n===== P2 验收结果 =====')
    width = max(len(name) for name, _, _ in results)
    passed = 0
    for name, ok, detail in results:
        print(f'[{"PASS" if ok else "FAIL"}] {name.ljust(width)}  {detail}')
        passed += 1 if ok else 0
    print(f'\n{passed}/{len(results)} 项通过')

    out = ROOT / 'P2_验收结果.txt'
    out.write_text('\n'.join(f'[{"PASS" if ok else "FAIL"}] {n}  {d}' for n, ok, d in results)
                   + f'\n\n{passed}/{len(results)} 项通过\n', encoding='utf-8')
    print(f'结果已写入 {out}')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
