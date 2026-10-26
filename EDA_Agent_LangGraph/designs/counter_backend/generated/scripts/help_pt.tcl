foreach command {read_parasitics read_saif report_power report_switching_activity report_timing report_constraint report_units report_annotated_parasitics read_sdc set_power_analysis_options set_switching_activity} {
    puts "EDA_HELP_BEGIN $command"
    if {[catch {help -verbose $command} message]} {puts $message}
    puts "EDA_HELP_END $command"
}
puts "EDA_HELP_COMPLETE PT"
exit
