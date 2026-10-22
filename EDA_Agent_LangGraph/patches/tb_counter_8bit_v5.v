`timescale 1ns / 1ps

// ============================================================================
// tb_counter_8bit  v5  —— 第 4 次优化
// 相对 v4 的改动：
//   1) 新增负向测试：故意给错误期望值，验证比较器能捕获（errors 必须 +1），
//      随后清零，因此整轮仍然 TEST PASSED
//   2) 意图性失败打印 [XFAIL] 而非 [FAIL]，不会污染流水线的失败判定
//   3) 功能覆盖点增加到 11 个（新增 negative_check）
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
    integer     s;
    integer     cov_bins [0:10];
    integer     bin_total;
    integer     expect_fail;

    reg  [7:0]  model;

    counter_8bit uut (
        .clk   (clk),
        .rst_n (rst_n),
        .en    (en),
        .count (count)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    task hit;
        input integer id;
        begin
            cov_bins[id] = cov_bins[id] + 1;
        end
    endtask

    task check;
        input [7:0] exp;
        begin
            case_id = case_id + 1;
            checks  = checks  + 1;
            if (count !== exp) begin
                errors = errors + 1;
                if (expect_fail) begin
                    $display("[XFAIL] #%0d t=%0t exp=%02h got=%02h (intentional)",
                             case_id, $time, exp, count);
                end else begin
                    $display("[FAIL] #%0d t=%0t exp=%02h got=%02h",
                             case_id, $time, exp, count);
                end
            end else begin
                $display("[PASS] #%0d t=%0t count=%02h", case_id, $time, count);
            end
        end
    endtask

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
        expect_fail = 0;
        for (i = 0; i < 11; i = i + 1) cov_bins[i] = 0;

        $display("[INFO] tb_counter_8bit v5 start");

        // ---- 1. 上电异步复位 ----
        #3;
        hit(0);
        check(8'h00);

        // ---- 2. 复位保持（en=0） ----
        @(negedge clk);
        rst_n = 1'b1;
        hit(1);
        repeat (3) next_cycle();

        // ---- 3. 连续计数 ----
        en = 1'b1;
        hit(2);
        repeat (5) next_cycle();

        // ---- 4. 计数过程中异步复位 ----
        @(posedge clk);
        #2;
        rst_n = 1'b0;
        #1;
        model = 8'h00;
        hit(4);
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

        // ---- 5a. 窄复位脉冲（2ns） ----
        @(posedge clk);
        #3;
        rst_n = 1'b0;
        #2;
        model = 8'h00;
        hit(5);
        check(model);
        rst_n = 1'b1;
        #1;
        check(model);
        next_cycle();

        // ---- 5b. 背靠背复位 ----
        @(negedge clk);
        rst_n = 1'b0;
        #1;
        model = 8'h00;
        hit(6);
        check(model);
        @(posedge clk);
        #1;
        check(model);
        @(negedge clk);
        rst_n = 1'b0;
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
        hit(7);
        repeat (50) next_cycle();
        en = 1'b1;

        // ---- 5d. 复位与 en 同时变化 ----
        @(negedge clk);
        rst_n = 1'b0;
        en = 1'b0;
        #1;
        model = 8'h00;
        hit(8);
        check(model);
        @(negedge clk);
        rst_n = 1'b1;
        en = 1'b1;
        next_cycle();

        // ---- 5e. en=1 时在 0x00 处复位 ----
        @(posedge clk);
        #1;
        model = model + 8'h01;
        check(model);
        rst_n = 1'b0;
        #1;
        model = 8'h00;
        hit(4);
        check(model);
        @(negedge clk);
        rst_n = 1'b1;
        next_cycle();

        // ---- 5f. 负向测试：验证比较器能捕获错误 ----
        // 用"减一"代替"判断后清零"：比较器若未触发，errors 会变 -1，
        // 最终 errors == 0 判定自然失败，从而避免引入不可达的 else 分支。
        expect_fail = 1;
        check(model + 8'h01);          // 故意给错误的期望值
        expect_fail = 0;
        $display("[INFO] negative check injected error count = %0d (expect 1)", errors);
        errors = errors - 8'd1;
        hit(10);

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
        hit(3);

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

        // ---- 9. 随机操作：3 个种子 × 100 次 ----
        for (s = 0; s < 3; s = s + 1) begin
            seed = 32'h00C0FFEE + s * 32'h00000101;
            $display("[INFO] random phase %0d start, seed=%0d", s, seed);
            for (i = 0; i < 100; i = i + 1) begin
                @(negedge clk);
                en = $random(seed) & 1'b1;
                if (($random(seed) & 15) == 0) begin
                    rst_n = 1'b0;
                    model = 8'h00;
                    #1;
                    hit(9);
                    check(model);
                    @(negedge clk);
                    rst_n = 1'b1;
                    next_cycle();
                end else begin
                    rst_n = 1'b1;
                    next_cycle();
                end
            end
        end
        $display("[INFO] random phase done");

        // ---- 功能覆盖统计 ----
        bin_total = 0;
        for (i = 0; i < 11; i = i + 1) begin
            if (cov_bins[i] > 0) bin_total = bin_total + 1;
            $display("[INFO] bin[%0d] = %0d", i, cov_bins[i]);
        end
        $display("[INFO] functional coverage = %0d/11 bins", bin_total);

        // ---- 汇总 ----
        $display("======================================");
        $display(" total checks = %0d, passed = %0d, failed = %0d",
                 checks, checks - errors, errors);
        $display(" scenarios: reset, hold, increment, wrap, async_reset,");
        $display("            en_edge, reset_narrow, reset_back2back, hold_long,");
        $display("            reset_vs_en, reset_at_7f, reset_at_ff, negative_check,");
        $display("            random x3");
        $display(" functional bins hit = %0d/11", bin_total);
        if (errors == 0) begin
            $display(" TEST PASSED");
        end else begin
            $display(" TEST FAILED (%0d errors)", errors);
        end
        $display("======================================");
        $finish;
    end

endmodule
