// Intentional fault injection for automatic-repair acceptance.
// Required behavior: asynchronous active-low reset, hold when en=0,
// increment when en=1, wrap at 255. The en gating is deliberately missing.
// This is an isolated experiment; counter_first_run is the passing baseline.
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
        end else begin
            count <= count + 8'h01;
        end
    end

endmodule
