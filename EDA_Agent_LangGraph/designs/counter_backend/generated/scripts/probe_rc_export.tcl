source generated/scripts/config.tcl
set_app_var target_library [list $EDA_DB]
set_app_var synthetic_library [list standard.sldb]
set_app_var link_library [concat [list *] [list $EDA_DB]]
file mkdir ../build/rc_probe
if {[catch {
    open_mw_lib /home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261025_141706_bb2a8ca2/build/icc/counter_mw
    open_mw_cel counter_8bit
    puts "EDA_RC_ESTIMATE_MANUAL_BEGIN"
    man extract_rc
    puts "EDA_RC_ESTIMATE_MANUAL_END"
    extract_rc -estimate
    write_parasitics -format SPEF -output ../build/rc_probe/estimate.spef
    if {![file exists ../build/rc_probe/estimate.spef] && ![file exists ../build/rc_probe/estimate.spef.max]} {
        error "No estimated SPEF was exported"
    }
    puts "EDA_RC_ESTIMATE_EXPORTED"
} message]} {
    puts "EDA_RC_PROBE_FAILED $message"
    exit 2
}
exit
