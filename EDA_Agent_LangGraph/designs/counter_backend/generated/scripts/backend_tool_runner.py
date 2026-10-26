# -*- coding: utf-8 -*-
"""Python 2.6+ runner for one snapshotted EDA stage; no process/directory scan."""
from __future__ import with_statement
import json
import os
import signal
import subprocess
import sys
import time

TOOLS = {
    'dc': '/opt/Synopsys/Synplify2015/bin/dc_shell',
    'icc': '/opt/Synopsys/ICC2016/bin/icc_shell',
    'pt': '/opt/Synopsys/PrimeTime2015/bin/pt_shell',
}


def script_path(root, value):
    if not value.startswith('generated/') or not value.endswith('.tcl'):
        raise ValueError('Only generated Tcl scripts are allowed')
    candidate = os.path.realpath(os.path.join(root, value))
    allowed = os.path.realpath(os.path.join(root, 'generated')) + os.sep
    if not candidate.startswith(allowed) or not os.path.isfile(candidate):
        raise ValueError('Script must remain in the immutable source snapshot')
    return candidate


def write_status(path, record):
    temp = path + '.tmp.' + str(os.getpid())
    with open(temp, 'w') as handle:
        json.dump(record, handle, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.rename(temp, path)


def stop_child_group(child):
    # Only the still-live Popen child started in its own session is authority.
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
        deadline = time.time() + 3
        while child.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
    return child.wait()


def run_stage(tool, script, seconds, build, root):
    status_path = os.path.join(build, tool + '.status.json')
    log_path = os.path.join(build, tool + '.log')
    descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    record = {'tool': tool, 'script': script, 'worker_pid': os.getpid(),
              'started_epoch': time.time(), 'timeout_seconds': seconds,
              'state': 'starting', 'tool_exit_code': None}
    try:
        with open('/proc/sys/kernel/random/boot_id') as handle:
            record['boot_id'] = handle.read(100).strip()
    except IOError:
        record['boot_id'] = None
    child = None
    with os.fdopen(descriptor, 'wb') as log:
        try:
            write_status(status_path, record)
            child = subprocess.Popen([TOOLS[tool], '-f', script], cwd=root,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     close_fds=True, preexec_fn=os.setsid)
            record.update(state='running', tool_pid=child.pid)
            try:
                with open('/proc/' + str(child.pid) + '/stat') as handle:
                    record['process_start_ticks'] = handle.read(8000).rsplit(')', 1)[1].split()[19]
            except IOError:
                record['process_start_ticks'] = None
            write_status(status_path, record)
            deadline = time.time() + seconds
            while child.poll() is None and time.time() < deadline:
                time.sleep(0.25)
            if child.poll() is None:
                record.update(state='timed_out', tool_exit_code=stop_child_group(child))
            else:
                record.update(state='exited', tool_exit_code=child.returncode)
        except BaseException as exc:
            record.update(state='runner_error', error=type(exc).__name__ + ': ' + str(exc))
            if child is not None and child.poll() is None:
                record['tool_exit_code'] = stop_child_group(child)
        finally:
            record['finished_epoch'] = time.time()
            write_status(status_path, record)
    # Code zero still requires a completion marker and report/error checks.
    return record


def main():
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('--tool', choices=sorted(TOOLS), type='choice')
    parser.add_option('--script')
    parser.add_option('--timeout', type='int', default=1200)
    parser.add_option('--worker', action='store_true', default=False)
    options, extra = parser.parse_args()
    if extra or not options.tool or not options.script or not 30 <= options.timeout <= 1800:
        parser.error('A tool, script and bounded timeout are required')
    root = os.path.realpath(os.getcwd())
    script = script_path(root, options.script)
    build = os.path.realpath(os.path.join(root, '..', 'build'))
    if os.path.basename(root) != 'src' or not os.path.isdir(build):
        raise ValueError('Run from a snapshot src directory with its sibling build')
    if options.worker:
        run_stage(options.tool, script, options.timeout, build, root)
        return 0
    claim = os.path.join(build, options.tool + '.launch.json')
    descriptor = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as handle:
        json.dump({'state': 'launch_requested', 'tool': options.tool,
                   'script': script, 'requested_epoch': time.time()}, handle)
    runner = os.path.realpath(__file__)
    with open(os.devnull, 'r+b') as null:
        worker = subprocess.Popen([sys.executable, runner, '--worker', '--tool', options.tool,
                                   '--script', options.script, '--timeout', str(options.timeout)],
                                  cwd=root, stdin=null, stdout=null, stderr=null,
                                  close_fds=True, preexec_fn=os.setsid)
    print(json.dumps({'launch_accepted': True, 'worker_pid': worker.pid,
                      'status_file': 'build/' + options.tool + '.status.json',
                      'stage_passed': False}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
