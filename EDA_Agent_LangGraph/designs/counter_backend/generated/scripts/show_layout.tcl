source generated/scripts/config.tcl
source generated/scripts/physical_target.tcl
set env(DISPLAY) :0
set_app_var target_library [list $EDA_DB]
set_app_var synthetic_library [list standard.sldb]
set_app_var link_library [concat [list *] [list $EDA_DB]]
file mkdir ../build/display
if {[catch {
    open_mw_lib $EDA_PHYSICAL_DIRECTORY/counter_mw
    open_mw_cel -readonly counter_8bit
    gui_start
    verify_zrt_route -drc true -open_net true
    set drc_handle [open ../build/display/drc_details.txt w]
    foreach_in_collection item [get_drc_errors -quiet] {
        puts $drc_handle "DRC [get_object_name $item]"
        foreach attribute {type bbox layer_names net1_name net2_name actual_spacing required_spacing route_types details report} {
            puts $drc_handle "$attribute: [get_attribute $item $attribute]"
        }
    }
    close $drc_handle
    set layout_window [gui_get_current_window -types Layout -mru]
    gui_zoom -window $layout_window -full
    gui_write_window_image -file ../build/display/layout_canvas.png -window $layout_window
    update
    after 1500
    update
    puts [exec timeout 15s /usr/bin/python generated/scripts/capture_display.py ../build/display/layout.png]
    puts "EDA_REAL_GUI_CAPTURED"
} message]} {
    puts "EDA_GUI_CAPTURE_FAILED $message"
    exit 2
}
exit 0
