# -*- coding: utf-8 -*-
"""Capture the guest's real EDA display; never send any input events."""
from __future__ import with_statement
import hashlib
import json
import os
import struct
import subprocess
import sys
import time

target = sys.argv[1]
if os.path.exists(target):
    raise ValueError('Refusing to replace an existing capture')
os.environ['DISPLAY'] = ':0'
import gtk
root = gtk.gdk.get_default_root_window()
geometry = root.get_geometry()
width, height = geometry[2], geometry[3]
x, y = 0, 0
window_title = sys.argv[2] if len(sys.argv) > 2 else None
if window_title:
    found = None
    for attempt in range(20):
        candidates = list(root.get_children())
        for depth in range(3):
            children = []
            for window in candidates[:200]:
                try:
                    if window_title in (window.get_name() or ''):
                        found = window
                        break
                    children.extend(window.get_children())
                except Exception:
                    pass
            if found is not None:
                break
            candidates = children
        if found is not None:
            break
        time.sleep(0.2)
    if found is None:
        raise ValueError('Requested report window was not found')
    box = found.get_frame_extents()
    x, y, width, height = box.x, box.y, box.width, box.height
    time.sleep(0.4)
pixels = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, width, height)
pixels.get_from_drawable(root, root.get_colormap(), x, y, 0, 0, width, height)
pixels.save(target, 'png')
method = 'GTK GDK root-window capture'
with open(target, 'rb') as handle:
    data = handle.read()
width, height = struct.unpack('>II', data[16:24])
metadata = {'method': method, 'display': ':0', 'input_events_sent': False,
            'window_title': window_title, 'capture_bounds': [x, y, width, height],
            'width': width, 'height': height, 'captured_epoch': time.time(),
            'sha256': hashlib.sha256(data).hexdigest()}
with open(target + '.json', 'w') as handle:
    json.dump(metadata, handle, sort_keys=True, indent=2)
print(json.dumps(metadata, sort_keys=True))
