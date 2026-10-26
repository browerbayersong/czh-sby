foreach command {route_zrt_detail route_zrt_eco remove_routes create_route_guide set_route_zrt_detail_options copy_mw_lib} {
    puts "EDA_ECO_HELP_BEGIN $command"
    if {[catch {help -verbose $command} message]} {puts $message}
    puts "EDA_ECO_HELP_END $command"
}
exit
