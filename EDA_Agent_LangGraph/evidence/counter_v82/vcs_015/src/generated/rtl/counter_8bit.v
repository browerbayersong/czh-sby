module counter_8bit (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       en,
    output reg  [7:0] count
);

    // 异步低有效复位优先；en=1 时加 1，0xFF 自动回绕至 0；en=0 时保持
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 8'h00;
        end else if (en) begin
            count <= count + 1'b1;
        end
    end

endmodule
