"""Offline acceptance tests; these fixtures are not real repair evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from drc_ai_repair import validate_plan, render_tcl, evaluate, BASE

class DrcAcceptanceTests(unittest.TestCase):
    def test_unchecked_commands_cannot_enter_template(self):
        plan={'strategy':'ripup_pair','pin_taper_mode':'off','extra_pin_tracks':True,'diagnosis':'test'}
        self.assertIn('copy_mw_lib -from',render_tcl(plan))
        with self.assertRaises(ValueError):
            validate_plan(dict(plan,tcl='remove_design -all'))
        with self.assertRaises(ValueError):
            validate_plan(dict(plan,pin_taper_mode='off; exit'))

    def test_actual_report_acceptance_and_missing_legality_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            d=root/'build/drc_ai'
            d.mkdir(parents=True)
            source=BASE/'session_queue/result_131/build/icc'
            routing=(source/'routing_drc.rpt').read_text()
            (d/'before_drc.rpt').write_text(routing)
            (d/'routing_drc.rpt').write_text(routing.replace('Total number of DRCs = 1','Total number of DRCs = 0'))
            for name in ('pg_connectivity.rpt','lvs.rpt','placement_legality.rpt'):
                (d/name).write_bytes((source/name).read_bytes())
            for name in ('netlist_before.v','netlist_after.v'):
                (d/name).write_text('module counter; wire a; endmodule')
            for name in ('cell_inventory_before.txt','cell_inventory_after.txt'):
                (d/name).write_text('U14 AO22X2\n')
            (root/'build/icc.status.json').write_text(json.dumps({'tool_exit_code':0}))
            (root/'build/icc.log').write_text('EDA_DRC_AI_CANDIDATE_EXECUTED\n')
            for name in ('counter_8bit.routed.v','counter_8bit.sdc','counter_8bit.gds'):
                (d/name).write_bytes(b'offline test fixture')
            self.assertTrue(evaluate(root)['accepted'])
            (d/'placement_legality.rpt').write_text('1\n')
            self.assertFalse(evaluate(root)['accepted'])

    def test_cell_or_netlist_change_is_rejected(self):
        # Exact normalized netlist comparison is intentionally stricter than
        # accepting a successful tool return code or a printed pass marker.
        from drc_ai_repair import canonical_netlist
        self.assertEqual(canonical_netlist('// time1\nmodule m; endmodule'),
                         canonical_netlist('// time2\nmodule m; endmodule'))
        self.assertNotEqual(canonical_netlist('module m; assign a=b; endmodule'),
                            canonical_netlist('module m; assign a=c; endmodule'))

if __name__=='__main__':unittest.main()
