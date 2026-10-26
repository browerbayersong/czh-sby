"""Keep one interactive SSH login for this local backend task; credentials never leave memory.

The user starts this process in PowerShell and enters their own password. Requests
and results are ordinary files inside this task's queue, with no listening port,
new login key, scheduled task, or background installation. Ctrl+C closes it.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import shlex
import stat
import time
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from dotenv import load_dotenv

from eda_remote_v8 import (
    RemoteError, SSHSettings, _create_new_dir, _ensure_project, _sftp_upload,
    local_source_files, ssh_connect,
)
from backend_transport import connection_deadline, exec_bounded as exec_checked, open_sftp_bounded

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE = ROOT / 'designs/counter_backend'
TOOL_PATHS = {
    'dc': '/opt/Synopsys/Synplify2015/bin/dc_shell',
    'icc': '/opt/Synopsys/ICC2016/bin/icc_shell',
    'pt': '/opt/Synopsys/PrimeTime2015/bin/pt_shell',
    'vcs': '/opt/Synopsys/VCS2014/bin/vcs',
}
DENIED = {'.ssh', '.mozilla', '.config', '.gnome2', '.gconf', '.bash_history', '.env'}


def remote_path(value: str) -> str:
    path = PurePosixPath(value)
    if not path.is_absolute() or '..' in path.parts or any(p in DENIED for p in path.parts):
        raise ValueError('远端路径必须是非私密的绝对路径')
    if re.search(r'(?i)(license|passwd|shadow|private|authorized_keys|id_rsa|id_ed25519)', value):
        raise ValueError('不读取认证或许可证内容')
    return str(path)


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts or any(p in DENIED for p in path.parts):
        raise ValueError('结果路径必须位于本次运行目录内')
    return str(path)


def read_remote(sftp, name: str, limit=4_000_000) -> bytes:
    info = sftp.lstat(name)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError('只读取大小受限的普通文件')
    with sftp.open(name, 'rb') as handle:
        return handle.read(limit + 1)


class BackendSession:
    def __init__(self, cfg: SSHSettings, workspace: Path):
        self.cfg = cfg
        self.workspace = workspace
        self.ssh = ssh_connect(cfg)
        self.ssh.get_transport().set_keepalive(20)
        self.runs: dict[str, dict] = {}
        for saved in (workspace / 'remote_runs').glob('*/run_summary.json'):
            record = json.loads(saved.read_text(encoding='utf-8'))
            label = record.get('run_label', '')
            expected = '/home/IC/Desktop/EDA_Projects/counter_backend/runs/' + label
            if (re.fullmatch(r'upload_(?:[0-9]{3,4}|[0-9]{8}_[0-9]{6}_[0-9a-f]{8})', label)
                    and record.get('remote_directory') == expected
                    and record.get('source_snapshot') == expected + '/src'
                    and record.get('upload_ok')):
                self.runs[label] = record

    def open_sftp(self):
        return open_sftp_bounded(self.ssh)

    def start_snapshot(self):
        """Create a unique immutable run without probing any old run directory."""
        files = local_source_files(self.workspace)
        run_id = uuid4().hex
        stamp = datetime.now()
        label = 'upload_' + stamp.strftime('%Y%m%d_%H%M%S_') + run_id[:8]
        record = {'run_id': run_id, 'run_label': label, 'mode': 'upload',
                  'when': stamp.isoformat(timespec='seconds'), 'file_count': len(files),
                  'upload_ok': False, 'status': 'uploading'}
        folder = self.workspace / 'remote_runs' / run_id
        folder.mkdir(parents=True, exist_ok=False)
        summary = folder / 'run_summary.json'
        sftp = self.open_sftp()
        try:
            with connection_deadline(self.ssh, 180, '后端源码快照上传'):
                project = _ensure_project(sftp, 'f' * 32,
                                          '/home/IC/Desktop/EDA_Projects', 'counter_backend')
                directory = project + '/runs/' + label
                src = directory + '/src'
                record.update(project_directory=project, remote_directory=directory,
                              source_snapshot=src)
                _create_new_dir(sftp, directory)
                _create_new_dir(sftp, src)
                _create_new_dir(sftp, directory + '/build')
                _sftp_upload(sftp, files, src)
                hashes = {}
                for rel, path in files:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if hashlib.sha256(read_remote(sftp, src + '/' + rel)).hexdigest() != digest:
                        raise RemoteError('快照回读校验失败：' + rel)
                    hashes[rel] = digest
                manifest = {'format': 'eda-agent-snapshot-v1', 'chat_id': 'f' * 32,
                            'project_name': 'counter_backend', 'label': label,
                            'created_at': record['when'], 'files_sha256': hashes}
                with sftp.open(directory + '/snapshot_manifest.json', 'wb') as handle:
                    handle.write(json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
                record.update(upload_ok=True, status='uploaded', local_directory=str(folder))
                text = json.dumps(record, ensure_ascii=False, indent=2)
                summary.write_text(text, encoding='utf-8')
                with sftp.open(directory + '/run_summary.json', 'wb') as handle:
                    handle.write(text.encode('utf-8'))
            self.runs[label] = record
            return record
        except Exception as exc:
            record.update(upload_ok=False, status='upload_failed', error=f'{type(exc).__name__}: {exc}')
            summary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            raise
        finally:
            sftp.close()

    def rescue_run(self, label: str, output: Path) -> dict:
        """Fetch known run logs first; never enumerate /proc or assume ICC stopped."""
        run = self.runs[label]
        result = {'target': run['remote_directory'], 'stop_attempted': False,
                  'icc_stop_status': 'unconfirmed', 'files': []}
        sftp = self.open_sftp()
        try:
            for rel in ('build/icc.log', 'build/icc/library_check.rpt', 'build/icc/units.rpt',
                        'build/icc/rc_model.txt', 'build/icc/routing_drc.rpt'):
                try:
                    name = run['remote_directory'] + '/' + rel
                    info = sftp.lstat(name)
                    if not stat.S_ISREG(info.st_mode):
                        raise ValueError('Result is not a regular file')
                    with sftp.open(name, 'rb') as handle:
                        data = handle.read(1_000_000)
                    target = output / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    result['files'].append({'path': rel, 'bytes': len(data), 'total_size': info.st_size})
                except (OSError, ValueError) as exc:
                    result['files'].append({'path': rel, 'error': str(exc)})
        finally:
            sftp.close()
        (output / 'rescue_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result

    def perform(self, job: dict, output: Path) -> dict:
        action = job['action']
        if action == 'find_files' or (action == 'inspect' and job.get('kind') == 'process_library_search'):
            raise ValueError('递归文件搜索已禁用；仅允许读取已确定的目录或文件')
        if action == 'finish':
            return {'finished': True}
        transport = self.ssh.get_transport()
        if not transport or not transport.is_active():
            self.ssh.close()
            print('SSH 连接已断开，正在重新连接…', flush=True)
            self.ssh = ssh_connect(self.cfg)
            self.ssh.get_transport().set_keepalive(20)
        if action == 'inspect':
            kind = job['kind']
            inspections = {
                'kernel_tail': 'dmesg | tail -n 60',
                'baseline': '/bin/uname -r; /usr/bin/python --version; '
                            '/usr/bin/uptime; free -m; '
                            'df -Pk /home/IC/Desktop/EDA_Projects; /sbin/ifconfig eth0',
                'library_roots': 'ls -ld /* /home/IC/Desktop/* /home/IC/* 2>/dev/null | head -n 100; '
                                 'sed -n "1,100p" /home/IC/.synopsys_dc.setup; '
                                 'ls -ld /mnt/hgfs /media/* /mnt/* 2>/dev/null',
                'health': 'uptime; free -m; /sbin/ifconfig eth0; '
                          'ps -C dhclient -o pid,etime,args; '
                          'cat /etc/sysconfig/network-scripts/ifcfg-eth0 2>/dev/null',
                'display': 'printf "DISPLAY=%s\\n" "$DISPLAY"; command -v vncserver; command -v xwd; '
                           'command -v xdotool; command -v import; ls -ld /tmp/.X11-unix 2>/dev/null',
                'activity_tools': 'command -v vcd2saif; ls /opt/Synopsys/VCS2014/bin/*saif* '
                                  '/opt/Synopsys/PrimeTime2015/bin/*saif* 2>/dev/null',
            }
            if kind not in inspections:
                raise ValueError('未定义的检查类型')
            code, out, err = exec_checked(self.ssh, inspections[kind],
                                          timeout_seconds=20 if kind in {'baseline', 'kernel_tail'} else 85)
            (output / 'stdout.txt').write_text(out, encoding='utf-8')
            (output / 'stderr.txt').write_text(err, encoding='utf-8')
            return {'exit_code': code, 'kind': kind}
        if action == 'read_text':
            name = remote_path(job['path'])
            if not (name.endswith(('.tcl', '.tf', '.map', '.lib', '.txt', '.sdc', '.setup', '.itf', '.rpt', '.log'))):
                raise ValueError('只读取 EDA 配置、文本库或工具报告')
            sftp = self.open_sftp()
            try:
                info = sftp.lstat(name)
                prefix_only = bool(job.get('prefix_only', False))
                if prefix_only:
                    limit = int(job.get('limit_bytes', 64000))
                    if not stat.S_ISREG(info.st_mode) or not 1024 <= limit <= 1_000_000:
                        raise ValueError('只允许读取大小受限的普通文本文件片段')
                    with sftp.open(name, 'rb') as handle:
                        data = handle.read(limit)
                else:
                    data = read_remote(sftp, name)
                (output / 'content.txt').write_bytes(data)
                return {'path': name, 'bytes': len(data), 'total_size': info.st_size,
                        'truncated': len(data) < info.st_size,
                        'sha256': hashlib.sha256(data).hexdigest()}
            finally:
                sftp.close()
        if action == 'stat_paths':
            # Metadata only: inspect explicitly supplied paths, never recurse
            # through libraries or load EDA tools just to establish existence.
            values = job.get('paths')
            if not isinstance(values, list) or not 1 <= len(values) <= 24:
                raise ValueError('一次只检查 1 至 24 个明确路径')
            names = [remote_path(value) for value in values]
            entries = []
            with connection_deadline(self.ssh, 25, '文件存在性检查'):
                sftp = self.open_sftp()
                try:
                    for name in names:
                        try:
                            info = sftp.lstat(name)
                            entries.append({'path': name, 'exists': True,
                                'kind': 'directory' if stat.S_ISDIR(info.st_mode) else
                                        'file' if stat.S_ISREG(info.st_mode) else
                                        'symlink' if stat.S_ISLNK(info.st_mode) else 'other',
                                'bytes': info.st_size, 'mtime_epoch': info.st_mtime,
                                'mode': oct(info.st_mode)})
                        except OSError as exc:
                            entries.append({'path': name, 'exists': False if exc.errno == 2 else None,
                                            'error': str(exc), 'errno': exc.errno})
                finally:
                    sftp.close()
            return {'entries': entries, 'read_only': True, 'file_contents_read': False}
        if action == 'list_directory':
            name = remote_path(job['path'])
            sftp = self.open_sftp()
            try:
                entries = [{'name': x.filename, 'size': x.st_size, 'mode': oct(x.st_mode)}
                           for x in sftp.listdir_attr(name)][:600]
                return {'path': name, 'entries': entries}
            finally:
                sftp.close()
        if action == 'start_run':
            return self.start_snapshot()
        if action == 'control_tool':
            tool, operation = job['tool'], job['operation']
            if tool not in {'dc', 'icc', 'pt'} or operation not in {'diagnose', 'stop'}:
                raise ValueError('只诊断或停止本次记录中的工具')
            run = self.runs[job['run']]
            program = Path(__file__).with_name('backend_guest_control.py').read_text(encoding='utf-8')
            command = 'timeout 12s /usr/bin/python -c ' + shlex.quote(program) + ' ' + ' '.join(
                shlex.quote(x) for x in (run['source_snapshot'], tool, operation))
            code, out, err = exec_checked(self.ssh, command, timeout_seconds=20)
            (output / 'stdout.txt').write_text(out, encoding='utf-8')
            (output / 'stderr.txt').write_text(err, encoding='utf-8')
            return {'run': job['run'], 'tool': tool, 'operation': operation,
                    'exit_code': code, 'stdout': out, 'stderr': err}
        if action == 'check_runner':
            run = self.runs[job['run']]
            check = ('import sys; p="generated/scripts/backend_tool_runner.py"; '
                     'compile(open(p,"rb").read(),p,"exec"); '
                     'print("RUNNER_SYNTAX_OK Python " + sys.version.split()[0])')
            command = (f"cd {shlex.quote(run['source_snapshot'])} && /usr/bin/python -c "
                       + shlex.quote(check))
            code, out, err = exec_checked(self.ssh, command, timeout_seconds=15)
            return {'run': job['run'], 'exit_code': code, 'stdout': out, 'stderr': err}
        if action in {'run_tool', 'launch_tool'}:
            tool = job['tool']
            if tool not in {'dc', 'icc', 'pt'}:
                raise ValueError('工具未启用')
            run = self.runs[job['run']]
            script = relative_path(job['script'])
            if not script.startswith('generated/') or not script.endswith('.tcl'):
                raise ValueError('只执行本次源码快照中的 Tcl')
            seconds = int(job.get('timeout', 600))
            if not 30 <= seconds <= 1800:
                raise ValueError('工具超时超出范围')
            if action == 'launch_tool':
                command = (f"cd {shlex.quote(run['source_snapshot'])} && /usr/bin/python "
                           f"generated/scripts/backend_tool_runner.py --tool {tool} "
                           f"--script {shlex.quote(script)} --timeout {seconds}")
                code, out, err = exec_checked(self.ssh, command, timeout_seconds=20)
                if code != 0:
                    raise RemoteError(f'后端工具启动请求失败：{out} {err}')
                return {'exit_code': code, 'tool': tool, 'run': job['run'],
                        'stdout': out, 'stderr': err, 'stage_passed': False,
                        'note': '启动请求已返回；须回收 status、日志和报告后判定实际结果'}
            command = (f"cd {shlex.quote(run['source_snapshot'])} && timeout {seconds}s "
                       f"{shlex.quote(TOOL_PATHS[tool])} -f {shlex.quote(script)} "
                       f"> ../build/{tool}.log 2>&1")
            code, out, err = exec_checked(self.ssh, command, timeout_seconds=seconds + 30)
            return {'exit_code': code, 'tool': tool, 'command': command,
                    'stdout': out, 'stderr': err, 'run': job['run']}
        if action == 'run_activity':
            run = self.runs[job['run']]
            sftp = self.open_sftp()
            try:
                _create_new_dir(sftp, run['remote_directory'] + '/build/activity')
            finally:
                sftp.close()
            commands = (
                ('compile', 300, TOOL_PATHS['vcs'] + ' -full64 -sverilog -timescale=1ns/1ps '
                 '-top tb_counter_8bit -o ../build/activity/simv '
                 'generated/rtl/counter_8bit.v generated/tb/tb_counter_8bit.v'),
                ('simulation', 120, '../build/activity/simv'),
                ('conversion', 90, '/opt/Synopsys/Synplify2015/bin/vcd2saif '
                 '-input ../build/activity/counter.vcd -output ../build/activity/counter.saif'),
            )
            results = []
            for stage, seconds, tool_command in commands:
                command = (f"cd {shlex.quote(run['source_snapshot'])} && timeout {seconds}s "
                           f"{tool_command} > ../build/activity/{stage}.log 2>&1")
                code, out, err = exec_checked(self.ssh, command, timeout_seconds=seconds + 30)
                results.append({'stage': stage, 'exit_code': code, 'command': command})
                if code != 0:
                    break
            return {'run': job['run'], 'stages': results,
                    'note': 'Inspect simulation checks and SAIF contents before using activity for power analysis'}
        if action == 'fetch':
            run = self.runs[job['run']]
            sftp = self.open_sftp()
            files = []
            try:
                for rel in job['paths']:
                    rel = relative_path(rel)
                    try:
                        data = read_remote(sftp, run['remote_directory'] + '/' + rel, 30_000_000)
                        target = output / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                        files.append({'path': rel, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
                    except (OSError, ValueError) as exc:
                        files.append({'path': rel, 'error': str(exc)})
                return {'run': job['run'], 'files': files}
            finally:
                sftp.close()
        raise ValueError('未定义的会话任务')


def main() -> int:
    load_dotenv(Path(__file__).with_name('.env'))
    parser = argparse.ArgumentParser(description='后端实验会话：密码仅在本机输入一次并保留于内存')
    parser.add_argument('--host', default=os.getenv('EDA_SSH_HOST', '192.168.142.128'))
    parser.add_argument('--workspace', type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument('--rescue-run', help='先读取指定运行目录内的已知日志，再恢复会话；不遍历进程')
    parser.add_argument('--fresh-session', action='store_true',
                        help='跳过全部已有队列文件，仅处理本次连接之后新建的任务')
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    queue = workspace / 'session_queue'
    queue.mkdir(parents=True, exist_ok=True)
    recovery_old_requests = ({p.name for p in queue.glob('request_*.json')}
                             if args.rescue_run or args.fresh_session else set())
    session_stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    password = getpass.getpass(f'IC@{args.host} 的 SSH 密码（不回显）: ')
    session = BackendSession(SSHSettings(args.host, 'IC', 22, password), workspace)
    if args.rescue_run:
        rescue_folder = workspace / 'rescue_records' / session_stamp
        rescue_folder.mkdir(parents=True, exist_ok=False)
        print('正在读取本次工程的已知 ICC 日志，不遍历目录或进程…', flush=True)
        try:
            rescued = session.rescue_run(args.rescue_run, rescue_folder)
            print(f"日志回收结束，记录数：{len(rescued.get('files', []))}；ICC 停止状态尚未确认。", flush=True)
        except Exception as exc:
            error = {'error': f'{type(exc).__name__}: {exc}', 'icc_stop_status': 'unconfirmed'}
            (rescue_folder / 'rescue_result.json').write_text(json.dumps(error, ensure_ascii=False, indent=2), encoding='utf-8')
            print('日志读取暂未成功，错误已保存；会话继续保持。', flush=True)
            session.ssh.close()
    print('SSH 已连接。请保持此窗口运行；我会继续配置和执行后端实验。Ctrl+C 可结束。', flush=True)
    if recovery_old_requests:
        print('恢复模式：旧的待执行任务已暂停，只接收随后新建的任务。', flush=True)
    (queue / 'session_status.json').write_text(json.dumps(
        {'status': 'connected', 'session': session_stamp, 'host': args.host}, indent=2), encoding='utf-8')
    start = time.monotonic()
    try:
        while time.monotonic() - start < 6 * 3600:
            for request in sorted(queue.glob('request_*.json')):
                if request.name in recovery_old_requests:
                    continue
                job_id = request.stem[len('request_'):]
                target = queue / ('result_' + job_id)
                if target.exists():
                    continue
                target.mkdir()
                try:
                    job = json.loads(request.read_text(encoding='utf-8'))
                    (target / 'request_started.json').write_text(json.dumps({
                        'session': session_stamp, 'action': job['action'],
                        'started_at': datetime.now().isoformat(timespec='seconds'),
                    }, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(f"执行任务 {job_id}: {job['action']}…", flush=True)
                    result = session.perform(job, target)
                    result['status'] = 'completed'
                except Exception as exc:
                    result = {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}
                    # A timed-out exec can leave the old SSH connection unusable.
                    # Subsequent jobs reconnect with the credential still in memory.
                    session.ssh.close()
                (target / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
                print(f"任务 {job_id}: {result['status']}；记录已保存。", flush=True)
                if result.get('finished'):
                    return 0
            time.sleep(0.5)
    except KeyboardInterrupt:
        print('\n会话已结束。')
    finally:
        session.ssh.close()
        password = None
        (queue / 'session_status.json').write_text(json.dumps(
            {'status': 'closed', 'session': session_stamp}), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
