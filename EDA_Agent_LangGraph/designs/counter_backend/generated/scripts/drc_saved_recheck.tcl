# Independent read-only verification of the saved, model-selected repair copy.
source generated/scripts/config.tcl
set_app_var target_library [list $EDA_DB]
set_app_var synthetic_library [list standard.sldb]
set_app_var link_library [concat [list *] [list $EDA_DB]]
set_host_options -max_cores 1
set env(DISPLAY) :0
file mkdir ../build/drc_recheck
if {[catch {
    open_mw_lib /home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261026_130102_35ef2344/build/drc_ai/counter_mw
    open_mw_cel -readonly counter_8bit
    redirect -file ../build/drc_recheck/routing_drc.rpt {verify_zrt_route -drc true -open_net true}
    redirect -file ../build/drc_recheck/pg_connectivity.rpt {verify_pg_nets}
    redirect -file ../build/drc_recheck/lvs.rpt {verify_lvs}
    redirect -file ../build/drc_recheck/placement_legality.rpt {check_legality -verbose}
    write_verilog -no_physical_only_cells ../build/drc_recheck/saved_netlist.v
    gui_start
    set layout_window [gui_get_current_window -types Layout -mru]
    gui_zoom -window $layout_window -full
    gui_write_window_image -file ../build/drc_recheck/layout_canvas.png -window $layout_window
    update
    after 1000
    update
    puts [exec timeout 15s /usr/bin/python generated/scripts/capture_display.py ../build/drc_recheck/layout.png]
    puts [exec timeout 35s /usr/bin/python generated/scripts/capture_drc_repair.py 2>@1]
    puts "EDA_SAVED_DRC_RECHECK_COMPLETE"
} message]} {puts "EDA_RECHECK_FATAL $message"; exit 2}
exit 0
