# Persistence check without starting the GUI (which can wait on exit dialogs).
source generated/scripts/config.tcl
set_app_var target_library [list $EDA_DB]
set_app_var synthetic_library [list standard.sldb]
set_app_var link_library [concat [list *] [list $EDA_DB]]
set_host_options -max_cores 1
file mkdir ../build/drc_verify
if {[catch {
    open_mw_lib /home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261026_130102_35ef2344/build/drc_ai/counter_mw
    open_mw_cel -readonly counter_8bit
    redirect -file ../build/drc_verify/routing_drc.rpt {verify_zrt_route -drc true -open_net true}
    redirect -file ../build/drc_verify/pg_connectivity.rpt {verify_pg_nets}
    redirect -file ../build/drc_verify/lvs.rpt {verify_lvs}
    redirect -file ../build/drc_verify/placement_legality.rpt {check_legality -verbose}
    write_verilog -no_physical_only_cells ../build/drc_verify/saved_netlist.v
    puts "EDA_SAVED_DRC_VERIFY_COMPLETE"
} message]} {puts "EDA_VERIFY_FATAL $message"; exit 2}
exit 0
