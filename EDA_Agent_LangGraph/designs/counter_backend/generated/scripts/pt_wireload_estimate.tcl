source generated/scripts/config.tcl
source generated/scripts/physical_target.tcl

proc eda_pt_wireload {} {
    global EDA_TOP EDA_DB EDA_SAIF EDA_PHYSICAL_DIRECTORY EDA_SOURCE_DRC_COUNT
    file mkdir ../build/pt_estimate
    set source_saif [file normalize $EDA_SAIF]
    set stage_directory [file normalize ../build/pt_estimate]
    set analysis_saif $stage_directory/counter.saif
    file copy $source_saif $analysis_saif
    if {![file readable $analysis_saif] || [file size $analysis_saif] == 0} {error "Analysis SAIF is not readable"}
    set_app_var power_enable_analysis true
    set_app_var power_analysis_mode averaged
    redirect -file ../build/pt_estimate/report_power_manual.txt {man report_power}
    set_app_var search_path [concat [get_app_var search_path] [list [file dirname $EDA_DB]]]
    set_app_var link_path [concat [list *] [list $EDA_DB]]
    read_verilog $EDA_PHYSICAL_DIRECTORY/counter_8bit.routed.v
    current_design $EDA_TOP
    if {![link_design $EDA_TOP]} {error "Physical netlist linking failed"}
    read_sdc $EDA_PHYSICAL_DIRECTORY/counter_8bit.sdc
    set_operating_conditions -library typical typical
    set_wire_load_mode enclosed
    set_wire_load_model -name tsmc090_wl10 -library typical [current_design]
    set_propagated_clock [all_clocks]
    foreach port {VDD VSS} value {1 0} {
        if {[sizeof_collection [get_ports -quiet $port]]} {set_case_analysis $value [get_ports $port]}
    }
    if {[file exists inputs/dc/counter_8bit_namemap.tcl]} {source inputs/dc/counter_8bit_namemap.tcl}
    redirect -file ../build/pt_estimate/activity_annotation.rpt {
        if {![read_saif -strip_path tb_counter_8bit/u_dut $analysis_saif]} {error "SAIF annotation failed"}
    }
    update_timing
    redirect -file ../build/pt_estimate/check_timing.rpt {check_timing -verbose}
    redirect -file ../build/pt_estimate/units.rpt {report_units}
    redirect -file ../build/pt_estimate/timing_setup.rpt {report_timing -delay_type max -max_paths 10 -slack_lesser_than 1000 -significant_digits 6 -nosplit}
    redirect -file ../build/pt_estimate/timing_hold.rpt {report_timing -delay_type min -max_paths 10 -slack_lesser_than 1000 -significant_digits 6 -nosplit}
    redirect -file ../build/pt_estimate/constraints.rpt {report_constraint -all_violators -nosplit}
    update_power
    redirect -file ../build/pt_estimate/power.rpt {report_power -verbose -nosplit}
    redirect -file ../build/pt_estimate/activity_coverage.rpt {report_switching_activity -coverage}
    set scope [open ../build/pt_estimate/analysis_scope.txt w]
    puts $scope "Input: routed netlist $EDA_PHYSICAL_DIRECTORY/counter_8bit.routed.v"
    puts $scope "Connectivity/LVS clean; source routing DRC count: $EDA_SOURCE_DRC_COUNT. Manufacturing clearance is not claimed."
    puts $scope "Interconnect: tsmc090_wl10 statistical wire-load model supplied by the same logical library."
    puts $scope "PVT: TT, 1.0 V, 25 C. Activity: verified RTL SAIF, with tool annotation coverage recorded."
    puts $scope "No SPEF is read. This is an estimated netlist analysis, not detailed post-route extraction or signoff."
    close $scope
    puts "EDA_STAGE_COMPLETE PT_WIRELOAD_ESTIMATE"
}
if {[catch {eda_pt_wireload} message]} {
    puts "EDA_FATAL $message"
    exit 2
}
exit
