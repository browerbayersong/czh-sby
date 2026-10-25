`include "cfg.vh"

module counter_top (
    input  logic                   clk,
    input  logic                   rst_n,
    input  logic                   en,
    output logic [pkg_defs::DW-1:0] count
);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)      count <= `RST_VAL;
        else if (en)     count <= count + 1'b1;
    end
endmodule
