foreach command {set_layer_rc set_attribute get_layers list_attributes set_extraction_options set_tlu_plus_files check_error extract_rc read_lef set_write_stream_options check_legality check_physical_design} {
    puts "EDA_RC_HELP_BEGIN $command"
    if {[catch {help -verbose $command} message]} {puts $message}
    puts "EDA_RC_HELP_END $command"
}
puts "EDA_EXTRACTION_VARIABLES_BEGIN"
printvar *extract*
puts "EDA_EXTRACTION_VARIABLES_END"
puts "EDA_LAYER_ATTRIBUTES_BEGIN"
list_attributes -application -class layer
puts "EDA_LAYER_ATTRIBUTES_END"
puts "EDA_CHECK_ERROR_MANUAL_BEGIN"
man check_error
puts "EDA_CHECK_ERROR_MANUAL_END"
set lef /opt/Foundary_Library/TSMC90/aci/sc-x/lef/tsmc090lk_6lm_1thick_tech.lef
set handle [open $lef r]
set data [read $handle 100000]
close $handle
puts "EDA_PDK_LEF_RC_BEGIN $lef"
foreach line [split $data \n] {
    if {[regexp {(^LAYER|^UNITS|^END UNITS|CAPACITANCE|EDGECAPACITANCE|RESISTANCE)} $line]} {puts $line}
}
puts "EDA_PDK_LEF_RC_END"
exit
