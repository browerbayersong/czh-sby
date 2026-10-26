source generated/scripts/config.tcl

proc eda_route_count {} {
    redirect -file ../build/icc/routing_drc.rpt {verify_zrt_route -drc true -open_net true}
    set handle [open ../build/icc/routing_drc.rpt r]
    set text [read $handle]
    close $handle
    if {![regexp {Total number of DRCs = ([0-9]+)} $text unused count]} {
        error "Routing report has no DRC count"
    }
    return $count
}

proc eda_eco_main {} {
    global EDA_TOP EDA_DB EDA_GDS_MAP EDA_POWER_NET EDA_GROUND_NET
    file mkdir ../build/icc
    set_app_var target_library [list $EDA_DB]
    set_app_var synthetic_library [list standard.sldb]
    set_app_var link_library [concat [list *] [list $EDA_DB]]
    set_host_options -max_cores 1
    copy_mw_lib -from /home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261025_143839_f96edb1f/build/icc/counter_mw -to ../build/icc/counter_mw
    open_mw_lib ../build/icc/counter_mw
    open_mw_cel counter_8bit
    set_route_zrt_detail_options -drc_convergence_effort_level high -generate_extra_off_grid_pin_tracks true
    route_zrt_detail -incremental true -initial_drc_from_input true -max_number_iterations 80
    set count [eda_route_count]
    puts "EDA_ECO_INCREMENTAL_DRC $count"
    if {$count > 0} {
        set selected ""
        foreach_in_collection net [get_nets -hierarchical *] {
            set name [get_object_name $net]
            puts "EDA_ECO_NET $name"
            set canonical [string map [list "\\" ""] $name]
            if {$canonical eq "N7" || $canonical eq {count[5]}} {
                set selected [add_to_collection $selected $net]
            }
        }
        if {[sizeof_collection $selected] != 2} {error "Recorded ECO nets do not match the design"}
        route_zrt_eco -nets $selected -reroute modified_nets_first_then_others -utilize_dangling_wires false -max_detail_route_iterations 100
        set count [eda_route_count]
        puts "EDA_ECO_SELECTED_NETS_DRC $count"
    }
    if {$count > 0} {
        create_route_guide -name pin_access_spacing -coordinate {{8.0 16.3} {8.7 17.4}} -no_signal_layers M1
        route_zrt_eco -nets $selected -reroute modified_nets_first_then_others -utilize_dangling_wires false -max_detail_route_iterations 100
        set count [eda_route_count]
        puts "EDA_ECO_GUIDED_DRC $count"
    }
    redirect -file ../build/icc/pg_connectivity.rpt {verify_pg_nets}
    redirect -file ../build/icc/lvs.rpt {verify_lvs}
    redirect -file ../build/icc/placement_legality.rpt {check_legality -verbose}
    redirect -file ../build/icc/area.rpt {report_area -nosplit}
    redirect -file ../build/icc/physical.rpt {report_design_physical -all}
    redirect -file ../build/icc/units.rpt {report_units}
    if {$count != 0} {error "ECO still has $count DRC violations"}
    foreach report {routing_drc.rpt pg_connectivity.rpt lvs.rpt} {
        set handle [open ../build/icc/$report r]
        set text [read $handle]
        close $handle
        if {[regexp -nocase -line {^\s*ERROR\s*:} $text]} {error "Physical verification failed: $report"}
    }
    save_mw_cel
    write_verilog -no_physical_only_cells ../build/icc/counter_8bit.routed.v
    write_sdc -nosplit ../build/icc/counter_8bit.sdc
    set_write_stream_options -map_layer $EDA_GDS_MAP
    write_stream -format gds -cells $EDA_TOP ../build/icc/counter_8bit.gds
    puts "EDA_STAGE_COMPLETE ICC_LAYOUT"
    puts "EDA_SCOPE Physical layout verified; detailed parasitic extraction is not claimed."
}

if {[catch {eda_eco_main} message]} {
    puts "EDA_FATAL $message"
    exit 2
}
exit
