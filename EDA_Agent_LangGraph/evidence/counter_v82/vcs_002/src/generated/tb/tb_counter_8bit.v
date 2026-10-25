`timescale 1ns / 1ps

module tb_counter_8bit;

    // Inputs to DUT
    reg clk;
    reg rst_n;
    reg en;

    // Output from DUT
    wire [7:0] count;

    // Instantiate the Unit Under Test (UUT)
    counter_8bit uut (
        .clk(clk),
        .rst_n(rst_n),
        .en(en),
        .count(count)
    );

    // Clock generation: 10 ns period (5 ns high, 5 ns low)
    initial clk = 0;
    always #5 clk = ~clk;

    // Error counter
    integer errors = 0;

    // Task to check count after a clock edge (synchronous check)
    task check_count;
        input [7:0] expected;
        begin
            #1; // small delay after clock edge
            if (count !== expected) begin
                $display("ERROR at time %0t: expected %0h, got %0h", $time, expected, count);
                errors = errors + 1;
            end else begin
                $display("OK at time %0t: count = %0h", $time, count);
            end
        end
    endtask

    // Task to check count immediately after asynchronous reset assertion
    task check_async_reset;
        input [7:0] expected;
        begin
            #2; // allow async reset to propagate
            if (count !== expected) begin
                $display("ERROR at time %0t (async reset): expected %0h, got %0h", $time, expected, count);
                errors = errors + 1;
            end else begin
                $display("OK at time %0t (async reset): count = %0h", $time, count);
            end
        end
    endtask

    initial begin
        // Initialize inputs
        rst_n = 0;
        en = 0;

        // Test 1: Asynchronous reset while rst_n is low
        repeat (3) @(posedge clk);
        $display("Check: reset (rst_n=0) -> count should be 0");
        check_count(8'h00);

        // Release reset, keep en=0
        @(negedge clk);
        rst_n = 1;
        en = 0;

        // Test 2: Hold with en=0
        repeat (3) @(posedge clk);
        $display("Check: hold (en=0) -> count should remain 0");
        check_count(8'h00);

        // Enable counting
        @(negedge clk);
        en = 1;
        $display("Check: continuous counting from 0 to 255 and wraparound");

        // Test 3: Continuous counting from 0 to 255
        begin : continuous_count_loop
            integer i;
            for (i = 1; i <= 255; i = i + 1) begin
                @(posedge clk);
                check_count(i); // i is integer, truncated to 8 bits (1..255)
            end
        end

        // Test 4: Wraparound from 0xFF to 0x00
        @(posedge clk);
        $display("Check: wraparound (0xFF + 1) -> count should be 0");
        check_count(8'h00);

        // Test 5: Asynchronous reset during active counting
        repeat (4) @(posedge clk); // now count should be 4
        $display("Check: async reset during counting -> count should immediately become 0");
        #3; // move away from clock edge to avoid race
        rst_n = 0;
        check_async_reset(8'h00);

        // Release reset, en still 1
        @(negedge clk);
        rst_n = 1;

        // Test 6: Counting resumes after reset release
        repeat (2) @(posedge clk);
        $display("Check: after reset release -> count should be 2");
        check_count(8'h02);

        // Final result
        if (errors == 0) begin
            $display("======================================");
            $display(" TEST PASSED");
            $display("======================================");
        end else begin
            $display("======================================");
            $display(" TEST FAILED (%0d errors)", errors);
            $display("======================================");
        end

        $finish;
    end

endmodule
