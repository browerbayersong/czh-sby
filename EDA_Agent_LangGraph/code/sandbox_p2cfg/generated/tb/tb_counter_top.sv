`timescale 1ns/1ps

module tb_counter_top;
    logic clk = 1'b0;
    logic rst_n = 1'b0;
    logic en = 1'b0;
    logic [pkg_defs::DW-1:0] count;

    int checks = 0;
    int errors = 0;
    logic [pkg_defs::DW-1:0] exp_count;

    counter_top dut (.clk(clk), .rst_n(rst_n), .en(en), .count(count));

    always #5 clk = ~clk;

    task automatic check(input logic [pkg_defs::DW-1:0] want);
        checks = checks + 1;
        if (count === want) begin
            $display("[PASS] #%0d t=%0t count=%02h", checks, $time, count);
        end else begin
            errors = errors + 1;
            $display("[FAIL] #%0d t=%0t exp=%02h got=%02h", checks, $time, want, count);
        end
    endtask

    initial begin
`ifdef SIM_CFG
        $display("[INFO] compile with SIM_CFG");
`endif
`ifdef FROM_F
        $display("[INFO] compile with FROM_F from files.f");
`endif
        exp_count = '0;
        // 复位
        #2 rst_n = 1'b0;
        #3;
        check(exp_count);
        // 释放复位后保持
        @(negedge clk); rst_n = 1'b1; en = 1'b0;
        repeat (3) begin
            @(posedge clk); #1;
            check(exp_count);
        end
        // 使能递增
        en = 1'b1;
        repeat (20) begin
            @(posedge clk); #1;
            exp_count = exp_count + 1'b1;
            check(exp_count);
        end
        // 关闭使能后保持
        en = 1'b0;
        repeat (2) begin
            @(posedge clk); #1;
            check(exp_count);
        end

        $display(" total checks = %0d, passed = %0d, failed = %0d",
                 checks, checks - errors, errors);
        $display(" scenarios: reset, hold, increment, disable_hold");
        if (errors == 0) $display(" TEST PASSED");
        else             $display(" TEST FAILED (%0d errors)", errors);
        $finish;
    end

    initial begin
        #100000;
        $display(" TIMEOUT");
        $finish;
    end
endmodule
