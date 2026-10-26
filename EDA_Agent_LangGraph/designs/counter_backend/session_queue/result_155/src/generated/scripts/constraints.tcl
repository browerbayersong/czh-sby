# Units are ns and pF in the verified typical library. Clock matches the RTL TB.
create_clock -name clk -period $EDA_CLOCK_PERIOD -waveform {0 5} [get_ports clk]
set_clock_uncertainty $EDA_CLOCK_UNCERTAINTY [get_clocks clk]
set_clock_transition $EDA_INPUT_TRANSITION [get_clocks clk]
set_input_delay $EDA_INPUT_DELAY -clock clk [get_ports en]
set_input_transition $EDA_INPUT_TRANSITION [get_ports {en rst_n}]
set_output_delay $EDA_OUTPUT_DELAY -clock clk [all_outputs]
set_load $EDA_OUTPUT_LOAD [all_outputs]
# Asynchronous reset assertion is not a data path. Reset deassertion recovery and
# removal are outside this single-clock educational experiment's timing scope.
set_false_path -from [get_ports rst_n]
