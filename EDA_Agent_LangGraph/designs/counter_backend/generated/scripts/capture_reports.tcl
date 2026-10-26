set env(DISPLAY) :0
if {[catch {
    puts [exec timeout 80s /usr/bin/python generated/scripts/capture_reports.py 2>@1]
} message]} {
    puts "EDA_REPORT_CAPTURE_FAILED $message"
    exit 2
}
puts "EDA_REPORT_CAPTURES_SAVED"
exit 0
