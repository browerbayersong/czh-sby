# LangGraph 与 DeepSeek 辅助 DRC 修复

2026年10月26日真实实跑：初版 1 处 DRC → 模型第 1 轮 2 处且出现短路，拒绝 → 模型第 2 轮 0 处，检查通过。保存数据库重新打开后独立复查也为 0。

## 实现与执行

入口 `code/drc_ai_repair.py` 使用真实 StateGraph，节点为 diagnose_and_propose、execute_copy、verify_actual_reports。复查节点通过条件边结束或继续，最多 4 轮，本次第 2 轮结束。

DeepSeek 返回结构化候选参数，固定模板生成 Tcl，拒绝任意命令字段。所有候选从同一原始库重新复制，失败副本保留证据但不采纳。未修改 RTL、规则或原版数据库，没有将旧脚本的 PG 报告误判修正冒充本次物理修复。

真实模型返回名为 deepseek-flash；系统提示词、逐轮实际用户输入、原始响应、用量元数据、JSON 计划、生成 Tcl、workflow.mmd 与 history.json 均在 `20261026_ai_01/`。这些内容和原始工具日志才是本次实跑证据；测试中的模拟夹具仅用于离线验收逻辑检查。

成功策略：`ripup_pair`、`pin_taper_mode=off`、`extra_pin_tracks=false`。完整拆除 count[5] 与 N7 的信号布线后 ECO，允许工具寻找新的引脚接入路径。这些选项改变候选几何，不关闭规则检查。

## 原始结果位置

- 基线：result_131，运行 upload_20261025_143839_f96edb1f。
- 几何上下文：result_161、result_164。
- 第一轮失败：result_171，运行 upload_20261026_130022_aadb30fa，DRC 2，LVS 短路 1。
- 第二轮成功：result_177，运行 upload_20261026_130102_35ef2344。
- 成功 Tcl 与当次快照清单：result_185，SHA-256 已校验。
- 保存后独立命令行复查：result_184，运行 upload_20261026_131119_06234e60，退出码 0。
- 实际 GUI 与终端截图：result_180。GUI 任务在输出后等待退出，被 90 秒时限终止，最终状态在 result_181；该界面任务不能写为正常完成。采用独立命令行复查判定保存后的结果。
- 汇总：`../drc_ai_verified.json`，包含验收条件、失败轮、持久化复查及适用范围。

修复后的物理数据库：
`/home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261026_130102_35ef2344/build/drc_ai/counter_mw`

## 验收与限制

检查 36 条网络，DRC、开路和未放置单元均为 0；2 条电源网络错误为 0；LVS 六项和放置合法性十二项计数均为 0。去除注释及空白差异后的实际 Verilog 文本、单元名称与型号清单一致，修复后输出了 GDS、网表和 SDC。该文本一致性检查不作为通用逻辑等价验证器宣传。

当前结论为现有技术设置下的 ICC 内置布线检查通过，不是晶圆厂完整签核。技术库与参考库的一致性警告仍存在；天线规则未定义；详细 TLU+/SPEF 与修复布线后的 PT 没有运行。前面旧的 PT 统计估算不能冒充修复后布线提取结果。

## 复现实验

保持 EDA 虚拟机开启，重新确认地址，并启动 `backend_session.py --host <IP> --fresh-session`，密码在本机输入。随后从 Windows 项目 code 目录运行：

```powershell
.\venv\Scripts\python.exe -u drc_ai_repair.py `
  --context ..\designs\counter_backend\drc_ai\context.txt `
  --output ..\designs\counter_backend\drc_ai\新的独立目录 `
  --rounds 4
```

这会重新调用模型并创建新副本，不保证随机路由结果与本次逐字节一致。不要为了展示而重复运行已通过的实验；已有原始证据可直接复核。仅在需要新实验时执行。
