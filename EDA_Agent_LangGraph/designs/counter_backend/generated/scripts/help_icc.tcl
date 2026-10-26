foreach command {create_mw_lib import_designs create_floorplan create_fp_placement place_opt clock_opt route_zrt_auto route_opt verify_zrt_route verify_pg_nets verify_lvs write_parasitics write_stream save_mw_cel report_design_physical report_power report_timing set_tlu_plus_files create_rectangular_rings preroute_standard_cells gui_start gui_zoom gui_write_window_image gui_get_current_window} {
    puts "EDA_HELP_BEGIN $command"
    if {[catch {help -verbose $command} message]} {puts $message}
    puts "EDA_HELP_END $command"
}
puts "EDA_HELP_COMPLETE ICC"
exit
