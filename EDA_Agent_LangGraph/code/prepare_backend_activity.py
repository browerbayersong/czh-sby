"""Copy the verified counter TB and add only DUT VCD dumping for power analysis."""
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    source = root / 'designs/counter_opt_round3/generated/tb/tb_counter_8bit.v'
    target = root / 'designs/counter_backend/generated/tb/tb_counter_8bit.v'
    text = source.read_text(encoding='utf-8')
    marker = 'module tb_counter_8bit;'
    assert text.count(marker) == 1
    addition = '''

    // Backend power experiment: record DUT activity without changing checks.
    initial begin
        $dumpfile("../build/activity/counter.vcd");
        $dumpvars(0, u_dut);
    end'''
    text = text.replace(marker, marker + addition)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != text.encode('utf-8'):
        raise ValueError('Activity TB already exists with different bytes; preserve and review it first')
    target.write_text(text, encoding='utf-8', newline='\n')
    record = {
        'source': str(source),
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'output_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'change': 'Only added DUT VCD dumping; original stimulus, reference model, checks and seeds retained',
        'dut_instance': 'tb_counter_8bit/u_dut', 'status': 'not_yet_simulated',
    }
    (root / 'designs/counter_backend/activity_preparation.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Activity TB prepared; original checks retained; real simulation still pending.')


if __name__ == '__main__':
    main()
