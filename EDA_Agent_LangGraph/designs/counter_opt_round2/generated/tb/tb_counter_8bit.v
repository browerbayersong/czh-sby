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
    integer reset_en;
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
        rst_n = 1'b1;
        en = 1'b0;
        exp_count = 8'h00;
        total_checks = 0;
        passed = 0;
        failed = 0;
        seed = 32'h12345678;

        // Round 1: assert reset at 1ns and verify clear at 2ns.
        // The first rising clock edge is at 5ns, so a synchronous-only
        // reset implementation cannot satisfy this new early check.
        #1;
        rst_n = 1'b0;
        #1;
        check_count("initial_reset_before_clk");

        // Retain the original reset check after the first rising edge.
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

        // Round 2: the reference count is now 64 (320 modulo 256).
        // Advance to 254, then hold on both sides of the wrap boundary.
        for (i = 0; i < 190; i = i + 1)
            drive_check(1'b1, "boundary_prepare_254");
        for (i = 0; i < 3; i = i + 1)
            drive_check(1'b0, "hold_at_254");
        drive_check(1'b1, "increment_254_to_255");
        for (i = 0; i < 3; i = i + 1)
            drive_check(1'b0, "hold_at_255");
        drive_check(1'b1, "wrap_255_to_0");
        for (i = 0; i < 3; i = i + 1)
            drive_check(1'b0, "hold_at_0_after_wrap");
        drive_check(1'b1, "increment_0_to_1");

        // Verify reset priority for en=0 and en=1. Prefill a nonzero
        // count before each reset; sample at 3ns after a falling edge,
        // before the next rising edge, then check reset held/released.
        for (reset_en = 0; reset_en < 2; reset_en = reset_en + 1) begin
            drive_check(1'b1, "reset_case_prefill");
            @(negedge clk);
            en = (reset_en != 0);
            #2;
            rst_n = 1'b0;
            #1;
            if (reset_en == 0)
                check_count("async_reset_en_low");
            else
                check_count("async_reset_en_high");
            @(posedge clk);
            #1;
            check_count("reset_held_over_clk");
            @(negedge clk);
            rst_n = 1'b1;
            @(posedge clk);
            #1;
            check_count("reset_release_with_en");
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
        $display("scenarios: initial_reset_before_clk, initial_async_reset, hold, consecutive_increment_wrap, boundary_holds_254_255_0, wrap_255_to_0, reset_en_low, reset_en_high, async_reset_during_run, random_en");
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
