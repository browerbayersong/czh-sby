// counter_8bit.v - 8-bit unsigned up counter with asynchronous active-low reset
// Specification:
//   - posedge clk counting
//   - rst_n asynchronous, active low: count cleared to 8'h00
//   - en = 0: hold, en = 1: count + 1
//   - wraps from 255 to 0
`timescale 1ns/1ps

module counter_8bit (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       en,
    output reg  [7:0] count
);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 8'h00;
        end else if (en) begin
            count <= count + 8'h01;
        end
        // else: en == 0, hold current value
    end

endmodule
