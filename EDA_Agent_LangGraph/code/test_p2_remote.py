"""P2 远程层回归测试：SSH 失败、仿真超时、非法工程名、不支持的模式。

不连真实虚拟机，全部用 mock。
"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

import paramiko

sys.path.insert(0, r'E:\LangGraph')
import eda_remote_v8 as r  # noqa: E402


class FakeClient:
    def __init__(self):
        self.calls = 0

    def load_host_keys(self, *a, **k):
        pass

    def set_missing_host_key_policy(self, *a, **k):
        pass

    def connect(self, **kwargs):
        self.calls += 1
        raise TimeoutError('timed out')

    def close(self):
        pass


def main() -> int:
    # 1) 仿真超时：timeout 命令返回 124
    assert r._sim_result(124, '') == 'failed'
    assert r._sim_result(0, '[FAIL] #1 exp=00 got=01') == 'failed'
    assert r._sim_result(0, ' TEST PASSED') == 'passed_by_marker'
    assert r._sim_result(0, 'no marker here') == 'finished_unverified'
    print('PASS: 仿真超时/失败/通过/未验证 四类判定')

    # 2) SSH 连接超时会重试一次，最终抛 RemoteError 且带目标地址
    client = FakeClient()
    with mock.patch.object(paramiko, 'SSHClient', return_value=client), \
         mock.patch.object(r.time, 'sleep', lambda *_: None):
        try:
            r.ssh_connect(r.SSHSettings(host='10.0.0.9', password='x'))
        except r.RemoteError as exc:
            assert '10.0.0.9' in str(exc), exc
            assert client.calls == 2, client.calls
            print('PASS: SSH 超时重试 1 次并报出目标地址')
        else:
            raise AssertionError('超时未抛错')

    # 3) known_hosts 缺失时给出明确提示（不发起连接）
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch('pathlib.Path.home', return_value=Path(tmp)):
            try:
                r.ssh_connect(r.SSHSettings(host='10.0.0.9', password='x'))
            except r.RemoteError as exc:
                assert 'known_hosts' in str(exc), exc
                print('PASS: 缺少 known_hosts 时提示明确')
            else:
                raise AssertionError('缺 known_hosts 未报错')

    # 4) 非法/保留工程名
    for bad in ('adder', 'ref', 'mw_lib', '../x', 'a/b', ''):
        try:
            r._checked_project_name(bad)
        except r.RemoteError:
            pass
        else:
            raise AssertionError(f'工程名应被拒绝：{bad!r}')
    print('PASS: 保留名与非法工程名被拒绝')

    # 5) 不支持的模式在联网前就报错
    with tempfile.TemporaryDirectory() as tmp:
        try:
            r.remote_job(r.SSHSettings(host='10.0.0.9', password='x'),
                         Path(tmp), 'c' * 32, mode='bogus')
        except r.RemoteError as exc:
            assert '不支持' in str(exc), exc
            print('PASS: 不支持的模式在联网前被拒绝')
        else:
            raise AssertionError('非法模式未被拒绝')

    print('P2 远程层回归测试全部通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
