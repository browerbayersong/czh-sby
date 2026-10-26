"""Read actual DC/ICC/PT text reports, keeping units and missing values explicit."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
POWER_FACTORS = {'W': 1.0, 'mW': 1e-3, 'uW': 1e-6, 'nW': 1e-9, 'pW': 1e-12}


def _field(text: str, label: str) -> float | None:
    match = re.search(r'(?im)^\s*' + label + r'\s*[:=]\s*(' + NUMBER + r')', text)
    return float(match[1]) if match else None


def parse_area(text: str) -> dict[str, Any]:
    total = _field(text, r'Total cell area')
    if total is None:
        total = _field(text, r'Cell area')
    return {'cell_area': total, 'area_unit': 'library_area_unit',
            'number_of_cells': _field(text, r'Number of cells'),
            'combinational_area': _field(text, r'Combinational area'),
            'sequential_area': _field(text, r'Noncombinational area')}


def parse_timing(text: str) -> dict[str, Any]:
    slacks = [float(m) for m in re.findall(
        r'(?im)^\s*slack\s*\((?:MET|VIOLATED)\)\s*(' + NUMBER + r')', text)]
    delay = re.search(r'(?im)^\s*data arrival time\s+(' + NUMBER + r')', text)
    return {'worst_slack': min(slacks) if slacks else None,
            'reported_paths': len(slacks), 'all_reported_paths_meet': all(x >= 0 for x in slacks) if slacks else None,
            'first_data_arrival_time': float(delay[1]) if delay else None,
            'time_unit': None}  # Read report_units; do not assume all libraries use ns.


def parse_units(text: str) -> dict[str, str | None]:
    units = {}
    for name in ('Time', 'Capacitive Load', 'Power', 'Voltage', 'Resistance'):
        label = re.escape(name).replace(r'\ ', r'[ _]+')
        match = re.search(r'(?im)^\s*' + label + r'[ _]+(?:Unit|Units)\s*[:=]\s*(.+?)\s*$', text)
        units[name.lower().replace(' ', '_')] = match[1] if match else None
    return units


def parse_power(text: str) -> dict[str, Any]:
    fields = {}
    report_units = {}
    for kind in ('Dynamic', 'Leakage'):
        unit_match = re.search(r'(?im)^\s*' + kind + r' Power Units\s*=\s*1\s*(mW|uW|nW|pW|W)\b', text)
        report_units[kind.lower()] = unit_match[1] if unit_match else None
    labels = {
        'internal': 'Cell Internal Power', 'switching': 'Net Switching Power',
        'leakage': 'Cell Leakage Power', 'dynamic': 'Total Dynamic Power', 'total': 'Total Power',
    }
    for name, label in labels.items():
        match = re.search(r'(?im)^\s*' + label + r'\s*=\s*(' + NUMBER + r')\s*(mW|uW|nW|pW|W)?\b', text)
        if match:
            value, unit = float(match[1]), match[2]
            if unit is None:
                if name == 'leakage':
                    unit = report_units['leakage']
                elif name == 'total':
                    unit = report_units['dynamic'] if report_units['dynamic'] == report_units['leakage'] else None
                else:
                    unit = report_units['dynamic']
            fields[name] = {'value': value, 'unit': unit,
                            'watts': value * POWER_FACTORS[unit] if unit else None}
    # Preserve an explicitly reported total. Otherwise derive only from values
    # whose units were actually supplied, and label the result as derived.
    if 'total' not in fields:
        components = ('dynamic', 'leakage') if 'dynamic' in fields else ('internal', 'switching', 'leakage')
        if all(name in fields and fields[name]['watts'] is not None for name in components):
            fields['total'] = {'value': sum(fields[name]['watts'] for name in components),
                               'unit': 'W', 'watts': sum(fields[name]['watts'] for name in components),
                               'derived_from': list(components)}
    return fields


def parse_routing_drc(text: str) -> dict[str, Any]:
    drc = re.search(r'(?im)^\s*(?:Total\s+(?:number\s+of\s+)?(?:DRCs|DRC\s+(?:errors|violations)))\s*[:=]\s*(\d+)', text)
    opens = re.search(r'(?im)^\s*Total\s+(?:number\s+of\s+)?open\s+nets\s*[:=]\s*(\d+)', text)
    excluded = re.search(r'(?im)^\s*Total number of excluded ports\s*=\s*(\d+)\s+ports of\s+(\d+)\s+unplaced cells', text)
    checked = re.search(r'(?im)^\s*Total number of nets\s*=\s*(\d+)', text)
    counts = {'routing_drc_errors': int(drc[1]) if drc else None,
              'open_nets': int(opens[1]) if opens else None,
              'nets_checked': int(checked[1]) if checked else None,
              'excluded_ports': int(excluded[1]) if excluded else None,
              'unplaced_cells': int(excluded[2]) if excluded else None,
              'check_scope': 'ICC routing verification; not foundry signoff DRC'}
    counts['routing_clean'] = (all(counts[x] == 0 for x in ('routing_drc_errors', 'open_nets', 'excluded_ports', 'unplaced_cells'))
                               and counts['nets_checked'] > 0 if drc and opens and excluded and checked else None)
    return counts


def parse_pg_connectivity(text: str) -> dict[str, Any]:
    match = re.search(r'(?im)^\s*Checked\s+(\d+)\s+nets,\s*(\d+)\s+have Errors', text)
    return {'nets_checked': int(match[1]) if match else None,
            'nets_with_errors': int(match[2]) if match else None,
            'clean': int(match[1]) > 0 and int(match[2]) == 0 if match else None}


def parse_lvs(text: str) -> dict[str, Any]:
    result = {}
    for key, label in (('floating_ports', 'Floating ports'), ('floating_nets', 'Floating Nets'),
                       ('short_nets', 'SHORT Nets'), ('open_nets', 'OPEN Nets'),
                       ('electrical_equivalence_errors', 'Electrical Equivalent Error'),
                       ('must_join_errors', 'Must Joint Error')):
        found = re.search(r'(?im)Total\s+' + label + r'\s+are\s+(\d+)', text)
        result[key] = int(found[1]) if found else None
    values = list(result.values())
    result['clean'] = all(x == 0 for x in values) if all(x is not None for x in values) else None
    return result


def tool_stage_status(exit_code: int | None, log: str, marker: str) -> str:
    if exit_code is None:
        return 'not_run'
    if exit_code != 0:
        return 'tool_failed'
    diagnostic_errors = re.search(r'(?im)^Diagnostics summary:\s*(\d+)\s+errors?\b', log)
    if (re.search(r'(?im)^\s*(?:Error\s*:|Fatal\s*:|EDA_FATAL\b)', log)
            or diagnostic_errors and int(diagnostic_errors[1]) > 0):
        return 'tool_reported_error'
    # Synopsys echoes Tcl procedure definitions, including an unexecuted
    # `puts "EDA_STAGE_COMPLETE ..."`. Only a standalone emitted line counts.
    emitted = re.search(r'(?m)^\s*' + re.escape(marker) + r'\s*$', log)
    return 'completed' if emitted else 'completion_unverified'


def collect_stage(folder: Path, stage: str, exit_code: int | None) -> dict[str, Any]:
    def read(name):
        path = folder / name
        return path.read_text(encoding='utf-8', errors='replace') if path.is_file() else ''
    units = parse_units(read('units.rpt'))
    timing = parse_timing(read('timing_setup.rpt'))
    timing['time_unit'] = units.get('time')
    hold = parse_timing(read('timing_hold.rpt'))
    hold['time_unit'] = units.get('time')
    log_path = folder / (stage + '.log')
    if not log_path.is_file():
        log_path = folder.parent / (stage + '.log')
    log = log_path.read_text(encoding='utf-8', errors='replace') if log_path.is_file() else ''
    return {'stage': stage, 'status': tool_stage_status(exit_code, log, 'EDA_STAGE_COMPLETE ' + stage.upper()),
            'area': parse_area(read('area.rpt')), 'setup_timing': timing,
            'hold_timing': hold,
            'power': parse_power(read('power.rpt')), 'units': units,
            'routing_drc': parse_routing_drc(read('routing_drc.rpt')) if stage == 'icc' else None,
            'power_method': 'read accompanying switching-activity/annotation report; not inferred from file existence'}
