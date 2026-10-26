###################################################################

# Created by write_sdc on Sun Oct 25 14:04:43 2026

###################################################################
set sdc_version 2.0

set_units -time ns -resistance kOhm -capacitance pF -voltage V -current mA
set_operating_conditions typical -library typical
set_load -pin_load 0.01 [get_ports {count[2]}]
set_load -pin_load 0.01 [get_ports {count[1]}]
set_load -pin_load 0.01 [get_ports {count[0]}]
set_load -pin_load 0.01 [get_ports {count[7]}]
set_load -pin_load 0.01 [get_ports {count[6]}]
set_load -pin_load 0.01 [get_ports {count[5]}]
set_load -pin_load 0.01 [get_ports {count[4]}]
set_load -pin_load 0.01 [get_ports {count[3]}]
create_clock [get_ports clk]  -period 10  -waveform {0 5}
set_clock_uncertainty 0.1  [get_clocks clk]
set_clock_transition -max -rise 0.1 [get_clocks clk]
set_clock_transition -max -fall 0.1 [get_clocks clk]
set_clock_transition -min -rise 0.1 [get_clocks clk]
set_clock_transition -min -fall 0.1 [get_clocks clk]
set_false_path   -from [get_ports rst_n]
set_input_delay -clock clk  1  [get_ports en]
set_output_delay -clock clk  1  [get_ports {count[7]}]
set_output_delay -clock clk  1  [get_ports {count[6]}]
set_output_delay -clock clk  1  [get_ports {count[5]}]
set_output_delay -clock clk  1  [get_ports {count[4]}]
set_output_delay -clock clk  1  [get_ports {count[3]}]
set_output_delay -clock clk  1  [get_ports {count[2]}]
set_output_delay -clock clk  1  [get_ports {count[1]}]
set_output_delay -clock clk  1  [get_ports {count[0]}]
set_input_transition -max 0.1  [get_ports en]
set_input_transition -min 0.1  [get_ports en]
set_input_transition -max 0.1  [get_ports rst_n]
set_input_transition -min 0.1  [get_ports rst_n]
