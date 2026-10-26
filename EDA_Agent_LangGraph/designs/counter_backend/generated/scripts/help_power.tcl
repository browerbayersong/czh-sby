foreach command {create_power_straps create_terminal create_pin create_net_shape create_via get_net_shapes open_mw_cel} {
    puts "EDA_POWER_HELP_BEGIN $command"
    if {[catch {help -verbose $command} message]} {puts $message}
    puts "EDA_POWER_HELP_END $command"
}
puts "EDA_POWER_MANUAL_BEGIN"
man create_power_straps
puts "EDA_POWER_MANUAL_END"
exit
