set target_handle [open inputs/physical_run.txt r]
set physical_label [string trim [read $target_handle 200]]
close $target_handle
if {![regexp {^upload_[0-9]{8}_[0-9]{6}_[0-9a-f]{8}$} $physical_label]} {
    error "Invalid recorded physical run label"
}
set EDA_PHYSICAL_DIRECTORY /home/IC/Desktop/EDA_Projects/counter_backend/runs/$physical_label/build/icc
set target_handle [open $EDA_PHYSICAL_DIRECTORY/routing_drc.rpt r]
set target_report [read $target_handle]
close $target_handle
if {![regexp {Total number of DRCs = ([0-9]+)} $target_report unused EDA_SOURCE_DRC_COUNT]} {
    error "Physical target has no routing DRC count"
}
puts "EDA_SOURCE_ROUTING_DRC_COUNT $EDA_SOURCE_DRC_COUNT"
foreach target_pattern {{Total number of open nets = ([0-9]+)} {ports of ([0-9]+) unplaced cells}} {
    if {![regexp $target_pattern $target_report unused target_count] || $target_count != 0} {
        error "Physical target has open nets or unplaced cells"
    }
}
foreach target_name {pg_connectivity.rpt lvs.rpt} {
    set target_handle [open $EDA_PHYSICAL_DIRECTORY/$target_name r]
    set target_report [read $target_handle]
    close $target_handle
    if {[regexp -nocase -line {^\s*ERROR\s*:} $target_report]} {
        error "Physical target has connectivity errors"
    }
}
