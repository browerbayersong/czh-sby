source generated/scripts/config.tcl
set_app_var target_library [list $EDA_DB]
set_app_var synthetic_library [list standard.sldb]
set_app_var link_library [concat [list *] [list $EDA_DB]]
file mkdir ../build/drc_shapes
if {[catch {
    open_mw_lib /home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261025_143839_f96edb1f/build/icc/counter_mw
    open_mw_cel -readonly counter_8bit
    redirect -file ../build/drc_shapes/shapes.txt {
        foreach_in_collection net [get_nets -hierarchical *] {
            set name [get_object_name $net]
            set canonical [string map [list "\\" ""] $name]
            if {$canonical eq {count[5]} || $canonical eq {N7}} {
                puts "NET $name"
                foreach_in_collection shape [get_net_shapes -of_objects $net -intersect {{7.7 16.1} {8.9 17.7}}] {
                    puts "SHAPE [get_object_name $shape]"
                    foreach attr {bbox layer_name width shape_type} {
                        if {![catch {get_attribute $shape $attr} value]} {puts "$attr: $value"}
                    }
                }
            }
        }
        foreach_in_collection shape [get_pin_shapes -of_objects [get_cells U14]] {
            puts "PIN_SHAPE [get_object_name $shape]"
            foreach attr {bbox layer_name pin_name} {
                if {![catch {get_attribute $shape $attr} value]} {puts "$attr: $value"}
            }
        }
    }
    puts "EDA_DRC_SHAPES_SAVED"
} message]} {puts "EDA_PROBE_FATAL $message"; exit 2}
exit 0
