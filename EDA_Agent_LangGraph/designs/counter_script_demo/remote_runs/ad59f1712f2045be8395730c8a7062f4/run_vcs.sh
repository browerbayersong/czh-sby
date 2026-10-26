#!/bin/bash
set -euo pipefail

# Compile the existing counter RTL and testbench with VCS 2014.03.
timeout 300s /opt/Synopsys/VCS2014/bin/vcs \
    -full64 \
    -sverilog \
    -timescale=1ns/1ps \
    -cm line+cond+fsm+tgl+branch \
    -cm_dir ../build/cov.vdb \
    -top tb_counter_8bit \
    -o ../build/simv \
    generated/rtl/counter_8bit.v \
    generated/tb/tb_counter_8bit.v \
    > ../build/vcs_compile.log 2>&1

# Run the simulation and collect coverage into the same coverage database.
timeout 120s ../build/simv \
    -cm line+cond+fsm+tgl+branch \
    -cm_dir ../build/cov.vdb \
    > ../build/vcs_sim.log 2>&1

# Generate the text coverage report.
timeout 120s /opt/Synopsys/VCS2014/bin/urg \
    -dir ../build/cov.vdb \
    -format text \
    -report ../build/covReport \
    > ../build/urg.log 2>&1
