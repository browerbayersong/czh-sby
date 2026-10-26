import io
import json
import os
import stat
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import backend_guest_control as guest


class RecordedProcessControlTests(unittest.TestCase):
    def invoke(self, boot='current-boot', ticks='1000', cwd='/home/IC/demo/src'):
        root = '/home/IC/demo/src'
        record = {'tool': 'icc', 'script': root + '/generated/run.tcl', 'tool_pid': 123,
                  'state': 'running', 'boot_id': boot, 'process_start_ticks': ticks}
        proc_fields = ['S', '1', '123'] + ['0'] * 16 + ['1000']
        files = {
            os.path.join(root, '..', 'build', 'icc.status.json'): json.dumps(record),
            '/proc/sys/kernel/random/boot_id': 'current-boot',
            '/proc/123/cmdline': b'/opt/Synopsys/ICC2016/bin/icc_shell\x00-f\x00run.tcl',
            '/proc/123/stat': '123 (icc_shell) ' + ' '.join(proc_fields),
        }

        def open_known(path, *args):
            if path not in files:
                self.fail('Unexpected process/file access: ' + path)
            data = files[path]
            return io.BytesIO(data) if isinstance(data, bytes) else io.StringIO(data)

        with patch.object(guest.os, 'lstat', return_value=SimpleNamespace(st_mode=stat.S_IFREG, st_size=1000)), \
             patch.object(guest.os, 'readlink', return_value=cwd), \
             patch.object(guest, 'open', side_effect=open_known, create=True), \
             patch.object(guest.os, 'killpg', create=True) as kill:
            try:
                result = guest.control(root, 'icc', 'stop')
            except ValueError:
                kill.assert_not_called()
                raise
            kill.assert_called_once_with(123, guest.signal.SIGTERM)
            return result

    def test_previous_boot_cannot_be_signalled(self):
        with self.assertRaises(ValueError):
            self.invoke(boot='previous-boot')

    def test_reused_pid_cannot_be_signalled(self):
        with self.assertRaises(ValueError):
            self.invoke(ticks='999')

    def test_other_working_directory_cannot_be_signalled(self):
        with self.assertRaises(ValueError):
            self.invoke(cwd='/home/IC/another-project')

    def test_only_matching_recorded_group_receives_term(self):
        result = self.invoke()
        self.assertTrue(result['term_requested'])
        self.assertFalse(result['exit_confirmed'])


if __name__ == '__main__':
    unittest.main()
