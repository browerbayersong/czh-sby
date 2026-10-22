`timescale 1ns / 1ps

// fifo_sync 的参考模型验证平台。
// 模型维护队列内容、读写指针与计数，逐拍与 DUT 比对 count/full/empty/dout。
// 覆盖：复位、写入、读出、写满、读空、同时读写、随机 300 拍。

module tb_fifo_sync;

    localparam WIDTH = 8;
    localparam DEPTH = 16;

    reg              clk;
    reg              rst_n;
    reg              wr_en;
    reg              rd_en;
    reg  [WIDTH-1:0] din;
    wire [WIDTH-1:0] dout;
    wire             full;
    wire             empty;
    wire [4:0]       count;

    integer checks;
    integer errors;
    integer case_id;
    integer seed;
    integer i;

    reg  [WIDTH-1:0] mem_m [0:DEPTH-1];
    reg  [3:0]       wptr_m;
    reg  [3:0]       rptr_m;
    integer          count_m;
    reg  [WIDTH-1:0] exp_dout;


    fifo_sync dut (
        .clk   (clk),
        .rst_n (rst_n),
        .wr_en (wr_en),
        .rd_en (rd_en),
        .din   (din),
        .dout  (dout),
        .full  (full),
        .empty (empty),
        .count (count)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    task check;
        reg exp_full;
        reg exp_empty;
        begin
            exp_full  = (count_m == DEPTH);
            exp_empty = (count_m == 0);
            case_id = case_id + 1;
            checks  = checks + 1;
            if ((count !== count_m[4:0]) || (full !== exp_full) || (empty !== exp_empty) ||
                (dout !== exp_dout)) begin
                errors = errors + 1;
                $display("[FAIL] #%0d t=%0t cnt=%0d/%0d full=%b/%b empty=%b/%b dout=%02h/%02h",
                         case_id, $time, count, count_m, full, exp_full, empty, exp_empty,
                         dout, exp_dout);
            end else begin
                $display("[PASS] #%0d t=%0t cnt=%0d", case_id, $time, count);
            end
        end
    endtask

    task do_cycle;
        reg rd_ok;
        reg wr_ok;
        begin
            @(posedge clk);
            #1;
            rd_ok = rd_en && (count_m != 0);
            wr_ok = wr_en && (count_m != DEPTH);
            if (rd_ok) begin
                exp_dout = mem_m[rptr_m];
                rptr_m   = rptr_m + 4'd1;
                count_m  = count_m - 1;
            end
            if (wr_ok) begin
                mem_m[wptr_m] = din;
                wptr_m        = wptr_m + 4'd1;
                count_m       = count_m + 1;
            end
            check;
        end
    endtask

    task model_reset;
        begin
            for (i = 0; i < DEPTH; i = i + 1) mem_m[i] = {WIDTH{1'b0}};
            wptr_m   = 4'd0;
            rptr_m   = 4'd0;
            count_m  = 0;
            exp_dout = {WIDTH{1'b0}};
        end
    endtask

    initial begin
        checks  = 0;
        errors  = 0;
        case_id = 0;
        seed    = 32'h00C0FFEE;
        rst_n   = 1'b0;
        wr_en   = 1'b0;
        rd_en   = 1'b0;
        din     = {WIDTH{1'b0}};

        $display("[INFO] tb_fifo_sync start");

        // ---- 1. 上电异步复位 ----
        #3;
        model_reset;
        check;

        @(negedge clk);
        rst_n = 1'b1;

        // ---- 2. 写入 5 个 ----
        for (i = 0; i < 5; i = i + 1) begin
            @(negedge clk);
            wr_en = 1'b1;
            rd_en = 1'b0;
            din   = i[7:0] + 8'h10;
            do_cycle();
        end

        // ---- 3. 读出 3 个（检查 FIFO 顺序） ----
        for (i = 0; i < 3; i = i + 1) begin
            @(negedge clk);
            wr_en = 1'b0;
            rd_en = 1'b1;
            do_cycle();
        end

        // ---- 4. 写满 ----
        while (count_m < DEPTH) begin
            @(negedge clk);
            wr_en = 1'b1;
            rd_en = 1'b0;
            din   = 8'hA0 + count_m[7:0];
            do_cycle();
        end

        // ---- 5. 满时继续写：应被忽略 ----
        @(negedge clk);
        wr_en = 1'b1;
        rd_en = 1'b0;
        din   = 8'h5A;
        do_cycle();

        // ---- 6. 全部读出 ----
        while (count_m > 0) begin
            @(negedge clk);
            wr_en = 1'b0;
            rd_en = 1'b1;
            do_cycle();
        end

        // ---- 7. 空时继续读：应被忽略 ----
        @(negedge clk);
        wr_en = 1'b0;
        rd_en = 1'b1;
        do_cycle();

        // ---- 8. 同时读写 ----
        for (i = 0; i < 6; i = i + 1) begin
            @(negedge clk);
            wr_en = 1'b1;
            rd_en = 1'b0;
            din   = 8'h30 + i[7:0];
            do_cycle();
        end
        for (i = 0; i < 4; i = i + 1) begin
            @(negedge clk);
            wr_en = 1'b1;
            rd_en = 1'b1;
            din   = 8'h60 + i[7:0];
            do_cycle();
        end

        // ---- 9. 随机 300 拍 ----
        $display("[INFO] random phase start, seed=%0d", seed);
        for (i = 0; i < 300; i = i + 1) begin
            @(negedge clk);
            wr_en = $random(seed) & 1'b1;
            rd_en = $random(seed) & 1'b1;
            din   = $random(seed);
            do_cycle();
        end
        $display("[INFO] random phase done, seed=%0d", seed);

        // ---- 汇总 ----
        $display("======================================");
        $display(" total checks = %0d, passed = %0d, failed = %0d",
                 checks, checks - errors, errors);
        $display(" scenarios: reset, write, read_order, fill, write_when_full,");
        $display("            drain, read_when_empty, simultaneous, random(seed=%0d)", seed);
        if (errors == 0) begin
            $display(" TEST PASSED");
        end else begin
            $display(" TEST FAILED (%0d errors)", errors);
        end
        $display("======================================");
        $finish;
    end

endmodule
