file mkdir ../build/diagnostic
set report [open ../build/diagnostic/environment.txt w]
foreach name {/proc/meminfo /proc/loadavg /proc/version} {
    puts $report "FILE $name"
    if {[catch {set h [open $name r]} message]} {
        puts $report $message
    } else {
        puts $report [read $h 6000]
        close $h
    }
}
set name [file join $env(HOME) .bashrc]
puts $report "STARTUP COMMAND LINES"
if {![catch {set h [open $name r]}]} {
    set data [read $h 32000]
    close $h
    foreach line [split $data \n] {
        if {[regexp {(^|[ ;])(read|stty|find|exec|source|ulimit|cd)[ ;]} $line] && ![regexp -nocase {password|secret|token|api.key|private.key} $line]} {
            puts $report $line
        }
    }
}
close $report
puts "EDA_DIAGNOSTIC_COMPLETE"
exit
