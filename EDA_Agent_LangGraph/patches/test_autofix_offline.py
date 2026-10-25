"""eda_autofix 离线冒烟测试：不连虚拟机、不调真实模型。

验证：第 1 轮编译失败 → 生成补丁 → 第 2 轮使用补丁后的源码 → 通过。
"""

import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == 'patches' else Path(__file__).resolve().parent))
import eda_autofix as fa  # noqa: E402

BAD = 'module a; endmodule\n'
GOOD = 'module a(input clk); endmodule\n'

staged: list[str] = []
state = {'n': 0}


def fake_remote_job(cfg, workspace, chat_id, mode='vcs', tb_top='',
                    remote_base='', project_name=''):
    state['n'] += 1
    staged.append((Path(workspace) / 'generated/rtl/a.v').read_text(encoding='utf-8'))
    if state['n'] == 1:
        return {'status': 'compile_failed', 'compile_exit_code': 1,
                'compile_log': 'Error: syntax error near "endmodule"',
                'run_label': 'vcs_001', 'remote_directory': '/x/vcs_001'}
    return {'status': 'passed_by_marker', 'compile_exit_code': 0, 'sim_exit_code': 0,
            'compile_log': 'compiled', 'sim_log': 'TEST PASSED',
            'run_label': 'vcs_002', 'remote_directory': '/x/vcs_002',
            'coverage': {'score': 90.0}}


class Resp:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def invoke(self, messages):
        return Resp(json.dumps({
            'reason': '补上缺失的 clk 端口',
            'files': [{'path': 'generated/rtl/a.v', 'content': GOOD}],
        }))


fa.remote_job = fake_remote_job
fake_first = types.ModuleType('first_do')
fake_first.llm = FakeLLM()
sys.modules['first_do'] = fake_first

ws = Path(tempfile.mkdtemp())
(ws / 'generated/rtl').mkdir(parents=True)
(ws / 'generated/tb').mkdir(parents=True)
(ws / 'generated/rtl/a.v').write_text(BAD, encoding='utf-8', newline='\n')
(ws / 'generated/tb/tb_a.v').write_text('module tb_a; endmodule\n', encoding='utf-8', newline='\n')

result = fa.run_autofix(None, ws, 'c' * 32, 'tb_a', '/home/IC/x', 'proj', 3)

print('ok =', result['ok'], '| final =', result['final_status'],
      '| rounds =', len(result['iterations']))
print('第 1 轮状态 =', result['iterations'][0]['status'],
      '/ 类型 =', result['iterations'][0]['error_type'])
print('第 2 轮状态 =', result['iterations'][1]['status'])

assert result['ok'] is True, result
assert len(result['iterations']) == 2, result['iterations']
assert staged[0] == BAD, '第 1 轮应使用原始源码'
assert staged[1] == GOOD, '第 2 轮应使用补丁后的源码'
assert len(result['diffs']) == 1

# 已批准文件必须没被改动
assert (ws / 'generated/rtl/a.v').read_text(encoding='utf-8') == BAD, '不得覆盖已批准文件'

# 采纳后才写入
written = fa.adopt_result(ws, result)
assert written == ['generated/rtl/a.v']
assert (ws / 'generated/rtl/a.v').read_text(encoding='utf-8') == GOOD

print('PASS: 闭环逻辑、影子目录隔离、补丁校验、人工采纳均正常')

# 回归：VCS 版权声明里的 "license agreement" 不能被当成 license 失败
assert fa.classify_failure(
    'compile_failed',
    'only as authorized in a license agreement\nError-[SE] Syntax error',
) == 'compile'
assert fa.classify_failure('compile_failed', 'Unable to checkout a license for VCS') == 'environment'
print('PASS: 失败分类回归（版权声明不误判 / 真 license 失败仍可识别）')
