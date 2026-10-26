source generated/scripts/config.tcl

proc eda_dc_main {} {
    global EDA_TOP EDA_DB EDA_SAIF
    global EDA_CLOCK_PERIOD EDA_INPUT_DELAY EDA_OUTPUT_DELAY EDA_OUTPUT_LOAD
    global EDA_INPUT_TRANSITION EDA_CLOCK_UNCERTAINTY
    file mkdir ../build/dc
    file mkdir ../build/dc/work
    file mkdir ../build/dc/cache
    set_app_var search_path [concat [get_app_var search_path] [list [file dirname $EDA_DB]]]
    set_app_var target_library [list $EDA_DB]
    set_app_var synthetic_library [list standard.sldb]
    set_app_var link_library [concat [list *] [list $EDA_DB] [list standard.sldb]]
    set cache_write ../build/dc/cache
    set cache_read ../build/dc/cache
    define_design_lib WORK -path ../build/dc/work
    saif_map -start
    read_verilog generated/rtl/counter_8bit.v
    current_design $EDA_TOP
    if {![link]} {error "Design linking failed"}
    set_operating_conditions -library typical typical
    source generated/scripts/constraints.tcl
    set_fix_multiple_port_nets -all -buffer_constants
    redirect -file ../build/dc/check_design_before.rpt {check_design}
    if {![file exists $EDA_SAIF]} {error "Verified simulation activity input is missing"}
    redirect -file ../build/dc/activity_before.rpt {
        read_saif -input $EDA_SAIF -instance_name tb_counter_8bit/u_dut -auto_map_names -verbose
    }
    compile -map_effort medium
    change_names -rules verilog -hierarchy
    redirect -file ../build/dc/activity_annotation.rpt {
        read_saif -input $EDA_SAIF -instance_name tb_counter_8bit/u_dut -auto_map_names -verbose
    }
    redirect -file ../build/dc/check_design.rpt {check_design}
    redirect -file ../build/dc/units.rpt {report_units}
    redirect -file ../build/dc/library.rpt {report_lib typical}
    redirect -file ../build/dc/area.rpt {report_area -hierarchy -nosplit}
    redirect -file ../build/dc/timing_setup.rpt {
        report_timing -delay_type max -max_paths 10 -significant_digits 6 -nosplit
    }
    redirect -file ../build/dc/timing_hold.rpt {
        report_timing -delay_type min -max_paths 10 -significant_digits 6 -nosplit
    }
    redirect -file ../build/dc/qor.rpt {report_qor}
    redirect -file ../build/dc/constraints.rpt {report_constraint -all_violators -nosplit}
    redirect -file ../build/dc/power.rpt {report_power -analysis_effort medium -nosplit}
    if {[llength [info commands report_saif]]} {
        redirect -file ../build/dc/activity_coverage.rpt {report_saif}
    }
    saif_map -write_map ../build/dc/counter_8bit.namemap -type ptpx
    write_file -format verilog -hierarchy -output ../build/dc/counter_8bit.mapped.v
    write_file -format ddc -hierarchy -output ../build/dc/counter_8bit.mapped.ddc
    write_sdc -nosplit ../build/dc/counter_8bit.sdc
    write_sdf ../build/dc/counter_8bit.sdf
    puts "EDA_STAGE_COMPLETE DC"
}

if {[catch {eda_dc_main} message]} {
    puts "EDA_FATAL $message"
    exit 2
}
exit
