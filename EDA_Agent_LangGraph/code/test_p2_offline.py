"""P2 离线测试：编译配置（.f/宏/include/tb_top）与若干回归场景。

不连虚拟机、不调模型。
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r'E:\LangGraph')
from eda_remote_v8 import (  # noqa: E402
    RemoteError,
    _validate_tb,
    load_compile_config,
    local_source_files,
    source_manifest,
)


def build_ws(root: Path) -> None:
    (root / 'generated/rtl/inc').mkdir(parents=True)
    (root / 'generated/tb').mkdir(parents=True)
    (root / 'generated/rtl/a.v').write_text('module a; endmodule\n', encoding='utf-8')
    (root / 'generated/rtl/b.v').write_text('module b; endmodule\n', encoding='utf-8')
    (root / 'generated/rtl/inc/defs.vh').write_text('`define W 8\n', encoding='utf-8')
    (root / 'generated/tb/tb_top.v').write_text('module tb_top; a ua(); b ub(); endmodule\n',
                                                encoding='utf-8')
    (root / 'files.f').write_text(
        '// 手写 filelist\n'
        '+incdir+generated/rtl/inc\n'
        '+define+SIM +define+WIDTH=8\n'
        'generated/rtl/b.v\n'
        'generated/rtl/a.v\n'
        'generated/tb/tb_top.v\n',
        encoding='utf-8',
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        build_ws(ws)
        files = local_source_files(ws)

        # 1) .f 展开
        (ws / 'compile_cfg.json').write_text(json.dumps({
            'filelist': ['files.f'],
            'defines': {'EXTRA': '1'},
            'tb_top': 'tb_top',
        }, ensure_ascii=False), encoding='utf-8')
        cfg = load_compile_config(ws, files)
        assert cfg is not None
        assert cfg['sources'] == ['generated/rtl/b.v', 'generated/rtl/a.v', 'generated/tb/tb_top.v'], cfg
        assert cfg['incdirs'] == ['generated/rtl/inc'], cfg
        assert set(cfg['defines']) == {'EXTRA=1', 'SIM', 'WIDTH=8'}, cfg
        assert cfg['tb_top'] == 'tb_top'
        print('PASS: .f 展开（顺序 / incdir / define / tb_top）')

        # 2) 直接 filelist（不用 .f）+ options
        (ws / 'compile_cfg.json').write_text(json.dumps({
            'filelist': ['generated/rtl/a.v', 'generated/rtl/b.v'],
            'options': ['+lint=all'],
        }), encoding='utf-8')
        cfg = load_compile_config(ws, files)
        assert cfg['sources'] == ['generated/rtl/a.v', 'generated/rtl/b.v']
        assert cfg['options'] == ['+lint=all']
        print('PASS: 直接 filelist 与白名单选项')

        bad_cases = [
            ({'unknown': 1}, '未知字段'),
            ({'filelist': ['/etc/passwd']}, '绝对路径'),
            ({'filelist': ['generated/rtl/zzz.v']}, '未上传文件'),
            ({'filelist': ['generated/rtl/a.v'], 'defines': {'bad-name': 1}}, '非法宏名'),
            ({'filelist': ['generated/rtl/a.v'], 'options': ['-y /tmp']}, '非白名单选项'),
            ({'filelist': []}, '空 filelist'),
        ]
        for payload, label in bad_cases:
            (ws / 'compile_cfg.json').write_text(json.dumps(payload), encoding='utf-8')
            try:
                load_compile_config(ws, files)
            except RemoteError:
                pass
            else:
                raise AssertionError(f'应当拒绝：{label}')
        print('PASS: 6 类非法配置均被拒绝')

        # 3) 无配置时返回 None
        (ws / 'compile_cfg.json').unlink()
        assert load_compile_config(ws, files) is None
        print('PASS: 无配置时退回自动扫描')

        # 4) 重复模块被拒绝
        (ws / 'generated/rtl/dup.v').write_text('module a; endmodule\n', encoding='utf-8')
        try:
            source_manifest(local_source_files(ws))
        except RemoteError as exc:
            assert '重复模块' in str(exc)
            print('PASS: 同层重复模块被拒绝')
        else:
            raise AssertionError('重复模块未被拒绝')
        (ws / 'generated/rtl/dup.v').unlink()

        # 5) 错误的 TB 顶层被拒绝
        manifest = source_manifest(local_source_files(ws))
        try:
            _validate_tb('tb_not_exist', manifest)
        except RemoteError:
            print('PASS: 错误 TB 顶层被拒绝')
        else:
            raise AssertionError('错误 TB 顶层未被拒绝')
        _validate_tb('tb_top', manifest)

    # 6) 空工作空间被拒绝
    with tempfile.TemporaryDirectory() as tmp2:
        try:
            local_source_files(Path(tmp2))
        except RemoteError:
            print('PASS: 空工作空间被拒绝')
        else:
            raise AssertionError('空工作空间未被拒绝')

    print('P2 离线测试全部通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
