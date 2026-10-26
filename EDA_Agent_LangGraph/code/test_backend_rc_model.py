from pathlib import Path
from types import ModuleType
import unittest

source = Path(__file__).resolve().parent.parent / 'designs/counter_backend/generated/scripts/prepare_rc_model.py'
rc = ModuleType('prepare_rc_model')
exec(compile(source.read_bytes(), str(source), 'exec'), rc.__dict__)


class RCModelTests(unittest.TestCase):
    def setUp(self):
        self.lef = '\n'.join('LAYER M%d\n CAPACITANCE CPERSQDIST 0.01 ;\n'
                             ' EDGECAPACITANCE 0.002 ;\n RESISTANCE RPERSQ 0.13 ;\nEND M%d\n' % (n, n)
                             for n in range(1, 7))
        self.tf = 'Technology {\nunitCapacitanceName = "pf"\nunitLengthName = "micron"\nunitResistanceName = "kohm"\n}\n'
        self.tf += '\n'.join('Layer "M%d" {\n unitNomResistance = 0.00013\n}' % n for n in range(1, 7))

    def test_mapping_preserves_area_cap_and_combines_both_edges(self):
        result = rc.enriched_technology(self.tf, rc.lef_layers(self.lef))
        self.assertEqual(result.count('unitNomCapacitance = 0.01'), 6)
        self.assertEqual(result.count('unitNomSideWallCap = 0.004'), 6)
        self.assertEqual(result.count('unitNomResistance = 0.00013'), 6)

    def test_unit_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            rc.enriched_technology(self.tf.replace('"pf"', '"ff"'), rc.lef_layers(self.lef))

    def test_mismatched_technology_is_rejected(self):
        with self.assertRaises(ValueError):
            rc.enriched_technology(self.tf.replace('0.00013', '0.0013'), rc.lef_layers(self.lef))

    def test_existing_values_are_not_overwritten(self):
        with self.assertRaises(ValueError):
            rc.enriched_technology(self.tf.replace('unitNomResistance', 'unitNomCapacitance = 7\nunitNomResistance'),
                                   rc.lef_layers(self.lef))


if __name__ == '__main__':
    unittest.main()
