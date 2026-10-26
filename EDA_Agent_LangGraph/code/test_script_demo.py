"""Offline checks for generated-script admission and evidence-based completion."""
import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from eda_remote_v8 import SSHSettings
from eda_script_demo import (
    RTL, SCRIPT, TB, archive_script_demo, classify_result, digest,
    local_preflight, run_script_demo, validate_script,
)


VALID = '''#!/bin/bash
set -euo pipefail
timeout 300s /opt/Synopsys/VCS2014/bin/vcs -full64 -sverilog -timescale=1ns/1ps -cm line+cond+fsm+tgl+branch -cm_dir ../build/cov.vdb -top tb_counter_8bit -o ../build/simv generated/rtl/counter_8bit.v generated/tb/tb_counter_8bit.v > ../build/vcs_compile.log 2>&1
timeout 120s ../build/simv -cm line+cond+fsm+tgl+branch -cm_dir ../build/cov.vdb > ../build/vcs_sim.log 2>&1
timeout 120s /opt/Synopsys/VCS2014/bin/urg -dir ../build/cov.vdb -format text -report ../build/covReport > ../build/urg.log 2>&1
'''


class ScriptTests(unittest.TestCase):
    def test_valid_options_reordered_and_continued(self):
        continuation = '-sverilog ' + chr(92) + chr(10) + ' -full64'
        script = VALID.replace('-full64 -sverilog', continuation).replace('-top tb_counter_8bit', '-top "tb_counter_8bit" +incdir+generated/rtl')
        self.assertEqual(len(validate_script(script)['stages']), 3)

    def test_reject_unapproved_behavior(self):
        bad = [
            VALID + 'echo TEST PASSED\n',
            VALID.replace('set -euo pipefail', 'set +e'),
            VALID.replace('-o ../build/simv', '-o /tmp/simv'),
            VALID.replace('-o ../build/simv', '-o ../build/simv -o /tmp/simv'),
            VALID.replace('-full64', '-full64; curl example.com'),
            VALID.replace('-full64', '-full64 $(whoami)'),
            VALID.replace('-full64', '-full64 `whoami`'),
            VALID.replace('timeout 120s ../build/simv', 'echo TEST PASSED'),
            VALID.replace('> ../build/vcs_sim.log', '> ../build/other.log'),
            VALID.replace(' -cm line+cond+fsm+tgl+branch', ''),
            VALID.replace('300s', '99999s'),
            VALID.replace('-sverilog', '-sverilog -P unreviewed.so'),
            VALID.replace('generated/rtl/counter_8bit.v', '../../counter_8bit.v'),
        ]
        for script in bad:
            with self.subTest(script=script):
                with self.assertRaises(ValueError):
                    validate_script(script)

    def test_stage_order_is_required(self):
        lines = VALID.splitlines()
        lines[2], lines[3] = lines[3], lines[2]
        with self.assertRaises(ValueError):
            validate_script('\n'.join(lines))

    def test_script_exit_zero_is_insufficient(self):
        metrics = {'checks': 2035, 'passed': 2035, 'failed': 0,
                   'functional_bins_hit': 14, 'functional_bins_total': 14}
        self.assertEqual(classify_result(0, 'TEST PASSED', metrics, {'score': 84.97}), 'passed')
        self.assertNotEqual(classify_result(0, 'TEST PASSED', {}, {'score': 84.97}), 'passed')
        self.assertNotEqual(classify_result(0, '[FAIL]\nTEST PASSED', metrics, {'score': 84.97}), 'passed')
        self.assertNotEqual(classify_result(0, 'TEST PASSED', metrics, {}), 'passed')
        self.assertNotEqual(classify_result(1, 'TEST PASSED', metrics, {'score': 84.97}), 'passed')

    def test_real_script_execution_path_and_evidence_archive(self):
        """Fake only SSH I/O; check script execution, parsed logs and copied evidence."""
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / 'workspace'
            contents = {RTL: b'module counter_8bit; endmodule\n',
                        TB: b'module tb_counter_8bit; endmodule\n', SCRIPT: VALID.encode()}
            for relative, data in contents.items():
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            manifest = {'files_sha256': {rel: digest(data) for rel, data in contents.items()},
                        'script_review': validate_script(VALID)}
            (workspace / 'generation_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            local = workspace / 'remote_runs/run'
            local.mkdir(parents=True)
            (local / 'run_summary.json').write_text('{"status":"uploaded"}', encoding='utf-8')

            class RemoteWriter(io.BytesIO):
                def close(self):
                    pass

            class SFTP:
                def lstat(self, name):
                    data = contents[name.split('/src/')[1]]
                    return SimpleNamespace(st_mode=stat.S_IFREG, st_size=len(data))

                def open(self, name, mode):
                    return (io.BytesIO(contents[name.split('/src/')[1]])
                            if mode == 'rb' else RemoteWriter())

                def close(self):
                    pass

            sftp = SFTP()
            ssh = SimpleNamespace(open_sftp=lambda: sftp, close=lambda: None)
            upload = {'local_directory': str(local), 'remote_directory': '/home/IC/demo/runs/upload_001',
                      'source_snapshot': '/home/IC/demo/runs/upload_001/src', 'project_directory': '/home/IC/demo'}
            sim_log = ('[INFO] functional coverage = 14/14 bins\n'
                       'total checks = 2035, passed = 2035, failed = 0\nTEST PASSED\n')
            coverage_log = ('Total Coverage Summary\nSCORE LINE COND TOGGLE FSM BRANCH\n'
                            '84.97 91.95 -- 82.95 -- 80.00\n')
            def remote_log(_sftp, name, _folder):
                return sim_log if name == 'vcs_sim.log' else coverage_log if name.endswith('dashboard.txt') else 'fixture log\n'

            with patch('eda_script_demo.remote_job', return_value=upload), \
                 patch('eda_script_demo.ssh_connect', return_value=ssh), \
                 patch('eda_script_demo._create_new_dir'), \
                 patch('eda_script_demo.exec_checked', return_value=(0, '', '')) as execute, \
                 patch('eda_script_demo._read_remote_log', side_effect=remote_log):
                result = run_script_demo(SSHSettings('example.invalid'), workspace,
                                         project='demo', remote_base='/home/IC', chat_id='f' * 32)
            self.assertEqual(result['status'], 'passed')
            self.assertEqual(execute.call_count, 2)
            self.assertIn('bash -n generated/scripts/run_vcs.sh', execute.call_args_list[0].args[1])
            command = execute.call_args_list[1].args[1]
            self.assertIn('bash -x generated/scripts/run_vcs.sh', command)
            self.assertNotIn('/bin/vcs', command)
            self.assertEqual(json.loads((local / 'run_summary.json').read_text())['status'], 'uploaded')
            saved = json.loads((local / 'script_run_summary.json').read_text())
            self.assertEqual(saved['metrics']['passed'], 2035)
            self.assertEqual(saved['coverage']['score'], 84.97)
            archive = archive_script_demo(workspace, result, Path(folder) / 'report')
            with zipfile.ZipFile(archive.with_suffix('.zip')) as zipped:
                hashes = json.loads(zipped.read('SHA256SUMS.json'))
                for relative, expected in hashes.items():
                    self.assertEqual(digest(zipped.read(relative)), expected)
            # Editing a previously reviewed file must invalidate the next run.
            (workspace / SCRIPT).write_text(VALID + '# changed\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                local_preflight(workspace)


if __name__ == '__main__':
    unittest.main()
