# AI 辅助 DRC 诊断与修复的案例证据核对

2026年10月26日，仅执行只读核查和文件回收，没有启动 ICC，没有改动基线数据库，也没有调用 DeepSeek 进行修复。

## 基线与原始文件

所选远端运行：`upload_20261025_143839_f96edb1f`，本地原始工具结果为 `designs/counter_backend/session_queue/result_131/`。

- 原始布线检查：`build/icc/routing_drc.rpt`。36 条网络，0 开路，0 未放置单元，1 处 DRC。
- 完整日志与状态：`build/icc.log`、`build/icc.status.json`。工具退出码 2，不能标成全通过。
- 违规详情：`session_queue/result_112/build/display/drc_details.txt`。该证据来自后来只读打开同一数据库，不是重新布局布线的结果。
- 原始脚本已回收至 `session_queue/result_155/src/generated/scripts/`，包括 config.tcl、constraints.tcl、icc_layout_only.tcl、icc_place_route.tcl、prepare_rc_model.py。全部与当次 snapshot_manifest.json 的 SHA-256 一致。
- 原始主 Tcl 的 SHA-256：`a369858282d7e1ebe3d38269f1cf0880f66171f89a55af29782a35db7d861b17`。
- 当前工作区主 Tcl 与原始版不同，应在案例中保留两者及 diff，不得将当前版描述为当次执行脚本。

## 本次存在性确认

核实结果为 `session_queue/result_154`，Milkyway 根目录及 CEL 目录分别在 result_156 与 result_157。所有 11 个指定路径均存在，CEL 中有实际的 `counter_8bit:1` 和附属数据；本次只核对元数据，没有重新打开 ICC 验证可载入性。

远端运行根目录：
`/home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261025_143839_f96edb1f`

- 物理数据库：上述根目录下 `build/icc/counter_mw`。
- 运行内技术文件：上述根目录下 `build/icc/derived_tech.tf`。
- 原始技术文件：`/opt/Foundary_Library/TSMC90/aci/sc-x/astro/tf/tsmc090_6lm_1thick.tf`。
- 物理参考库：`/opt/Foundary_Library/TSMC90/aci/sc-x/astro/tsmc090g_fram`。
- 逻辑库：`/opt/Foundary_Library/TSMC90/aci/sc-x/synopsys/typical.db`。
- LEF 技术文件与 GDS 层映射同样存在，具体路径见 result_154。

工艺库载荷没有复制进材料包；记录路径、元数据和先前保存的来源哈希。

## 诊断应区分的问题

1. **真实物理违规**：M1 Diff net spacing，网络 count[5] 与 N7，标记框 `(8.270,16.625)-(8.405,17.040)` μm。现有 actual_spacing、required_spacing 字段为空，不可猜测尺寸或把 DRC 标记框当作真实导线几何。
2. **原始报告解析缺陷**：原 Tcl 的 `regexp -nocase {error[ :]}` 会匹配 PG 报告中的 `Create error cell`。PG 检查实际为 2 条网络、0 错误，因此原始 EDA_FATAL 的触发原因与 spacing 违规不是同一个问题。当前脚本已经修改该规则并增加 DRC 数量验收，不可算作本次新开发的 AI 修复。
3. **库一致性风险**：日志 71—84 行附近有 MWLIBP-300/301/324，主库 6 层与参考库 9 层不一致，另有 M1 pitch 警告。需要调查，不足以直接证明是这处违规的根因。
4. **已有失败尝试**：当前 icc_eco_spacing.tcl 属于后续 ECO 实验，result_127 最终为 7 处 DRC，不能当成成功补丁。

## 功能拓展的可行路径

先建立 LangGraph 诊断流程，输入实际报告、结构化违规、上下文和工具版本。DeepSeek 输出诊断依据、缺失信息、候选受限 Tcl 及验证计划。补充局部导线、引脚、过孔和适用规则后，在新复制的 Milkyway 库尝试候选操作，使用 ICC 真实 DRC、开路、PG/LVS 与放置合法性结果决定保留或回退。

DRC 清零且其他检查不退化才可记录为该案例修复成功。不要降低规则、删除违规标记或修改 RTL 来掩盖物理问题。若候选改变逻辑连接或单元，需要增加对应逻辑复核。

缺少 TLU+ 与这个 spacing 诊断任务分开记录；可以先研究当前 ICC 内置布线检查，但不能据此宣称详细寄生、时序功耗签核完成。
