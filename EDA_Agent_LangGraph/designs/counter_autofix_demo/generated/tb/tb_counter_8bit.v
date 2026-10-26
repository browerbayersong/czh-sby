`timescale 1ns/1ps

module tb_counter_8bit;

    reg        clk;
    reg        rst_n;
    reg        en;
    wire [7:0] count;

    reg [7:0] exp_count;
    integer total_checks;
    integer passed;
    integer failed;
    integer i;
    integer seed;

    // DUT
    counter_8bit u_dut (
        .clk   (clk),
        .rst_n (rst_n),
        .en    (en),
        .count (count)
    );

    // 10ns period clock
    initial clk = 1'b0;
    always #5 clk = ~clk;

    // Independent reference model; does not read DUT count
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            exp_count <= 8'h00;
        else if (en)
            exp_count <= exp_count + 8'h01;
    end

    task check_count;
        input [255:0] name;
        begin
            total_checks = total_checks + 1;
            if (count === exp_count) begin
                passed = passed + 1;
                $display("[PASS] %0s: count=%0d expected=%0d", name, count, exp_count);
            end else begin
                failed = failed + 1;
                $display("[FAIL] %0s: count=%0d expected=%0d", name, count, exp_count);
            end
        end
    endtask

    task drive_check;
        input next_en;
        input [255:0] name;
        begin
            @(negedge clk);
            en = next_en;
            @(posedge clk);
            #1;
            check_count(name);
        end
    endtask

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        en = 1'b0;
        exp_count = 8'h00;
        total_checks = 0;
        passed = 0;
        failed = 0;
        seed = 32'h12345678;

        // Initial asynchronous reset: first rising edge clears counter
        @(posedge clk);
        #1;
        check_count("initial_async_reset");

        // Release reset and check hold (en=0)
        @(negedge clk);
        rst_n = 1'b1;
        en = 1'b0;
        @(posedge clk);
        #1;
        check_count("hold_after_reset");

        // 320 consecutive increments: covers 255->0 wrap
        for (i = 0; i < 320; i = i + 1) begin
            drive_check(1'b1, "consecutive_increment_wrap");
        end

        // Asynchronous reset during run, applied away from rising edge
        @(negedge clk);
        #2; // clk is low, not a rising edge
        rst_n = 1'b0;
        #1; // check clear before next clk edge
        check_count("async_reset_clear_before_clk_edge");

        // Release reset on a falling edge, hold with en=0
        @(negedge clk);
        rst_n = 1'b1;
        en = 1'b0;
        @(posedge clk);
        #1;
        check_count("hold_after_async_reset");

        // 500 fixed-seed random enable cycles
        for (i = 0; i < 500; i = i + 1) begin
            @(negedge clk);
            en = $random(seed);
            @(posedge clk);
            #1;
            check_count("random_en");
        end

        $display("total checks = %0d, passed = %0d, failed = %0d",
                 total_checks, passed, failed);
        $display("scenarios: initial_async_reset, hold, consecutive_increment_wrap, async_reset_during_run, random_en");
        if (failed == 0)
            $display("TEST PASSED");
        else
            $display("TEST FAILED");
        $finish;
    end

    // Independent simulation timeout
    initial begin
        #1000000;
        $display("[FAIL] timeout: simulation exceeded 1ms");
        total_checks = total_checks + 1;
        failed = failed + 1;
        $display("total checks = %0d, passed = %0d, failed = %0d",
                 total_checks, passed, failed);
        $display("scenarios: timeout");
        $display("TEST FAILED");
        $finish;
    end

endmodule
