import io
from contextlib import contextmanager
import json
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend_session import BackendSession
from backend_transport import connection_deadline, open_sftp_bounded, exec_bounded
from eda_remote_v8 import RemoteError


class SessionRecoveryTests(unittest.TestCase):
    def test_new_snapshot_does_not_visit_existing_runs(self):
        session = BackendSession.__new__(BackendSession)
        session.ssh = SimpleNamespace(close=lambda: None)
        session.runs = {}
        remote = {}
        visited = []

        class SFTP:
            def lstat(self, name):
                visited.append(name)
                return SimpleNamespace(st_mode=stat.S_IFREG, st_size=len(remote[name]))

            @contextmanager
            def open(self, name, mode):
                visited.append(name)
                stream = io.BytesIO(remote.get(name, b''))
                yield stream
                if mode == 'wb':
                    remote[name] = stream.getvalue()
                stream.close()

            def close(self):
                pass

        def upload(sftp, files, target):
            for rel, path in files:
                remote[target + '/' + rel] = path.read_bytes()

        session.open_sftp = lambda: SFTP()
        with tempfile.TemporaryDirectory() as folder:
            session.workspace = Path(folder)
            source = Path(folder) / 'rtl.v'
            source.write_text('module counter; endmodule', encoding='utf-8')
            with patch('backend_session.local_source_files', return_value=[('generated/rtl.v', source)]), \
                 patch('backend_session._ensure_project', return_value='/home/IC/Desktop/EDA_Projects/counter_backend'), \
                 patch('backend_session._create_new_dir', side_effect=lambda sftp, name: visited.append(name)), \
                 patch('backend_session._sftp_upload', side_effect=upload):
                result = session.start_snapshot()
            self.assertTrue(result['upload_ok'])
            self.assertTrue(all('upload_001' not in p and 'upload_003' not in p for p in visited))
            manifest = json.loads(remote[result['remote_directory'] + '/snapshot_manifest.json'])
            self.assertEqual(len(manifest['files_sha256']), 1)
            self.assertEqual(session.runs[result['run_label']], result)

    def test_sftp_handshake_timeout_closes_connection(self):
        class SSH:
            def __init__(self):
                self.closed = threading.Event()

            def close(self):
                self.closed.set()

            def open_sftp(self):
                self.closed.wait(1)
                raise OSError('connection closed')

        ssh = SSH()
        with self.assertRaises(RemoteError):
            open_sftp_bounded(ssh, seconds=0.03)
        self.assertTrue(ssh.closed.is_set())

    def test_exec_acknowledgement_is_inside_deadline(self):
        closed = threading.Event()
        ssh = SimpleNamespace(close=closed.set)

        def unacknowledged(*args, **kwargs):
            closed.wait(1)
            raise OSError('connection closed before exec acknowledgement')

        with patch('backend_transport.exec_checked', side_effect=unacknowledged):
            with self.assertRaises(RemoteError):
                exec_bounded(ssh, 'ignored', timeout_seconds=0.03)
        self.assertTrue(closed.is_set())

    def test_success_does_not_close_connection(self):
        ssh = SimpleNamespace(close=lambda: self.fail('successful request closed'))
        with connection_deadline(ssh, 1, 'test'):
            pass

    def test_search_actions_never_connect_or_execute(self):
        session = BackendSession.__new__(BackendSession)
        for job in ({'action': 'find_files'}, {'action': 'inspect', 'kind': 'process_library_search'}):
            with self.assertRaises(ValueError):
                session.perform(job, Path('.'))

    def test_recovery_reads_only_named_reports(self):
        session = BackendSession.__new__(BackendSession)
        session.runs = {'upload_003': {'remote_directory': '/home/IC/demo/runs/upload_003'}}
        names = []

        class SFTP:
            def lstat(self, name):
                names.append(name)
                return SimpleNamespace(st_mode=stat.S_IFREG, st_size=4)

            def open(self, name, mode):
                return io.BytesIO(b'log\n')

            def close(self):
                pass

        session.open_sftp = lambda: SFTP()
        with tempfile.TemporaryDirectory() as folder, \
             patch('backend_session.exec_checked', side_effect=AssertionError('Recovery must not execute or scan processes')):
            result = session.rescue_run('upload_003', Path(folder))
            self.assertEqual(len(result['files']), 5)
            self.assertFalse(result['stop_attempted'])
            self.assertEqual(result['icc_stop_status'], 'unconfirmed')
            self.assertTrue(all(name.startswith('/home/IC/demo/runs/upload_003/build/') for name in names))
            self.assertNotIn('/proc', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
