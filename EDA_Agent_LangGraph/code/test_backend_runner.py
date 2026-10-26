import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace, ModuleType
from unittest.mock import patch

RUNNER_PATH = Path(__file__).resolve().parent.parent / 'designs/counter_backend/generated/scripts/backend_tool_runner.py'
runner = ModuleType('backend_tool_runner')
runner.__file__ = str(RUNNER_PATH)
exec(compile(RUNNER_PATH.read_bytes(), str(RUNNER_PATH), 'exec'), runner.__dict__)


class BackendRunnerTests(unittest.TestCase):
    def test_script_cannot_escape_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'generated').mkdir()
            (root / 'outside.tcl').write_text('exit', encoding='utf-8')
            with self.assertRaises(ValueError):
                runner.script_path(str(root), 'generated/../outside.tcl')

    def test_existing_tool_log_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'icc.log'
            log.write_text('original run', encoding='utf-8')
            with self.assertRaises(FileExistsError), patch.object(runner.subprocess, 'Popen') as popen:
                runner.run_stage('icc', 'demo.tcl', 30, folder, folder)
            popen.assert_not_called()
            self.assertEqual(log.read_text(encoding='utf-8'), 'original run')

    def test_zero_exit_is_recorded_without_claiming_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            child = SimpleNamespace(pid=12345, poll=lambda: 0, returncode=0)
            # The guest uses POSIX rename semantics; os.replace supplies those
            # semantics for this isolated Windows test of status-file updates.
            with patch.object(runner.subprocess, 'Popen', return_value=child), \
                 patch.object(runner.os, 'rename', side_effect=os.replace), \
                 patch.object(runner.os, 'setsid', create=True):
                result = runner.run_stage('icc', 'demo.tcl', 30, folder, folder)
            self.assertEqual(result['tool_exit_code'], 0)
            self.assertEqual(result['state'], 'exited')
            self.assertNotIn('passed', result)


if __name__ == '__main__':
    unittest.main()
