# -*- coding: utf-8 -*-
"""v8.2 safe SSH/SFTP runner with a named persistent project and immutable run snapshots.

Never executes user/LLM-authored shell/Tcl. Runs only a fixed VCS command template.
Never touches a project not owned by the current chat. No deletion is performed.
"""
from __future__ import annotations

import json
import hashlib
import os
import posixpath
import re
import shlex
import stat
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Any

from eda_agent_v8_core import safe_rel_name, SPECIAL_NAMES

VCS_BINARY = '/opt/Synopsys/VCS2014/bin/vcs'
URG_BINARY = '/opt/Synopsys/VCS2014/bin/urg'
COVERAGE_METRICS = 'line+cond+fsm+tgl+branch'
COVERAGE_TIMEOUT = 120
# 覆盖率会显著增加仿真收尾时的内存/磁盘开销；资源紧张时可用 EDA_COVERAGE=0 关掉
COVERAGE_ENABLED = os.environ.get('EDA_COVERAGE', '1').strip().lower() not in {'0', 'false', 'off', 'no'}
DC_BINARY = '/opt/Synopsys/Synplify2015/bin/dc_shell'
ICC_BINARY = '/opt/Synopsys/ICC2016/bin/icc_shell'
SOURCE_SUFFIXES = frozenset({'.v', '.sv', '.vh', '.svh', '.f', '.tcl', '.sdc', '.txt', '.py', '.sh', '.mk', '.md', '.json', '.yml', '.yaml', '.cfg', '.ini', '.xdc'})
VERILOG_SUFFIXES = frozenset({'.v', '.sv'})
MAX_FILES = 512
MAX_TOTAL_BYTES = 50_000_000
MAX_FILE_BYTES = 4_000_000
MAX_OUTPUT_CAPTURE = 2_000_000
MAX_LOG_BYTES = 8_000_000
SIM_TIMEOUT = 120
COMPILE_TIMEOUT = 300
NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')
SSH_USERNAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.-]*$')
MODULE_RE = re.compile(r'\bmodule\s+(?:(?:automatic|static)\s+)?([a-zA-Z_][\w$]*)\b')


class RemoteError(RuntimeError):
    """A safe error that may be shown in the frontend (never includes passwords)."""


@dataclass(frozen=True)
class SSHSettings:
    host: str
    user: str = 'IC'
    port: int = 22
    password: str | None = None

    def validated(self) -> 'SSHSettings':
        if not self.host or len(self.host) > 253 or any(c.isspace() for c in self.host):
            raise RemoteError('SSH 主机 IP/地址不合法')
        if not SSH_USERNAME_RE.fullmatch(self.user) or self.user in {'root', '.', '..'}:
            raise RemoteError('仅允许普通 Linux 用户连接，禁止使用 root')
        if not isinstance(self.port, int) or not (1 <= self.port <= 65535):
            raise RemoteError('SSH 端口不合法')
        return self


def ssh_connect(cfg: SSHSettings):
    """Host-key-checked SSH using OpenSSH known_hosts (from previously verified Windows ssh).

    Unknown/replaced keys are rejected rather than silently trusted. Paramiko may
    support older ssh-rsa host keys; ssh-dss is neither added nor required.
    """
    cfg.validated()
    try:
        import paramiko
    except ImportError as e:
        raise RemoteError('尚未安装 Paramiko：请在项目虚拟环境执行 pip install "paramiko>=3.3,<4"') from e
    client = paramiko.SSHClient()
    known_hosts = Path.home() / '.ssh' / 'known_hosts'
    if not known_hosts.is_file():
        raise RemoteError(f'未找到 SSH 已知主机文件 {known_hosts}。请先使用 Windows ssh 手动核对指纹并连接一次。')
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    # VMware NAT 偶发抖动时 12s 太紧；连接超时放宽到 20s，并对超时/协议错误重试一次。
    connect_timeout = float(os.environ.get('EDA_SSH_TIMEOUT', '20'))
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            client.connect(
                hostname=cfg.host, port=cfg.port, username=cfg.user, password=cfg.password or None,
                timeout=connect_timeout, auth_timeout=25, banner_timeout=25,
                allow_agent=True, look_for_keys=True,
            )
            return client
        except paramiko.AuthenticationException as e:
            client.close()
            raise RemoteError(f'SSH 认证失败（{cfg.user}@{cfg.host}:{cfg.port}）：{e}') from e
        except Exception as e:  # noqa: BLE001 - 超时/协议错误统一重试一次
            last_error = e
            if attempt == 0:
                time.sleep(2.0)
                continue
            break
    client.close()
    raise RemoteError(
        f'SSH 连接失败（{cfg.user}@{cfg.host}:{cfg.port}）：{type(last_error).__name__}: {last_error}'
    ) from last_error


def exec_checked(ssh, command: str, *, timeout_seconds: int = 20) -> tuple[int, str, str]:
    """Read both channels incrementally with bounded memory and a wall-clock timeout."""
    transport = ssh.get_transport()
    if not transport or not transport.is_active():
        raise RemoteError('SSH 已断开')
    channel = transport.open_session(timeout=15)
    channel.settimeout(5)
    try:
        channel.exec_command(command)
        out, err = bytearray(), bytearray()
        out_trunc, err_trunc = False, False
        start = time.monotonic()
        while True:
            moved = False
            while channel.recv_ready():
                chunk = channel.recv(32768)
                if len(out) + len(chunk) <= MAX_OUTPUT_CAPTURE:
                    out.extend(chunk)
                else:
                    out_trunc = True
                moved = True
            while channel.recv_stderr_ready():
                chunk = channel.recv_stderr(32768)
                if len(err) + len(chunk) <= MAX_OUTPUT_CAPTURE:
                    err.extend(chunk)
                else:
                    err_trunc = True
                moved = True
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                code = channel.recv_exit_status()
                if out_trunc:
                    out.extend(b'\n[OUTPUT TRUNCATED]\n')
                if err_trunc:
                    err.extend(b'\n[ERROR TRUNCATED]\n')
                return code, out.decode('utf-8', 'replace'), err.decode('utf-8', 'replace')
            if time.monotonic() - start > timeout_seconds:
                raise RemoteError(f'远程命令超过 {timeout_seconds} 秒。已关闭 SSH 通道；实际 EDA 命令另有 Linux timeout 限制。')
            if not moved:
                time.sleep(0.08)
    finally:
        channel.close()


def connection_probe(cfg: SSHSettings) -> dict[str, Any]:
    """Only reports identity, working directory and binary existence. Nothing is uploaded."""
    ssh = ssh_connect(cfg)
    try:
        code, out, err = exec_checked(ssh, 'id -un; pwd; for p in '
                                      + ' '.join(shlex.quote(p) for p in [VCS_BINARY, DC_BINARY, ICC_BINARY])
                                      + '; do if test -x "$p"; then echo "TOOL_OK $p"; else echo "TOOL_MISSING $p"; fi; done')
        if code != 0:
            raise RemoteError(f'远程探测失败：{err or out}')
        first = out.splitlines()[0].strip() if out.splitlines() else ''
        if first != cfg.user:
            raise RemoteError(f'实际登录用户 {first!r} 与预期 {cfg.user!r} 不一致')
        return {'success': True, 'stdout': out, 'stderr': err}
    finally:
        ssh.close()


def local_source_files(workspace: Path) -> list[tuple[str, Path]]:
    """Only approved/stored text in inputs/ and generated/. No symlinks."""
    root = workspace.resolve(strict=True)
    files: list[tuple[str, Path]] = []
    total = 0
    for sub in ('inputs', 'generated'):
        folder = root / sub
        if folder.is_symlink():
            raise RemoteError(f'{sub} 是符号链接，拒绝上传')
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob('*')):
            if not path.resolve().is_relative_to(root):
                raise RemoteError(f'发现指向工作空间之外的文件/目录：{path}')
            if path.is_symlink():
                raise RemoteError(f'拒绝上传符号链接：{path}')
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            try:
                checked = safe_rel_name(rel)
            except ValueError as e:
                # Skip editor/secret files, but refuse suspicious paths with traversal.
                if path.name.startswith(('.', '~')):
                    continue
                raise RemoteError(f'非法源文件路径：{rel}：{e}') from e
            if checked != rel or (path.suffix.lower() not in SOURCE_SUFFIXES and path.name not in SPECIAL_NAMES):
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                raise RemoteError(f'上传文件超过 {MAX_FILE_BYTES} 字节：{rel}')
            total += path.stat().st_size
            files.append((rel, path))
            if len(files) > MAX_FILES or total > MAX_TOTAL_BYTES:
                raise RemoteError('工程文件数量或总容量超出安全上限')
    if not files:
        raise RemoteError('此对话还没有保存的工程文件。请先生成、审阅并保存，或者导入 RTL。')
    return files


def strip_verilog_comments(src: str) -> str:
    # Simple stripping to detect common modules; not a full SystemVerilog parser.
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', src, flags=re.S)


def source_manifest(files: list[tuple[str, Path]]) -> dict[str, Any]:
    """Select module owners; prefer approved/generated versions over imported originals.

    Ambiguous duplicate modules *within the same tier* are rejected, not guessed.
    """
    modules_by_file: dict[str, set[str]] = {}
    owners: dict[str, tuple[str, int]] = {}
    skipped: set[str] = set()
    for rel, local in files:
        if local.suffix.lower() not in VERILOG_SUFFIXES:
            continue
        src = local.read_text(encoding='utf-8', errors='replace')
        names = set(MODULE_RE.findall(strip_verilog_comments(src)))
        modules_by_file[rel] = names
        for name in names:
            priority = 2 if rel.startswith('generated/') else 1
            old = owners.get(name)
            if old is None:
                owners[name] = (rel, priority)
            elif old[1] < priority:
                owners[name] = (rel, priority)
                skipped.add(old[0])
            elif old[1] > priority:
                skipped.add(rel)
            elif old[0] != rel:
                raise RemoteError(f'同层出现重复模块 {name}：{old[0]} 与 {rel}。请先整理工程。')
    # If a file declares multiple modules, dropping it may drop unique modules too.
    for rel in list(skipped):
        if any(owners[m][0] == rel for m in modules_by_file[rel]):
            raise RemoteError(f'{rel} 同时含重复模块与独有模块，无法安全排除。请将模块拆成独立文件。')
    selected = [rel for rel in modules_by_file if rel not in skipped]
    if not selected:
        raise RemoteError('没有找到 .v 或 .sv RTL 文件')
    incdirs = sorted({posixpath.dirname(rel) for rel, _ in files
                      if rel.endswith(('.vh', '.svh', '.v', '.sv'))})
    tb_candidates = sorted(n for n, (rel, _) in owners.items()
                           if rel in selected and (n.lower().startswith('tb') or 'testbench' in n.lower()))
    return {'sources': selected, 'incdirs': incdirs,
            'testbenches': tb_candidates, 'modules': sorted(owners), 'excluded': sorted(skipped)}


def file_preview(workspace: Path) -> dict[str, Any]:
    fs = local_source_files(workspace)
    try:
        manifest = source_manifest(fs)
        error = ''
    except RemoteError as exc:
        manifest = {'sources': [], 'incdirs': [], 'testbenches': [], 'modules': [], 'excluded': []}
        error = str(exc)
    return {'file_count': len(fs), 'total_bytes': sum(p.stat().st_size for _, p in fs),
            'vcs_preview_error': error, **manifest}


def _lstat_dir(sftp, path: str) -> bool:
    try:
        info = sftp.lstat(path)
    except OSError as e:
        # Some SFTP servers use different exception text; only accept genuine not found.
        if getattr(e, 'errno', None) == 2:
            return False
        raise
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RemoteError(f'远程路径不是普通目录：{path}')
    return True


def _create_new_dir(sftp, path: str) -> None:
    if _lstat_dir(sftp, path):
        raise RemoteError(f'远程运行目录意外已经存在，拒绝覆盖：{path}')
    sftp.mkdir(path, mode=0o700)


def _ensure_shared_dir(sftp, path: str) -> None:
    if not _lstat_dir(sftp, path):
        try:
            sftp.mkdir(path, mode=0o700)
        except OSError as e:
            raise RemoteError(f'无法创建远程目录 {path}：{e}') from e
    if not _lstat_dir(sftp, path):
        raise RemoteError(f'无法使用远程目录：{path}')


# Only safe locations below the SSH user's home are accepted for a project base.
# A readable, user-chosen project name is appended; run names are sequential.
REMOTE_SEGMENT_RE = re.compile(r'^[\w][\w .()\-]{0,79}$', re.UNICODE)
REMOTE_DENIED_DIRS = frozenset({'adder', 'ref', 'mw_lib', '.ssh', '.config'})


def _remote_base_path(home: str, user_input: str) -> str:
    """Accept ~/foo, foo or /home/user/foo, but never leave the login home.

    Reject the old adder/ref tree, traversal, symlinks (checked separately) and shell metacharacters.
    Existing unrelated projects are NEVER silently adopted.
    """
    if not isinstance(user_input, str):
        raise RemoteError('Linux 上传根目录必须是文字')
    raw = user_input.strip()
    if not raw:
        raw = '~/eda_agent_runs'
    if raw.startswith('~/'):
        raw = posixpath.join(home, raw[2:])
    elif raw.startswith('~'):
        raise RemoteError('请使用 ~/目录名，不支持 ~其他用户名')
    elif not raw.startswith('/'):
        raw = posixpath.join(home, raw)
    if (len(raw) > 400 or '\x00' in raw or '\\' in raw or
            any(ord(c) < 32 or ord(c) == 127 for c in raw)):
        raise RemoteError('Linux 上传路径含不安全字符或长度过大')
    if not raw.startswith(home + '/'):
        raise RemoteError(f'上传根目录只能位于当前 SSH 用户家目录 {home} 下')
    rel = raw[len(home) + 1:]
    parts = rel.split('/')
    if (not 1 <= len(parts) <= 10 or any(
            part in ('', '.', '..') or
            not REMOTE_SEGMENT_RE.fullmatch(part) or
            part.endswith((' ', '.')) or
            part.casefold() in REMOTE_DENIED_DIRS
            for part in parts)):
        raise RemoteError('上传路径不安全，或指向保留的旧工程目录（例如 adder/ref）；请换一个独立目录')
    return posixpath.join(home, *parts)


PROJECT_NAME_RE = re.compile(r'^[\w][\w-]{0,63}$', re.UNICODE)
PROJECT_MARKER = '.eda_agent_project.json'


def _checked_project_name(name: str) -> str:
    if not isinstance(name, str):
        raise RemoteError('工程名称必须是文字')
    name = name.strip()
    if not PROJECT_NAME_RE.fullmatch(name) or name.casefold() in REMOTE_DENIED_DIRS:
        raise RemoteError('工程名称只能包含汉字、字母、数字、下划线和短横线（最长64字），不可使用 adder/ref 等保留名称')
    return name


def _read_project_marker(sftp, marker_path: str) -> dict:
    try:
        info = sftp.lstat(marker_path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
            raise RemoteError('工程身份标记不是普通的小文件，拒绝接管已有目录')
        with sftp.open(marker_path, 'rb') as handle:
            return json.loads(handle.read(4097).decode('utf-8'))
    except OSError as exc:
        raise RemoteError(f'无法验证现有工程目录身份：{marker_path}：{exc}') from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise RemoteError('已有工程的身份标记格式损坏，拒绝继续') from exc


def _ensure_project(sftp, chat_id: str, remote_base: str, project_name: str) -> str:
    """Create/reopen only a chat-owned project; reject unmarked pre-existing projects."""
    if not re.fullmatch(r'[0-9a-f]{32}', chat_id):
        raise RemoteError('非法聊天 ID')
    home = sftp.normalize('.')
    if not home.startswith('/') or home == '/':
        raise RemoteError('无法安全确定 Linux 普通用户家目录')
    base = _remote_base_path(home, remote_base)
    project_name = _checked_project_name(project_name)
    parent = home
    for component in base[len(home)+1:].split('/'):
        parent = posixpath.join(parent, component)
        _ensure_shared_dir(sftp, parent)
    project = posixpath.join(base, project_name)
    marker_path = posixpath.join(project, PROJECT_MARKER)
    if _lstat_dir(sftp, project):
        marker = _read_project_marker(sftp, marker_path)
        if marker.get('format') != 'eda-agent-v8.2' or marker.get('chat_id') != chat_id:
            raise RemoteError('目标工程目录已存在，且不是当前对话创建的工程。为保护旧文件，请换一个工程名称')
    else:
        _create_new_dir(sftp, project)
        marker = {'format': 'eda-agent-v8.2', 'chat_id': chat_id,
                  'created_at': datetime.now().isoformat(timespec='seconds')}
        # Project created by us and marker is the first file written to it.
        with sftp.open(marker_path, 'wb') as f:
            f.write(json.dumps(marker, ensure_ascii=False).encode('utf-8'))
    _ensure_shared_dir(sftp, posixpath.join(project, 'runs'))
    _ensure_shared_dir(sftp, posixpath.join(project, 'inputs'))
    _ensure_shared_dir(sftp, posixpath.join(project, 'generated'))
    return project


def _next_named_run(sftp, project: str, mode: str) -> tuple[str, str]:
    """Atomic mkdir of sequential vcs_001/upload_001 etc, no existing run touched."""
    prefix = 'vcs' if mode == 'vcs' else 'upload'
    parent = posixpath.join(project, 'runs')
    for n in range(1, 10000):
        label = f'{prefix}_{n:03d}'
        path = posixpath.join(parent, label)
        if _lstat_dir(sftp, path):
            continue
        try:
            sftp.mkdir(path, mode=0o700)
            return label, path
        except OSError as exc:
            # Another concurrent run may create the same name. If so, retry.
            if _lstat_dir(sftp, path):
                continue
            raise RemoteError(f'无法创建运行目录 {path}：{exc}') from exc
    raise RemoteError('当前项目运行目录太多，请整理后使用新工程名称')


def _sftp_upload(sftp, files: list[tuple[str, Path]], target: str) -> None:
    made: set[str] = set()
    for rel, local in files:
        segments = rel.split('/')
        parent = target
        for segment in segments[:-1]:
            parent = posixpath.join(parent, segment)
            if parent not in made:
                _ensure_shared_dir(sftp, parent)
                made.add(parent)
        remote = posixpath.join(target, *segments)
        # Paramiko does NOT treat 'xb' as writable: x=exclusive creation, not w=write.
        # In this freshly allocated, mode-0700 UUID run folder, verify nonexistence
        # before using 'wb'. This is compatible with old OpenSSH SFTP implementations.
        try:
            sftp.lstat(remote)
        except OSError as exc:
            if getattr(exc, 'errno', None) != 2:
                raise RemoteError(f'远程目标文件状态检查失败：{remote}：{exc}') from exc
        else:
            raise RemoteError(f'远程目标文件已存在，拒绝覆盖：{remote}')
        try:
            with local.open('rb') as src, sftp.open(remote, 'wb') as dst:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    dst.write(chunk)
                dst.flush()
            remote_size = sftp.stat(remote).st_size
            if remote_size != local.stat().st_size:
                raise RemoteError(f'远程文件大小校验失败：{rel}，本地 {local.stat().st_size} 字节，远程 {remote_size} 字节')
        except OSError as exc:
            raise RemoteError(f'SFTP 上传失败：{rel} → {remote}：{exc}') from exc


def _read_remote_log(sftp, name: str, folder: str) -> str:
    dest = posixpath.join(folder, name)
    try:
        info = sftp.lstat(dest)
        if not stat.S_ISREG(info.st_mode):
            return '[日志文件不是普通文件]'
        with sftp.open(dest, 'rb') as f:
            raw = f.read(MAX_LOG_BYTES + 1)
            if len(raw) > MAX_LOG_BYTES:
                return raw[:MAX_LOG_BYTES].decode('utf-8', 'replace') + '\n[LOG TRUNCATED]\n'
            return raw.decode('utf-8', 'replace')
    except OSError as e:
        return f'[未能读取 {name}：{e}]'


def _sim_result(exit_code: int, log: str) -> str:
    if exit_code != 0:
        return 'failed'
    if re.search(r'(?im)^\s*(?:\[?FAIL(?:ED|URE)?\]?\b|TEST[_ ]FAIL\b|UVM_FATAL\b|\*\*\s*ERROR\s*\*\*)', log):
        return 'failed'
    if re.search(r'(?im)^\s*(?:\[?PASS(?:ED)?\]?\b|TEST[_ ]PASS(?:ED)?\b)', log):
        return 'passed_by_marker'
    return 'finished_unverified'


def _parse_coverage(text: str) -> dict[str, Any]:
    """解析 urg 生成的 dashboard.txt，取 Total Coverage Summary 那一行。

    形如：
        SCORE  LINE   COND   TOGGLE FSM    BRANCH
         88.53  90.14 --      95.45 --      80.00
    缺失的指标在 urg 输出里是 '--'，统一记为 None。
    """
    m = re.search(
        r'Total Coverage Summary\s*\n\s*SCORE\s+LINE\s+COND\s+TOGGLE\s+FSM\s+BRANCH\s*\n\s*(.+)',
        text,
    )
    if not m:
        return {}
    keys = ['score', 'line', 'cond', 'toggle', 'fsm', 'branch']
    out: dict[str, Any] = {}
    for key, cell in zip(keys, m.group(1).split()):
        out[key] = None if cell in {'--', '-'} else float(cell)
    return out


def _validate_tb(top: str, manifest: dict[str, Any]):
    if not NAME_RE.fullmatch(top):
        raise RemoteError('Testbench 顶层模块名不合法')
    if top not in manifest['modules']:
        raise RemoteError(f'Testbench 顶层 {top} 不在工程实际模块列表里；请检查是否保存了文件')


def _safe_local_run_dir(workspace: Path, run_id: str) -> Path:
    root = workspace.resolve(strict=True)
    if not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise RemoteError('本地运行 ID 不合法')
    base = root / 'remote_runs'
    if base.is_symlink() or not base.resolve().is_relative_to(root):
        raise RemoteError('本地 remote_runs 目录不安全')
    base.mkdir(exist_ok=True)
    target = base / run_id
    target.mkdir(mode=0o700, exist_ok=False)
    return target


def _local_write(folder: Path, name: str, text: str) -> None:
    with (folder / name).open('x', encoding='utf-8', newline='\n') as f:
        f.write(text)


def _sync_project_latest(sftp, files: list[tuple[str, Path]], project: str, label: str) -> dict[str, int]:
    """Mirror approved local sources for convenient browsing in project/inputs and project/generated.

    Existing source bytes are first backed up to history/<runlabel>/<original path>,
    and the immutable per-run src snapshot has already been written. No remote
    deletion, no writes outside this chat-owned project. Source updates are a
    conscious user-triggered upload operation, not an LLM action.
    """
    changed, unchanged, created = 0, 0, 0
    for rel, local in files:
        path = posixpath.join(project, *rel.split('/'))
        parent = project
        for component in rel.split('/')[:-1]:
            parent = posixpath.join(parent, component)
            _ensure_shared_dir(sftp, parent)
        current_bytes = None
        try:
            info = sftp.lstat(path)
        except OSError as exc:
            if getattr(exc, 'errno', None) != 2:
                raise RemoteError(f'无法读取当前工程文件状态 {path}：{exc}') from exc
        else:
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                raise RemoteError(f'当前工程文件不是可管理的普通文件：{path}')
            with sftp.open(path, 'rb') as src:
                current_bytes = src.read(MAX_FILE_BYTES + 1)
        new_bytes = local.read_bytes()
        if current_bytes == new_bytes:
            unchanged += 1
            continue
        if current_bytes is not None:
            backup_root = posixpath.join(project, 'history', label)
            backup_parent = backup_root
            _ensure_shared_dir(sftp, posixpath.join(project, 'history'))
            _ensure_shared_dir(sftp, backup_root)
            for component in rel.split('/')[:-1]:
                backup_parent = posixpath.join(backup_parent, component)
                _ensure_shared_dir(sftp, backup_parent)
            backup = posixpath.join(backup_root, *rel.split('/'))
            try:
                sftp.lstat(backup)
            except OSError as exc:
                if getattr(exc, 'errno', None) != 2:
                    raise RemoteError(f'检查备份文件失败：{exc}') from exc
            else:
                raise RemoteError(f'备份文件意外已存在：{backup}')
            with sftp.open(backup, 'wb') as dst:
                dst.write(current_bytes)
                dst.flush()
            if sftp.stat(backup).st_size != len(current_bytes):
                raise RemoteError(f'备份大小不一致：{backup}')
            changed += 1
        else:
            created += 1
        # Stage a fresh file first; only atomically replace project-owned latest
        # after the backup and the immutable run snapshot have been stored.
        temp = path + '.stage_' + label
        try:
            sftp.lstat(temp)
        except OSError as exc:
            if getattr(exc, 'errno', None) != 2:
                raise RemoteError(f'远程临时文件状态无法确认：{temp}') from exc
        else:
            raise RemoteError(f'发现意外的临时文件：{temp}')
        with sftp.open(temp, 'wb') as dst:
            dst.write(new_bytes)
            dst.flush()
        if sftp.stat(temp).st_size != len(new_bytes):
            raise RemoteError(f'更新源文件大小验证失败：{rel}')
        if current_bytes is None:
            # A new destination must not already exist.
            try:
                sftp.lstat(path)
            except OSError as exc:
                if getattr(exc, 'errno', None) != 2:
                    raise RemoteError(f'更新目标状态不明：{rel}：{exc}') from exc
            else:
                raise RemoteError(f'同步时目标意外出现：{rel}')
            sftp.rename(temp, path)
        else:
            try:
                # OpenSSH SFTP extension; keeps latest-version replacement atomic.
                sftp.posix_rename(temp, path)
            except (OSError, AttributeError):
                # Some older SFTP servers lack posix-rename. We already stored
                # an immutable run snapshot AND the previous source under history/.
                # Fall back to a backed-up replacement, never delete anything.
                try:
                    with sftp.open(path, 'wb') as dst:
                        dst.write(new_bytes)
                        dst.flush()
                except OSError as exc:
                    # Backup remains available even if this recovery fails.
                    try:
                        with sftp.open(path, 'wb') as dst:
                            dst.write(current_bytes)
                            dst.flush()
                    except OSError:
                        pass
                    raise RemoteError(f'同步当前版本失败（历史备份仍保留）：{rel}：{exc}') from exc
                # temp file is never executed. Preserve it if cleanup unavailable.
                try:
                    sftp.remove(temp)
                except OSError:
                    pass
        with sftp.open(path, 'rb') as verify:
            data = verify.read(MAX_FILE_BYTES + 1)
        if hashlib.sha256(data).digest() != hashlib.sha256(new_bytes).digest():
            raise RemoteError(f'远程当前版本内容校验失败：{rel}（快照与历史备份均已保留）')
    return {'created': created, 'updated_with_backup': changed, 'unchanged': unchanged}


def remote_job(cfg: SSHSettings, workspace: Path, chat_id: str,
               mode: str = 'upload', tb_top: str = '',
               remote_base: str = '~/Desktop/EDA_Projects',
               project_name: str = 'EDA_Demo') -> dict[str, Any]:
    """User-triggered upload or VCS; project is stable and each run is immutable.

    Never executes model-authored .sh/.tcl/Makefile. SSH commands use fixed templates.
    This API deliberately does not support free-form remote commands.
    """
    if mode not in {'upload', 'vcs'}:
        raise RemoteError('不支持的远程任务类型')
    _checked_project_name(project_name)
    files = local_source_files(workspace)
    manifest: dict[str, Any] | None = None
    if mode == 'vcs':
        manifest = source_manifest(files)
        _validate_tb(tb_top, manifest)
    run_id = uuid4().hex  # local metadata identity only; never appears in Linux path
    ssh = ssh_connect(cfg)
    sftp = None
    result: dict[str, Any] = {'run_id': run_id, 'mode': mode, 'file_count': len(files),
                              'when': datetime.now().isoformat(timespec='seconds')}
    try:
        sftp = ssh.open_sftp()
        project = _ensure_project(sftp, chat_id, remote_base, project_name)
        label, run_dir = _next_named_run(sftp, project, mode)
        src_dir = posixpath.join(run_dir, 'src')
        _create_new_dir(sftp, src_dir)
        _sftp_upload(sftp, files, src_dir)
        snapshot_manifest = {
            'format': 'eda-agent-snapshot-v1', 'chat_id': chat_id,
            'project_name': _checked_project_name(project_name),
            'label': label, 'created_at': result['when'],
            'files_sha256': {rel: hashlib.sha256(local.read_bytes()).hexdigest()
                             for rel, local in files},
        }
        with sftp.open(posixpath.join(run_dir, 'snapshot_manifest.json'), 'wb') as marker:
            marker.write(json.dumps(snapshot_manifest, ensure_ascii=False, indent=2).encode('utf-8'))
        result.update(project_directory=project, remote_directory=run_dir,
                      source_snapshot=src_dir, run_label=label, upload_ok=True,
                      status='uploaded')
        if mode == 'vcs' and manifest is not None:
            build_dir = posixpath.join(run_dir, 'build')
            _create_new_dir(sftp, build_dir)
            q = shlex.quote
            relsrc = manifest['sources']
            include_args = ['+incdir+' + d for d in manifest['incdirs'] if d]
            # run from src/ so v7 generated/rtl and inputs/ paths still work.
            args = [VCS_BINARY, '-full64', '-sverilog', '-timescale=1ns/1ps']
            if COVERAGE_ENABLED:
                args += ['-cm', COVERAGE_METRICS, '-cm_dir', '../build/cov.vdb']
            args += ['-top', tb_top, '-o', '../build/simv'] + include_args + relsrc
            compile_cmd = (f'cd {q(src_dir)} && timeout {COMPILE_TIMEOUT}s '
                           + ' '.join(q(a) for a in args)
                           + ' > ../build/vcs_compile.log 2>&1')
            code, _, _ = exec_checked(ssh, compile_cmd, timeout_seconds=COMPILE_TIMEOUT + 25)
            c_log = _read_remote_log(sftp, 'vcs_compile.log', build_dir)
            result.update(compile_exit_code=code, compile_log=c_log,
                          compile_command=' '.join(q(a) for a in args),
                          sources=relsrc, excluded_sources=manifest['excluded'])
            if code != 0:
                result['status'] = 'compile_failed'
            else:
                sim_flags = (f'-cm {COVERAGE_METRICS} -cm_dir ../build/cov.vdb ' if COVERAGE_ENABLED else '')
                sim_cmd = (f'cd {q(src_dir)} && timeout {SIM_TIMEOUT}s '
                           f'../build/simv {sim_flags}'
                           '> ../build/vcs_sim.log 2>&1')
                exit_code, _, _ = exec_checked(ssh, sim_cmd, timeout_seconds=SIM_TIMEOUT + 25)
                sim_log = _read_remote_log(sftp, 'vcs_sim.log', build_dir)
                result.update(sim_exit_code=exit_code, sim_log=sim_log,
                              status=_sim_result(exit_code, sim_log))
                # 覆盖率是附加信息：失败不影响本轮判定，只记录原因。
                if COVERAGE_ENABLED:
                    try:
                        urg_cmd = (f'cd {q(src_dir)} && timeout {COVERAGE_TIMEOUT}s {URG_BINARY} '
                                   '-dir ../build/cov.vdb -format text -report ../build/covReport '
                                   '> ../build/urg.log 2>&1')
                        urg_code, _, _ = exec_checked(ssh, urg_cmd, timeout_seconds=COVERAGE_TIMEOUT + 30)
                        cov_dashboard = _read_remote_log(sftp, 'covReport/dashboard.txt', build_dir)
                        result['coverage'] = _parse_coverage(cov_dashboard)
                        result['coverage_exit_code'] = urg_code
                        if result['coverage']:
                            result['coverage_text'] = cov_dashboard
                    except (RemoteError, OSError) as exc:
                        result['coverage_error'] = str(exc)
        # Project root also shows the latest approved sources for easier manual browsing;
        # old copies are retained in history/<label> and immutable run snapshots.
        try:
            result['sync'] = _sync_project_latest(sftp, files, project, label)
        except (RemoteError, OSError) as exc:
            result['sync_error'] = str(exc)
        local_dir = _safe_local_run_dir(workspace, run_id)
        if 'compile_log' in result:
            _local_write(local_dir, 'vcs_compile.log', result['compile_log'])
        if 'sim_log' in result:
            _local_write(local_dir, 'vcs_sim.log', result['sim_log'])
        if result.get('coverage_text'):
            _local_write(local_dir, 'coverage_dashboard.txt', result['coverage_text'])
        summary = {k: v for k, v in result.items()
                   if k not in {'compile_log', 'sim_log', 'coverage_text'}}
        summary_json = json.dumps(summary, ensure_ascii=False, indent=2)
        _local_write(local_dir, 'run_summary.json', summary_json)
        try:
            with sftp.open(posixpath.join(run_dir, 'run_summary.json'), 'wb') as marker:
                marker.write(summary_json.encode('utf-8'))
        except OSError as exc:
            result['summary_upload_warning'] = f'远程汇总文件保存失败（本地报告已保留）：{exc}'
        result['local_directory'] = str(local_dir)
        return result
    finally:
        if sftp is not None:
            sftp.close()
        ssh.close()
