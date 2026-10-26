# -*- coding: utf-8 -*-
"""Convert installed, matching LEF RC data into a run-local ICC 1D RC model.

No PDK file is changed. No capacitance is invented. This educational, single
interconnect-corner model is not a replacement for foundry signoff TLUPlus.
Python 2.6 compatible for the lab guest.
"""
from __future__ import with_statement
import hashlib
import json
import os
import re
import sys

NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def lef_layers(text):
    layers = {}
    for match in re.finditer(r'(?ms)^LAYER\s+(M[1-6])\s*\n(.*?)^END\s+\1\s*$', text):
        name, body = match.group(1), match.group(2)
        values = {}
        for key, label in (('area_cap_pf_um2', r'CAPACITANCE\s+CPERSQDIST'),
                           ('edge_cap_pf_um', 'EDGECAPACITANCE'),
                           ('resistance_ohm_sq', r'RESISTANCE\s+RPERSQ')):
            field = re.search(r'(?m)^\s*' + label + r'\s+(' + NUMBER + r')\s*;', body)
            if not field or float(field.group(1)) <= 0:
                raise ValueError('Missing positive LEF RC value: ' + name + ' ' + key)
            values[key] = float(field.group(1))
        layers[name] = values
    if sorted(layers) != ['M1', 'M2', 'M3', 'M4', 'M5', 'M6']:
        raise ValueError('Matching six-metal routing layers are required')
    return layers


def enriched_technology(text, layers):
    if not re.search(r'unitCapacitanceName\s*=\s*"pf"', text):
        raise ValueError('Expected pF in technology units')
    if not re.search(r'unitLengthName\s*=\s*"micron"', text):
        raise ValueError('Expected micron in technology units')
    if not re.search(r'unitResistanceName\s*=\s*"kohm"', text):
        raise ValueError('Expected kohm in technology units')
    seen = []

    def replace(match):
        head, name, body, close = match.groups()
        values = layers[name]
        nominal = re.search(r'unitNomResistance\s*=\s*(' + NUMBER + r')', body)
        expected = values['resistance_ohm_sq'] / 1000.0
        if not nominal or abs(float(nominal.group(1)) - expected) > max(1e-12, expected * 1e-6):
            raise ValueError('LEF and technology sheet resistance differ: ' + name)
        if re.search(r'unit(?:Min|Nom|Max)(?:Capacitance|SideWallCap)\s*=', body):
            raise ValueError('Refusing to replace existing electrical fields: ' + name)
        addition = '\n\t\t/* Matching LEF RC converted for educational single-corner analysis. */\n'
        for corner in ('Min', 'Nom', 'Max'):
            addition += '\t\tunit%sCapacitance = %.12g\n' % (corner, values['area_cap_pf_um2'])
            # LEF edge cap is per edge; ICC SideWallCap includes both long sides.
            addition += '\t\tunit%sSideWallCap = %.12g\n' % (corner, 2.0 * values['edge_cap_pf_um'])
        seen.append(name)
        return head + body + addition + close

    result = re.sub(r'(?ms)(^Layer\s+"(M[1-6])"\s*\{)(.*?)(^\})', replace, text)
    if sorted(seen) != sorted(layers):
        raise ValueError('Technology layer names do not match the LEF')
    return result


def main():
    tf_path, lef_path, output, metadata = sys.argv[1:]
    with open(tf_path, 'rb') as handle:
        tf_bytes = handle.read(4000000)
    with open(lef_path, 'rb') as handle:
        lef_bytes = handle.read(1000000)
    layers = lef_layers(lef_bytes.decode('utf-8'))
    derived = enriched_technology(tf_bytes.decode('utf-8'), layers).encode('utf-8')
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(derived)
    record = {
        'source_tf': tf_path, 'source_lef': lef_path,
        'source_tf_sha256': hashlib.sha256(tf_bytes).hexdigest(),
        'source_lef_sha256': hashlib.sha256(lef_bytes).hexdigest(),
        'derived_tf_sha256': hashlib.sha256(derived).hexdigest(),
        'layers': layers, 'source_resistance_unchanged': True,
        'area_capacitance_unit': 'pF/um^2', 'edge_capacitance_unit': 'pF/um per edge',
        'icc_sidewall_mapping': 'two times LEF edge capacitance; both long sides',
        'corner_scope': 'Same LEF nominal values assigned to min/nom/max; one interconnect corner',
        'limitations': '1D LEF RC estimate; no TLUPlus, coupling/variation/signoff model',
        'references': [
            'https://coriolis.lip6.fr/doc/lefdef/lefdefref/LEFSyntax.html',
            'https://users.ece.utexas.edu/~mcdermot/vlsi1/VLSI2_SP_2017/synopsys/doc/ICC/icctf.pdf'],
    }
    fd = os.open(metadata, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(record, handle, sort_keys=True, indent=2)
    print('EDA_RC_MODEL_PREPARED six layers; source libraries unchanged')


if __name__ == '__main__':
    main()
