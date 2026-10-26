# -*- coding: utf-8 -*-
"""Python 2.6+ diagnostics for a single recorded tool, never a process scan."""
from __future__ import with_statement
import json
import os
import signal
import stat
import sys


def control(root, tool, operation):
    if tool not in ('icc', 'dc', 'pt') or operation not in ('diagnose', 'stop'):
        raise ValueError('Unsupported recorded-tool operation')
    status_path = os.path.join(root, '..', 'build', tool + '.status.json')
    info = os.lstat(status_path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > 16000:
        raise ValueError('Invalid runner status file')
    with open(status_path) as handle:
        record = json.load(handle)
    if record.get('tool') != tool or not record.get('script', '').startswith(root + '/generated/'):
        raise ValueError('Runner status does not match this source snapshot')
    pid = int(record['tool_pid'])
    if pid < 2:
        raise ValueError('Invalid recorded PID')
    result = {'tool': tool, 'pid': pid, 'operation': operation, 'runner_state': record.get('state')}
    if operation == 'stop':
        with open('/proc/sys/kernel/random/boot_id') as handle:
            boot = handle.read(100).strip()
        if not record.get('boot_id') or record['boot_id'] != boot:
            raise ValueError('Refusing to signal a tool recorded before this boot')
    proc = '/proc/' + str(pid)
    try:
        cwd = os.readlink(proc + '/cwd')
    except OSError:
        result['process_absent_or_inaccessible'] = True
        return result
    if cwd != root:
        raise ValueError('PID no longer belongs to this experiment snapshot')
    with open(proc + '/cmdline', 'rb') as handle:
        command = handle.read(8000)
    if (tool + '_shell').encode('ascii') not in command:
        raise ValueError('PID does not match the recorded EDA tool')
    with open(proc + '/stat') as handle:
        fields = handle.read(8000).rsplit(')', 1)[1].split()
    group = int(fields[2])
    result.update(process_state=fields[0], process_group=group)
    if operation == 'stop':
        if (group != pid or record.get('state') not in ('starting', 'running')
                or not record.get('process_start_ticks')
                or record['process_start_ticks'] != fields[19]):
            raise ValueError('Refusing to signal an unverified process group')
        os.killpg(pid, signal.SIGTERM)
        result['term_requested'] = True
        result['exit_confirmed'] = False
    else:
        with open(proc + '/wchan') as handle:
            result['wait_channel'] = handle.read(256).strip()
        with open(proc + '/status') as handle:
            result['resource_lines'] = [line.strip() for line in handle.read(12000).splitlines()
                                       if line.startswith(('Name:', 'State:', 'VmPeak:', 'VmRSS:', 'Threads:'))]
    return result


if __name__ == '__main__':
    print(json.dumps(control(sys.argv[1], sys.argv[2], sys.argv[3]), sort_keys=True))
