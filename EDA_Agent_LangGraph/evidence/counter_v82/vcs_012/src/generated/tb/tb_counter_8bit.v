`timescale 1ns / 1ps

// ============================================================================
// tb_counter_8bit  v3  —— 第 3 轮迭代版本
// 相对 v2 的改动（只加场景，不改判定格式）：
//   1) 窄复位脉冲：时钟高电平期间拉低 2ns 后释放，验证异步复位立即生效
//   2) 背靠背复位：连续两个周期断言复位，验证计数不会丢失或多余
//   3) 长保持：en=0 持续 50 拍，验证计数稳定
//   4) 复位与 en 同时变化：验证复位优先级高于使能
// 模块名与最终 TEST PASSED / TEST FAILED 汇总格式保持不变。
// ============================================================================

module tb_counter_8bit;

    reg         clk;
    reg         rst_n;
    reg         en;
    wire [7:0]  count;

    integer     checks;
    integer     errors;
    integer     case_id;
    integer     seed;
    integer     i;

    reg  [7:0]  model;

    counter_8bit uut (
        .clk   (clk),
        .rst_n (rst_n),
        .en    (en),
        .count (count)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    // 统一检查点
    task check;
        input [7:0] exp;
        begin
            case_id = case_id + 1;
            checks  = checks  + 1;
            if (count !== exp) begin
                errors = errors + 1;
                $display("[FAIL] #%0d t=%0t exp=%02h got=%02h", case_id, $time, exp, count);
            end else begin
                $display("[PASS] #%0d t=%0t count=%02h", case_id, $time, count);
            end
        end
    endtask

    // 一个完整时钟：上升沿采样，#1 后与参考模型比对
    task next_cycle;
        begin
            @(posedge clk);
            #1;
            if (en) model = model + 8'h01;
            check(model);
        end
    endtask

    initial begin
        checks = 0;
        errors = 0;
        case_id = 0;
        seed = 32'h00C0FFEE;
        rst_n = 1'b0;
        en = 1'b0;
        model = 8'h00;

        $display("[INFO] tb_counter_8bit v3 start");

        // ---- 1. 上电异步复位 ----
        #3;
        check(8'h00);

        // ---- 2. 复位保持（en=0） ----
        @(negedge clk);
        rst_n = 1'b1;
        repeat (3) next_cycle();

        // ---- 3. 连续计数 ----
        en = 1'b1;
        repeat (5) next_cycle();

        // ---- 4. 计数过程中异步复位 ----
        @(posedge clk);
        #2;
        rst_n = 1'b0;
        #1;
        model = 8'h00;
        check(model);
        @(negedge clk);
        rst_n = 1'b1;

        // ---- 5. en 在边沿后 1ns 翻转：本拍仍按旧值 ----
        en = 1'b1;
        @(posedge clk);
        #1;
        model = model + 8'h01;
        check(model);
        en = 1'b0;
        @(posedge clk);
        #1;
        check(model);
        en = 1'b1;

        // ---- 5a. 窄复位脉冲（2ns，夹在两个时钟沿之间） ----
        @(posedge clk);
        #3;
        rst_n = 1'b0;
        #2;
        model = 8'h00;
        check(model);               // 异步复位立即生效
        rst_n = 1'b1;
        #1;
        check(model);               // 释放后到下一沿之前应保持 0
        next_cycle();               // 下一拍正常计数

        // ---- 5b. 背靠背复位（连续两个周期断言） ----
        @(negedge clk);
        rst_n = 1'b0;
        #1;
        model = 8'h00;
        check(model);
        @(posedge clk);
        #1;
        check(model);
        @(negedge clk);
        rst_n = 1'b0;               // 再次断言
        #1;
        check(model);
        @(posedge clk);
        #1;
        check(model);
        @(negedge clk);
        rst_n = 1'b1;
        next_cycle();

        // ---- 5c. 长保持：en=0 持续 50 拍 ----
        en = 1'b0;
        repeat (50) next_cycle();
        en = 1'b1;

        // ---- 5d. 复位与 en 同时变化：复位优先 ----
        @(negedge clk);
        rst_n = 1'b0;
        en = 1'b0;
        #1;
        model = 8'h00;
        check(model);
        @(negedge clk);
        rst_n = 1'b1;
        en = 1'b1;
        next_cycle();

        // ---- 6. 递增到 0x7F 后异步复位 ----
        while (model < 8'h7F) next_cycle();
        @(posedge clk);
        #2;
        rst_n = 1'b0;
        #1;
        model = 8'h00;
        check(model);
        @(negedge clk);
        rst_n = 1'b1;
        next_cycle();

        // ---- 7. 递增到 0xFF 并验证回绕 ----
        while (model < 8'hFF) next_cycle();
        next_cycle();

        // ---- 8. 再次到 0xFF，验证满值复位 ----
        while (model < 8'hFF) next_cycle();
        @(posedge clk);
        #2;
        rst_n = 1'b0;
        #1;
        model = 8'h00;
        check(model);
        @(negedge clk);
        rst_n = 1'b1;
        next_cycle();

        // ---- 9. 随机操作（固定种子，可复现） ----
        $display("[INFO] random phase start, seed=%0d", seed);
        for (i = 0; i < 200; i = i + 1) begin
            @(negedge clk);
            en = $random(seed) & 1'b1;
            if (($random(seed) & 15) == 0) begin
                rst_n = 1'b0;
                model = 8'h00;
                #1;
                check(model);
                @(negedge clk);
                rst_n = 1'b1;
                next_cycle();
            end else begin
                rst_n = 1'b1;
                next_cycle();
            end
        end
        $display("[INFO] random phase done, seed=%0d", seed);

        // ---- 汇总 ----
        $display("======================================");
        $display(" total checks = %0d, passed = %0d, failed = %0d",
                 checks, checks - errors, errors);
        $display(" scenarios: reset, hold, increment, async_reset, en_edge,");
        $display("            reset_narrow, reset_back2back, hold_long, reset_vs_en,");
        $display("            reset_at_7f, wrap, reset_at_ff, random(seed=%0d)", seed);
        if (errors == 0) begin
            $display(" TEST PASSED");
        end else begin
            $display(" TEST FAILED (%0d errors)", errors);
        end
        $display("======================================");
        $finish;
    end

endmodule
