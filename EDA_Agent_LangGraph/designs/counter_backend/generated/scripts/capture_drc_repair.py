# -*- coding: utf-8 -*-
"""Capture exact DRC report summaries in real guest terminals, no input events."""
from __future__ import with_statement
import hashlib
import json
import os
import subprocess
import time

os.environ['DISPLAY'] = ':0'
out = os.path.abspath('../build/drc_recheck')
baseline = '/home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261025_143839_f96edb1f/build/icc/routing_drc.rpt'
cases = [('before', baseline), ('after', os.path.join(out, 'routing_drc.rpt'))]
manifest = []
for label, source in cases:
    with open(source, 'rb') as f:
        data = f.read()
    lines = data.splitlines()
    start = [i for i, line in enumerate(lines) if 'Verify Summary:' in line][-1]
    excerpt = '\n'.join(lines[start:])
    txt = os.path.join(out, label + '.txt')
    with open(txt, 'wb') as f:
        f.write('Read-only original ICC routing verification report\nCase: '+label+'\n\n'+excerpt+'\n')
    terminal = subprocess.Popen(['/usr/bin/gnome-terminal','--disable-factory','--hide-menubar',
        '--geometry=105x29+5+5','--title=EDA DRC AI '+label,
        '-x','/bin/bash','-c','cat -- "$1"; sleep 6','drc_report',txt])
    time.sleep(1)
    png = os.path.join(out,label+'.png')
    subprocess.check_call(['/usr/bin/python','generated/scripts/capture_display.py',png])
    manifest.append({'source':source,'source_sha256':hashlib.sha256(data).hexdigest(),
        'image':png,'input_events_sent':False,'label':label})
    if terminal.poll() is None:
        terminal.terminate()
with open(os.path.join(out,'capture_manifest.json'),'w') as f:
    json.dump(manifest,f,indent=2,sort_keys=True)
print('EDA_DRC_REPORT_SCREENSHOTS_SAVED')
