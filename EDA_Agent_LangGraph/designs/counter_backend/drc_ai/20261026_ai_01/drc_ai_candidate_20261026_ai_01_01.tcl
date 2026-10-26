source generated/scripts/config.tcl
set_app_var target_library [list $EDA_DB]
set_app_var synthetic_library [list standard.sldb]
set_app_var link_library [concat [list *] [list $EDA_DB]]
set_host_options -max_cores 1
file mkdir ../build/drc_ai
proc inventory {filename} {
    set h [open $filename w]
    set rows {}
    foreach_in_collection c [get_cells -hierarchical *] {
        lappend rows "[get_object_name $c] [get_attribute $c ref_name]"
    }
    foreach row [lsort $rows] {puts $h $row}
    close $h
}
if {[catch {
    copy_mw_lib -from /home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261025_143839_f96edb1f/build/icc/counter_mw -to ../build/drc_ai/counter_mw
    open_mw_lib ../build/drc_ai/counter_mw
    open_mw_cel counter_8bit
    redirect -file ../build/drc_ai/before_drc.rpt {verify_zrt_route -drc true -open_net true}
    write_verilog -no_physical_only_cells ../build/drc_ai/netlist_before.v
    inventory ../build/drc_ai/cell_inventory_before.txt
    set n7 ""
    set c5 ""
    foreach_in_collection n [get_nets -hierarchical *] {
        set canonical [string map [list "\\" ""] [get_object_name $n]]
        if {$canonical eq {N7}} {set n7 $n}
        if {$canonical eq {count[5]}} {set c5 $n}
    }
    set selected [add_to_collection $n7 $c5]
    if {[sizeof_collection $selected] != 2} {error "Target nets do not match recorded case"}
    set_route_zrt_detail_options -drc_convergence_effort_level high -pin_taper_mode default_width -generate_extra_off_grid_pin_tracks true
    remove_net_routing $n7
    route_zrt_eco -nets $selected -reroute modified_nets_first_then_others -utilize_dangling_wires false -max_detail_route_iterations 80
    redirect -file ../build/drc_ai/routing_drc.rpt {verify_zrt_route -drc true -open_net true}
    redirect -file ../build/drc_ai/pg_connectivity.rpt {verify_pg_nets}
    redirect -file ../build/drc_ai/lvs.rpt {verify_lvs}
    redirect -file ../build/drc_ai/placement_legality.rpt {check_legality -verbose}
    set h [open ../build/drc_ai/drc_details.txt w]
    foreach_in_collection item [get_drc_errors -quiet] {
        foreach attr {type bbox layer_names net1_name net2_name} {
            puts $h "$attr: [get_attribute $item $attr]"
        }
    }
    close $h
    write_verilog -no_physical_only_cells ../build/drc_ai/netlist_after.v
    inventory ../build/drc_ai/cell_inventory_after.txt
    save_mw_cel
    write_verilog -no_physical_only_cells ../build/drc_ai/counter_8bit.routed.v
    write_sdc -nosplit ../build/drc_ai/counter_8bit.sdc
    set_write_stream_options -map_layer $EDA_GDS_MAP
    write_stream -format gds -cells $EDA_TOP ../build/drc_ai/counter_8bit.gds
    puts "EDA_DRC_AI_CANDIDATE_EXECUTED"
} message]} {puts "EDA_DRC_AI_FATAL $message"; exit 2}
exit 0
