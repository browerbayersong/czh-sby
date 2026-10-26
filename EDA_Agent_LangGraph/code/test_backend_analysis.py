import unittest

from eda_backend_analysis import (
    parse_area, parse_power, parse_routing_drc, parse_timing, parse_units, tool_stage_status,
    parse_pg_connectivity, parse_lvs,
)


class BackendReportTests(unittest.TestCase):
    def test_dc_area_and_timing(self):
        area = parse_area('Number of cells: 28\nTotal cell area: 123.456\n')
        self.assertEqual(area['cell_area'], 123.456)
        self.assertEqual(area['number_of_cells'], 28)
        timing = parse_timing(' slack (MET) 9.31\n slack (VIOLATED) -0.012\n')
        self.assertEqual(timing['worst_slack'], -0.012)
        self.assertFalse(timing['all_reported_paths_meet'])

    def test_power_units_and_derived_total(self):
        result = parse_power('Cell Internal Power = 2.0 uW\nNet Switching Power = 1e-3 mW\nCell Leakage Power = 25 nW\n')
        self.assertAlmostEqual(result['total']['watts'], 3.025e-6)
        self.assertIn('derived_from', result['total'])
        self.assertEqual(parse_power('Total Power = 5.5 mW')['total']['watts'], 0.0055)

    def test_pt_report_header_units_are_distinct_from_library_power_units(self):
        text = ('Dynamic Power Units = 1 W\nLeakage Power Units = 1 W\n'
                'Cell Internal Power = 1.301e-05\nNet Switching Power = 1.723e-06\n'
                'Cell Leakage Power = 3.597e-07\nTotal Power = 1.510e-05\n')
        self.assertAlmostEqual(parse_power(text)['total']['watts'], 15.10e-6)

    def test_redirected_tool_errors_in_diagnostics_reject_completion(self):
        log = 'EDA_STAGE_COMPLETE PT\nDiagnostics summary: 1 error, 2 warnings\n'
        self.assertEqual(tool_stage_status(0, log, 'EDA_STAGE_COMPLETE PT'), 'tool_reported_error')

    def test_unknown_is_not_zero_or_assumed_units(self):
        self.assertIsNone(parse_area('')['cell_area'])
        self.assertIsNone(parse_timing('No paths.')['worst_slack'])
        self.assertIsNone(parse_routing_drc('verification finished')['routing_clean'])
        result = parse_power('Total Power = 5.5\n')
        self.assertIsNone(result['total']['watts'])
        self.assertEqual(parse_units('Time Unit : 1ns\nPower Unit : 1mW\n')['time'], '1ns')

    def test_require_routing_and_connectivity_results(self):
        scope = '\nTotal number of nets = 36\nTotal number of excluded ports = 0 ports of 0 unplaced cells connected to 0 nets\n'
        self.assertTrue(parse_routing_drc('Total number of DRCs = 0\nTotal number of open nets = 0' + scope)['routing_clean'])
        self.assertFalse(parse_routing_drc('Total number of DRCs = 2\nTotal number of open nets = 0' + scope)['routing_clean'])
        self.assertIsNone(parse_routing_drc('Total number of DRCs = 0')['routing_clean'])

    def test_excluded_unplaced_cells_cannot_produce_a_clean_route(self):
        text = ('Total number of DRCs = 0\nTotal number of open nets = 0\nTotal number of nets = 13\n'
                'Total number of excluded ports = 153 ports of 25 unplaced cells connected to 36 nets\n')
        self.assertFalse(parse_routing_drc(text)['routing_clean'])

    def test_zero_error_wording_is_not_itself_a_connectivity_error(self):
        pg = 'Create error cell counter.err ...\nNo errors are found.\nChecked 2 nets, 0 have Errors\n'
        self.assertTrue(parse_pg_connectivity(pg)['clean'])
        self.assertIsNone(parse_lvs('Total OPEN Nets are 0')['clean'])

    def test_tool_exit_zero_alone_does_not_complete_stage(self):
        self.assertEqual(tool_stage_status(0, '', 'EDA_STAGE_COMPLETE DC'), 'completion_unverified')
        self.assertEqual(tool_stage_status(0, 'Error: failed\nEDA_STAGE_COMPLETE DC', 'EDA_STAGE_COMPLETE DC'), 'tool_reported_error')
        self.assertEqual(tool_stage_status(0, 'EDA_STAGE_COMPLETE DC', 'EDA_STAGE_COMPLETE DC'), 'completed')

    def test_echoed_tcl_marker_does_not_complete_stage(self):
        echoed = 'proc main {} {\n    puts "EDA_STAGE_COMPLETE ICC"\n}\n'
        self.assertEqual(tool_stage_status(0, echoed, 'EDA_STAGE_COMPLETE ICC'), 'completion_unverified')
        self.assertEqual(tool_stage_status(0, echoed + 'EDA_STAGE_COMPLETE ICC\n',
                                           'EDA_STAGE_COMPLETE ICC'), 'completed')


if __name__ == '__main__':
    unittest.main()
