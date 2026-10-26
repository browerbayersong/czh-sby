source generated/scripts/config.tcl

proc eda_pt_main {} {
    global EDA_TOP EDA_DB EDA_SAIF
    set icc_dir [file normalize ../build/icc]
    set dc_dir [file normalize inputs/dc]
    file mkdir ../build/pt
    set_app_var power_enable_analysis true
    set_app_var power_analysis_mode averaged
    set_app_var search_path [concat [get_app_var search_path] [list [file dirname $EDA_DB]]]
    set_app_var link_path [concat [list *] [list $EDA_DB]]
    read_verilog $icc_dir/counter_8bit.routed.v
    current_design $EDA_TOP
    if {![link_design $EDA_TOP]} {error "Post-route netlist linking failed"}
    read_sdc $icc_dir/counter_8bit.sdc
    set_propagated_clock [all_clocks]
    foreach port {VDD VSS} value {1 0} {
        if {[sizeof_collection [get_ports -quiet $port]]} {
            set_case_analysis $value [get_ports $port]
        }
    }
    if {[file exists $icc_dir/counter_8bit.spef]} {
        set spef $icc_dir/counter_8bit.spef
    } elseif {[file exists $icc_dir/counter_8bit.spef.max]} {
        set spef $icc_dir/counter_8bit.spef.max
    } else {
        error "ICC parasitic output is missing; do not substitute a zero-wire estimate"
    }
    read_parasitics -format spef $spef
    if {[file exists $dc_dir/counter_8bit_namemap.tcl]} {
        source $dc_dir/counter_8bit_namemap.tcl
    }
    redirect -file ../build/pt/activity_annotation.rpt {
        read_saif -strip_path tb_counter_8bit/u_dut $EDA_SAIF
    }
    update_timing
    redirect -file ../build/pt/check_timing.rpt {check_timing -verbose}
    redirect -file ../build/pt/units.rpt {report_units}
    redirect -file ../build/pt/timing_setup.rpt {
        report_timing -delay_type max -max_paths 10 -significant_digits 6 -nosplit
    }
    redirect -file ../build/pt/timing_hold.rpt {
        report_timing -delay_type min -max_paths 10 -significant_digits 6 -nosplit
    }
    redirect -file ../build/pt/constraints.rpt {report_constraint -all_violators -nosplit}
    redirect -file ../build/pt/parasitic_annotation.rpt {
        report_annotated_parasitics -check -list_not_annotated
    }
    update_power
    redirect -file ../build/pt/power.rpt {report_power -nosplit}
    redirect -file ../build/pt/activity_coverage.rpt {report_switching_activity -coverage}
    redirect -file ../build/pt/activity_details.rpt {report_switching_activity -average_activity}
    set metadata [open ../build/pt/analysis_scope.txt w]
    puts $metadata "PVT: TT, 1.0 V, 25 C. Clock: 10 ns. Source activity: VCS-verified RTL SAIF."
    puts $metadata "Parasitics: $spef"
    puts $metadata "ICC uses a run-local TF populated from the matching installed LEF area and edge capacitance."
    puts $metadata "One-dimensional, single interconnect corner; no TLUPlus/coupling/variation/signoff model."
    close $metadata
    puts "EDA_STAGE_COMPLETE PT"
}

if {[catch {eda_pt_main} message]} {
    puts "EDA_FATAL $message"
    exit 2
}
exit
