# -*- coding: utf-8 -*-
"""Show exact original report excerpts in a real guest terminal and capture it."""
from __future__ import with_statement
import hashlib
import json
import os
import re
import subprocess
import sys
import time

PROJECT = '/home/IC/Desktop/EDA_Projects/counter_backend/runs/'


def label(path):
    with open(path) as handle:
        value = handle.read(200).strip()
    if not re.match(r'^upload_[0-9]{8}_[0-9]{6}_[0-9a-f]{8}$', value):
        raise ValueError('Invalid recorded report run')
    return value


def report_text(path, mode):
    with open(path, 'rb') as handle:
        data = handle.read(1000000)
    lines = data.decode('utf-8', 'replace').splitlines()
    if mode == 'timing':
        selected = lines[:8]
        for line in lines[8:]:
            if any(word in line for word in ('Startpoint:', 'Endpoint:', 'Path Group:', 'Path Type:',
                                             'data arrival time', 'data required time', 'slack (')):
                selected.append(line)
                if 'slack (' in line:
                    break
    elif mode == 'power':
        selected = lines[:8]
        selected += [line for line in lines if 'Power Units' in line]
        selected += lines[-12:]
    else:
        selected = lines[-19:]
    return '\n'.join(selected), hashlib.sha256(data).hexdigest()


def main():
    os.environ['DISPLAY'] = ':0'
    output = os.path.abspath('../build/report_captures')
    if not os.path.isdir(output):
        os.mkdir(output)
    physical = label('inputs/physical_run.txt')
    pt = label('inputs/pt_run.txt')
    dc = PROJECT + 'upload_002/build/dc/'
    layout = PROJECT + physical + '/build/icc/'
    power = PROJECT + pt + '/build/pt_estimate/'
    cases = [
        ('dc_power', 'DC original power report', dc + 'power.rpt', 'power'),
        ('dc_timing', 'DC original setup timing', dc + 'timing_setup.rpt', 'timing'),
        ('icc_drc', 'ICC DRC report - one residual violation', layout + 'routing_drc.rpt', 'tail'),
        ('icc_lvs', 'ICC original connectivity report', layout + 'lvs.rpt', 'tail'),
        ('pt_power', 'PT statistical wire-load power estimate', power + 'power.rpt', 'power'),
        ('pt_timing', 'PT statistical wire-load timing estimate', power + 'timing_setup.rpt', 'timing'),
    ]
    help_process = subprocess.Popen(['/usr/bin/gnome-terminal', '--help'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    help_text = help_process.communicate()[0]
    manifest = []
    for name, title, source, mode in cases:
        excerpt, digest = report_text(source, mode)
        text_file = os.path.join(output, name + '.txt')
        with open(text_file, 'wb') as handle:
            heading = 'Read-only original report excerpt\n' + title + '\n\n'
            handle.write((heading + excerpt + '\n').encode('utf-8'))
        unique_title = 'EDA evidence ' + name
        command = ['/usr/bin/gnome-terminal', '--disable-factory', '--hide-menubar',
                   '--geometry=105x32+5+5', '--title=' + unique_title]
        if b'--zoom' in help_text:
            command.append('--zoom=1.2')
        command += ['-x', '/bin/bash', '-c', 'cat -- "$1"; sleep 8', 'report_view', text_file]
        window = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(0.9)
        image = os.path.join(output, name + '.png')
        # Old PyGTK does not expose reliable titles for every X11 window.
        # Capture the real root display after opening the report terminal.
        subprocess.check_call(['/usr/bin/python', 'generated/scripts/capture_display.py', image])
        manifest.append({'name': name, 'source': source, 'source_sha256': digest,
                         'image': image, 'content': 'Exact original report lines displayed by gnome-terminal',
                         'input_events_sent': False})
        if window.poll() is None:
            window.terminate()
    with open(os.path.join(output, 'manifest.json'), 'w') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
    print('EDA_ORIGINAL_REPORT_CAPTURES_COMPLETE ' + str(len(manifest)))


if __name__ == '__main__':
    main()
