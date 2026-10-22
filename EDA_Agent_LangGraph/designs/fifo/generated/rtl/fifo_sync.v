`timescale 1ns / 1ps

// 同步 FIFO：深度 16、位宽 8，异步低有效复位。
// 读数据为寄存器输出：rd_en 有效后的下一个周期 dout 更新。
// 满时忽略写，空时忽略读；读写同时发生时 count 不变。

module fifo_sync #(
    parameter WIDTH = 8,
    parameter DEPTH = 16,
    parameter AW    = 4
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire             wr_en,
    input  wire             rd_en,
    input  wire [WIDTH-1:0] din,
    output reg  [WIDTH-1:0] dout,
    output wire             full,
    output wire             empty,
    output reg  [AW:0]      count
);

    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [AW-1:0]    wptr;
    reg [AW-1:0]    rptr;

    assign full  = (count == DEPTH);
    assign empty = (count == 0);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wptr  <= {AW{1'b0}};
            rptr  <= {AW{1'b0}};
            count <= {(AW+1){1'b0}};
            dout  <= {WIDTH{1'b0}};
        end else begin
            if (wr_en && !full) begin
                mem[wptr] <= din;
                wptr      <= wptr + 1'b1;
            end
            if (rd_en && !empty) begin
                dout <= mem[rptr];
                rptr <= rptr + 1'b1;
            end

            case ({wr_en && !full, rd_en && !empty})
                2'b10:   count <= count + 1'b1;
                2'b01:   count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end

endmodule
