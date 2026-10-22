"""v8.2 isolated mock tests. No real SSH/EDA, no credentials, no network.
python test_v8_2_offline.py
"""
import importlib.util
import io
import json
import posixpath
import re
import sys
import tempfile
import types
from pathlib import Path

core=types.ModuleType('eda_agent_v8_core')
core.SPECIAL_NAMES={'Makefile','GNUmakefile'}
def safe_rel_name(path):
    parts=path.replace('\\','/').split('/')
    if any(not p or p in ('.','..') or p.startswith('.') for p in parts):
        raise ValueError('unsafe path')
    if any(c in path for c in ':;`$\\\n'):
        raise ValueError('unsafe chars')
    return path
core.safe_rel_name=safe_rel_name
sys.modules['eda_agent_v8_core']=core
spec=importlib.util.spec_from_file_location('eda_remote_v8',str(Path(__file__).with_name('eda_remote_v8.py')))
r=importlib.util.module_from_spec(spec)
sys.modules['eda_remote_v8']=r
spec.loader.exec_module(r)

class FakeSFTP:
    def __init__(self, posix=True):
        self.dirs={'/','/home','/home/IC','/home/IC/Desktop'}
        self.files={}
        self.links=set()
        self.posix=posix
    def normalize(self,p): return '/home/IC'
    def lstat(self,p):
        if p in self.links: return types.SimpleNamespace(st_mode=0o120777,st_size=0)
        if p in self.dirs: return types.SimpleNamespace(st_mode=0o40700,st_size=0)
        if p in self.files: return types.SimpleNamespace(st_mode=0o100600,st_size=len(self.files[p]))
        raise FileNotFoundError(2, 'No such file or directory', p)
    stat=lstat
    def mkdir(self,p,mode=0o700):
        if p in self.dirs: raise FileExistsError(p)
        if posixpath.dirname(p) not in self.dirs: raise FileNotFoundError(p)
        self.dirs.add(p)
    def open(self,p,mode):
        if mode=='rb':
            if p not in self.files: raise FileNotFoundError(p)
            return io.BytesIO(self.files[p])
        assert mode=='wb',mode
        if posixpath.dirname(p) not in self.dirs: raise FileNotFoundError(p)
        fs=self.files
        class Writer(io.BytesIO):
            def close(self):
                fs[p]=self.getvalue()
                super().close()
        return Writer()
    def rename(self,a,b):
        if b in self.files or b in self.dirs: raise FileExistsError(b)
        self.files[b]=self.files.pop(a)
    def posix_rename(self,a,b):
        if not self.posix: raise OSError('Operation unsupported')
        self.files[b]=self.files.pop(a)
    def remove(self,p): self.files.pop(p)
    def close(self): pass
class FakeSSH:
    def __init__(self,sftp): self.sftp=sftp
    def open_sftp(self): return self.sftp
    def close(self): pass


def run_tests(posix=True):
    fs=FakeSFTP(posix)
    r.ssh_connect=lambda cfg: FakeSSH(fs)
    commands=[]
    def fake_exec(_ssh, cmd, timeout_seconds=0):
        commands.append(cmd)
        m=re.search(r'^cd\s+([^ ]+)',cmd)
        cwd=m.group(1)
        run=posixpath.dirname(cwd)
        if 'covReport' in cmd:
            assert 'urg' in cmd, cmd
            fs.files[run+'/build/covReport/dashboard.txt'] = (
                'Total Coverage Summary\n'
                'SCORE  LINE   COND   TOGGLE FSM    BRANCH\n'
                ' 88.53  90.14 --      95.45 --      80.00\n'
            ).encode()
            return 0,'',''
        if 'vcs_compile.log' in cmd:
            assert cwd.endswith('/src'),cmd
            assert '-o ../build/simv' in cmd,cmd
            assert 'generated/rtl/counter.v' in cmd,cmd
            fs.files[run+'/build/vcs_compile.log']=b'Compile successful\n'
        else:
            assert '../build/simv' in cmd,cmd
            fs.files[run+'/build/vcs_sim.log']=b'[PASS] passed\n'
        return 0,'',''
    r.exec_checked=fake_exec
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        (root/'generated'/'rtl').mkdir(parents=True)
        (root/'generated'/'tb').mkdir(parents=True)
        # newline='\n'：Windows 上 write_text 默认把 \n 转成 \r\n，会让下面的字节比对失败
        (root/'generated'/'rtl'/'counter.v').write_text('module counter(input clk); endmodule\n', encoding='utf-8', newline='\n')
        (root/'generated'/'tb'/'tb_counter.sv').write_text('module tb_counter; initial begin $display("[PASS] passed");$finish;end endmodule\n', encoding='utf-8', newline='\n')
        cfg=r.SSHSettings(host='192.168.79.129',user='IC',password='not_used_in_tests')
        cid='a'*32
        a=r.remote_job(cfg,root,cid,mode='upload',project_name='UART_RX',remote_base='/home/IC/Desktop/EDA_Projects')
        project='/home/IC/Desktop/EDA_Projects/UART_RX'
        assert a['project_directory']==project
        assert a['run_label']=='upload_001'
        assert a['remote_directory']==project+'/runs/upload_001'
        assert fs.files[project+'/generated/rtl/counter.v']==b'module counter(input clk); endmodule\n'
        assert fs.files[project+'/runs/upload_001/src/generated/rtl/counter.v']==fs.files[project+'/generated/rtl/counter.v']
        assert json.loads(fs.files[project+'/.eda_agent_project.json'])['chat_id']==cid
        b=r.remote_job(cfg,root,cid,mode='vcs',tb_top='tb_counter',project_name='UART_RX',remote_base='~/Desktop/EDA_Projects')
        assert b['status']=='passed_by_marker',b
        assert b['remote_directory']==project+'/runs/vcs_001'
        assert b['sync']['unchanged']==2
        assert len(commands)==3,b  # 编译 + 仿真 + urg
        assert b['coverage']['score']==88.53,b
        assert b['coverage']['toggle']==95.45,b
        assert b['coverage']['cond'] is None,b
        assert (root/'remote_runs'/b['run_id']/'vcs_sim.log').exists()
        # Modify the source after the initial run; the first run's snapshot must not change.
        original=fs.files[project+'/runs/vcs_001/src/generated/rtl/counter.v']
        (root/'generated'/'rtl'/'counter.v').write_text('module counter(input clk); wire NEW_WIRE; endmodule\n', encoding='utf-8', newline='\n')
        c=r.remote_job(cfg,root,cid,mode='vcs',tb_top='tb_counter',project_name='UART_RX',remote_base='~/Desktop/EDA_Projects')
        assert c['run_label']=='vcs_002'
        assert c['sync']['updated_with_backup']==1,c
        assert fs.files[project+'/runs/vcs_001/src/generated/rtl/counter.v']==original
        assert fs.files[project+'/runs/vcs_002/src/generated/rtl/counter.v']!=original
        assert fs.files[project+'/history/vcs_002/generated/rtl/counter.v']==original
        assert fs.files[project+'/generated/rtl/counter.v']!=original
        assert len(commands)==6,c  # 两轮 × (编译 + 仿真 + urg)
        # Project claim by a different chat must fail without overwriting any bytes.
        n=len(fs.files)
        try:
            r.remote_job(cfg,root,'b'*32,mode='upload',project_name='UART_RX',remote_base='~/Desktop/EDA_Projects')
        except r.RemoteError as e:
            assert '当前对话' in str(e)
        else: raise AssertionError('accepted another chat')
        assert len(fs.files)==n
        # Existing unmarked directory must never be adopted.
        fs.dirs.add('/home/IC/Desktop/EDA_Projects/Old_Manual_Project')
        try:
            r.remote_job(cfg,root,cid,mode='upload',project_name='Old_Manual_Project',remote_base='~/Desktop/EDA_Projects')
        except r.RemoteError: pass
        else: raise AssertionError('adopted unmarked directory')
        # Symbolic link in selected root must be refused
        fs.links.add('/home/IC/Desktop/link')
        try:
            r.remote_job(cfg,root,cid,mode='upload',project_name='abc',remote_base='~/Desktop/link')
        except r.RemoteError: pass
        else: raise AssertionError('accepted link')
    print('PASS: mode posix',posix,'upload and 2 VCS runs, stable project, immutable snapshots, history backup, no cross-chat takeover, symlink blocked')

run_tests(True)
run_tests(False)  # old SFTP server without POSIX rename extension
for path in ['/tmp/EDA','/home/IC/Desktop/adder','/home/IC/Desktop/../x','~/Desktop/.ssh','~/Desktop/EDA;rm','/home/IC2/evil']:
    try:r._remote_base_path('/home/IC',path)
    except r.RemoteError:pass
    else:raise AssertionError('accepted path '+path)
for name in ['../etc','adder','', 'hi foo', 'hello;rm','a/b','x'*65]:
    try:r._checked_project_name(name)
    except r.RemoteError:pass
    else:raise AssertionError('accepted project name '+name)
assert r._checked_project_name('计数器_工程')=='计数器_工程'
print('PASS: path name and traversal rules')
