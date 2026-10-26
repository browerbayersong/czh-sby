foreach command {compile read_saif report_power report_switching_activity report_timing report_area report_units write_sdc write_file saif_map set_switching_activity} {
    puts "EDA_HELP_BEGIN $command"
    if {[catch {help -verbose $command} message]} {puts $message}
    puts "EDA_HELP_END $command"
}
puts "EDA_HELP_COMPLETE DC"
exit
