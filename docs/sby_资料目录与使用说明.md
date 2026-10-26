# sby 分支资料目录与使用说明

本说明对应 2026 年 10 月 26 日整理的课程设计材料。路径均相对于仓库根目录。原始框架来自 chenzhaoho/czh；本次在原项目上加入真实 VCS/DC/ICC/PT 实验记录及 AI 辅助 DRC 修复，保留上游 P2 更新。旧文档带有各自历史日期，当前结果以根目录 README 和本说明为准。

## 一 报告与截图

| 文件或目录 | 用途 |
| --- | --- |
| `reports/EDA课程设计报告_AI修复补充版.docx` | 新报告，包含 DRC 修复流程、两轮实际结果、真实截图和适用范围。优先阅读这一版。 |
| `reports/EDA课程设计报告_现有基础稿.docx` | 补充前的用户当前稿，作为历史对照保留。 |
| `reports/screenshots/VCS/` | FIFO 复现、计数器生成、自动纠错、三轮测试增强和模型生成脚本的实际终端截图。 |
| `reports/screenshots/DRC_AI/before.png` | 初版 DRC 为 1 的原始报告节选截图。 |
| `reports/screenshots/DRC_AI/after.png` | 保存后的修复数据库重新打开，DRC 为 0 的报告节选截图。 |
| `reports/screenshots/DRC_AI/layout.png` | 修复副本的真实 ICC 版图界面。 |

截图用于展示，完整原始报告用于复核。个人信息及个人心得栏位沿用现有稿，仍需本人完善。旧报告的残余违规描述是修复前结果，不能据此认定修复副本仍有 1 处违规。

## 二 新增 AI DRC 修复功能

| 文件 | 用途 |
| --- | --- |
| `EDA_Agent_LangGraph/code/drc_ai_repair.py` | 新功能入口。StateGraph 组织诊断与方案选择、复制执行、真实报告验收，并在失败后反馈给模型重试。 |
| `EDA_Agent_LangGraph/code/test_drc_ai_repair.py` | 离线测试：拒绝任意命令字段、缺失验收证据不通过、网表变化不误判一致。测试夹具不是 EDA 实跑证据。 |
| `EDA_Agent_LangGraph/designs/counter_backend/drc_ai/README.md` | 实现、实验顺序、原始结果索引与复现步骤。 |
| `EDA_Agent_LangGraph/designs/counter_backend/drc_ai/context.txt` | 本案例实际提供给模型的初始几何及违规上下文。 |
| `EDA_Agent_LangGraph/designs/counter_backend/drc_ai/20261026_ai_01/` | 本次两轮真实运行的模型输入、响应、元数据、候选脚本和图状态。 |
| `EDA_Agent_LangGraph/designs/counter_backend/drc_ai_verified.json` | 从工具报告重新核对的成功摘要、独立复查结果和限制。 |

`20261026_ai_01` 内各文件的含义：

| 文件名 | 用途 |
| --- | --- |
| `system_prompt.txt` | 实际系统提示词，明确候选操作范围。 |
| `context.txt` | 该次图运行保存的原始案例上下文。 |
| `round_01_request.txt`、`round_02_request.txt` | 每轮完整用户输入；第二轮含第一轮真实失败反馈。 |
| `round_01_response.txt`、`round_02_response.txt` | DeepSeek 原始文本响应。 |
| `round_01_metadata.json`、`round_02_metadata.json` | API 返回的模型、响应标识和用量等元数据，不含密钥。 |
| `round_01_plan.json`、`round_02_plan.json` | 经过参数校验的结构化候选策略。 |
| `drc_ai_candidate_20261026_ai_01_01.tcl`、`drc_ai_candidate_20261026_ai_01_02.tcl` | 根据各轮模型参数生成并执行的固定模板 Tcl。第二个是通过的候选。 |
| `history.json` | 两轮方案、远端运行标识与实际验收结果，包括失败轮。 |
| `final.json` | LangGraph 最终状态及成功副本位置。 |
| `workflow.mmd` | 从实际编译图导出的 Mermaid 工作流。 |

模型选择的是受限策略和参数，由程序生成 Tcl；不是让模型执行任意 shell。第一轮失败副本不被采纳，第二轮重新从原始库复制。此次未移动单元、未修改 RTL 或工艺规则。

## 三 复制出来的修复文件与数据库

仓库根目录 `drc_ai/` 是从虚拟机修复目录复制出的工作结果，和上面的 Python 功能目录不同。

| 文件或目录 | 用途 |
| --- | --- |
| `drc_ai/counter_mw/` | 修复后的 Milkyway 工作数据库。需 Linux ICC 和匹配参考库，不是普通文本项目。 |
| `drc_ai/counter_mw/lib`、`lib_1`、`lib_bck` | Milkyway 库元数据及工具保存的辅助/备份数据，复制时保留。 |
| `drc_ai/counter_mw/CEL/` | `counter_8bit` 单元的物理数据库及附属数据。 |
| `drc_ai/counter_mw/err/` | 工具保存的检查结果对象，不要仅按文件名推断当前是否有错误；以实际检查计数为准。 |
| `drc_ai/counter_8bit.gds` | 修复后的版图导出。 |
| `drc_ai/counter_8bit.routed.v` | 修复后的网表。 |
| `drc_ai/counter_8bit.sdc` | 对应约束。 |
| `drc_ai/before_drc.rpt` | 在副本上修复前检查，复现基线 1 处 DRC。 |
| `drc_ai/routing_drc.rpt` | 修复后布线报告，36 条网络、DRC 0、开路 0。 |
| `drc_ai/pg_connectivity.rpt` | 电源网络检查，2 条网络、错误 0。 |
| `drc_ai/lvs.rpt` | ICC 内置连通性检查，六项错误计数为 0。 |
| `drc_ai/placement_legality.rpt` | 放置合法性报告，固定及非固定单元的十二项错误计数为 0。 |
| `drc_ai/netlist_before.v`、`netlist_after.v` | 修复前后导出的网表，用于规范化文本一致性比较。 |
| `drc_ai/cell_inventory_before.txt`、`cell_inventory_after.txt` | 单元名称与型号清单，用于检查是否改变逻辑单元。 |
| `drc_ai/drc_details.txt` | 修复后违规详情，当前为空；空文件本身不作为通过证据，要与报告计数一起检查。 |

复制件中全部 13 个顶层结果文件均已与 `result_177` 原始回收文件逐字节比较，一致。Milkyway 库本体按用户复制件保留，没有在 Windows 上重新打开 ICC。

### Linux 文件名恢复

Windows 复制件出现 `counter_8bit^%1`，原 Linux 单元版本文件名使用 `counter_8bit:1`。为避免在 Linux 上因版本文件名错误而无法打开，提供了：

- `artifacts/drc_ai_linux.tar.gz`：从复制件生成，恢复了已识别的 CEL/err 版本分隔符；不修改原复制文件夹。
- `artifacts/drc_ai_linux_manifest.json`：每个原文件名、Linux 归档名、字节数及 SHA-256。
- `tools/package_milkyway.py`：生成脚本。它拒绝未知的转义文件名与重名，排除临时 `.lock`，不执行 ICC。

在 Linux 上解压到一个新的目录，例如：

```bash
mkdir -p ~/eda_sby_restore
tar -xzf drc_ai_linux.tar.gz -C ~/eda_sby_restore
```

解压后库路径为 `~/eda_sby_restore/drc_ai/counter_mw`。**恢复归档已经过文件字节校验，但尚未在另一个 Linux 环境重新打开 ICC 验证**。它仍依赖原有 TSMC90 逻辑库、物理参考库及技术文件；本仓库不提供整套 PDK。不要沿用复制来的 `.lock`。

虚拟机上已经实际通过检查的修复库路径是：

```text
/home/IC/Desktop/EDA_Projects/counter_backend/runs/upload_20261026_130102_35ef2344/build/drc_ai/counter_mw
```

## 四 真实工具日志在哪里

主目录：`EDA_Agent_LangGraph/designs/counter_backend/session_queue/`。

| 目录 | 记录内容 |
| --- | --- |
| `result_038/build/dc/` | DC 面积、时序、功耗、映射网表和约束。完整 DC 日志在同级 `build/dc.log`。 |
| `result_131/build/icc/` | 原始 ICC 版图导出和检查报告，含 1 处 spacing DRC。完整日志在 `result_131/build/icc.log`。 |
| `result_144/build/pt_estimate/` | PT 的统计线负载估算，包含单位、时序、功耗和活动标注报告。不是详细寄生签核。 |
| `result_155/src/generated/scripts/` | 从原始运行重新取回并按快照校验的原版 Tcl/RC 准备脚本，不等同于后来修改的工作区版本。 |
| `result_161/build/drc_probe/` | 只读查询的单元、引脚几何和已安装命令帮助。 |
| `result_164/build/drc_shapes/` | 两条目标网络的局部线段和 U14 引脚形状。 |
| `result_171/build/drc_ai/` | AI 第一轮失败，DRC 2，LVS 短路 1。 |
| `result_177/build/drc_ai/` | AI 第二轮成功，包含修复前后报告、网表、清单和导出。 |
| `result_180/build/drc_recheck/` | 重新打开保存数据库取得的 GUI 和报告截图。 |
| `result_181/` | GUI 取证后等待退出而触发时限的状态；该任务不算正常完成。 |
| `result_184/build/drc_verify/` | 独立命令行重新打开保存库并复查，退出码 0，DRC 0，是持久化验收依据。 |
| `result_185/` | 第二轮实际上传的候选 Tcl 与原始快照清单，用于核对当次执行文件。 |

同一目录中：`request_NNN.json` 是本机任务请求，`result_NNN/result.json` 是执行或回收结果，`request_started.json` 记录所属会话与时间，`icc.status.json` 记录工具实际运行状态。**上传成功、启动成功、图结束或退出码 0，均不能单独替代真实报告验收。** 原始日志保留了失败、环境问题和过程记录，不是每个目录都代表通过。

公开仓库省略了整段 PDK 技术文件读回、LEF 全文回显、厂商帮助文档副本和旧的失效 PID 停止脚本；相应元数据及历史说明仍保留。`.lock`、密钥、密码和缓存不上传。

## 五 前面的仿真实验

以下目录位于 `EDA_Agent_LangGraph/designs/`：

| 目录 | 用途 |
| --- | --- |
| `fifo/remote_runs/` | 已有 FIFO 示例在本机工具链上的复现实验，351 项检查通过。 |
| `counter_first_run/` | 真实 DeepSeek 生成计数器并用 VCS 验证，基线 824 项检查通过。 |
| `counter_autofix_demo/` | 缺少 en 门控的故障与模型修复验收。失败轮与成功轮都保留；影子目录是本次可核对的实验数据，不要误删。 |
| `counter_opt_round1/` | 第一轮人工辅助测试增强，825 项检查。 |
| `counter_opt_round2/` | 第二轮人工辅助测试增强，1035 项检查。 |
| `counter_opt_round3/` | 第三轮人工辅助测试增强，2035 项检查，显式功能点 14/14。 |
| `counter_script_demo/` | LangGraph + DeepSeek 生成 VCS/URG 脚本，并真实执行验收。 |
| `counter_backend/` | 活动信息、DC/ICC/PT、诊断、AI DRC 修复及原始结果。 |

常见文件：`generated/rtl/` 为 RTL，`generated/tb/` 为测试平台，`generation_request.txt` 为生成需求，`optimization_record.json` 为该轮改动和指标，`remote_runs/<标识>/` 为对应远端日志与快照。`vcs_compile.log`、`vcs_sim.log`、`coverage_dashboard.txt`、`run_summary.json` 分别为编译、仿真、覆盖率汇总及运行摘要。

三轮 Testbench 增强属于人工和 AI 助手协作，不是三轮 DeepSeek 自主 PPA 优化。第三轮总覆盖分数 84.97% 包含测试平台统计范围，不能写成 DUT 单独覆盖率。不要与上游 `EDA_Agent_LangGraph/evidence/counter_v82/` 的另一组 1032 检查、11/11 功能点实验混用；两组代码和统计口径不同。

## 六 程序入口与环境

| 文件 | 用途 |
| --- | --- |
| `EDA_Agent_LangGraph/code/web_app_eda_v8.py` | 原项目 Streamlit 网页入口。新增 DRC 功能当前以命令行入口提供，没有声称已经增加网页 DRC 按钮。 |
| `EDA_Agent_LangGraph/code/eda_agent_v8_core.py` | 需求规划、代码生成与静态复查的 StateGraph。 |
| `EDA_Agent_LangGraph/code/eda_autofix.py` | 根据真实编译/仿真反馈的自动纠错流程。 |
| `EDA_Agent_LangGraph/code/eda_remote_v8.py` | SSH/SFTP、源码快照和工具调用封装，含上游 P2 编译配置功能。 |
| `EDA_Agent_LangGraph/code/eda_analysis.py` | 解析 VCS 指标和结果摘要。 |
| `EDA_Agent_LangGraph/code/backend_session.py` | 本机交互式 SSH 会话及文件任务队列，密码只在本机输入。 |
| `EDA_Agent_LangGraph/code/backend_transport.py` | 带期限的连接、SFTP 与命令执行。 |
| `EDA_Agent_LangGraph/code/backend_guest_control.py` | 仅针对本项目记录的工具进程做诊断/停止的辅助程序。 |
| `EDA_Agent_LangGraph/code/eda_backend_analysis.py` | 解析 DC/ICC/PT 原始报告、单位和检查计数。 |
| `EDA_Agent_LangGraph/code/prepare_backend_activity.py`、`prepare_backend_inputs.py` | 准备活动信息、DC 输入和来源哈希。 |
| `EDA_Agent_LangGraph/code/eda_script_demo.py`、`generate_script_demo.py`、`run_generated_script.py` | 模型生成仿真脚本、审阅和实际运行演示。 |
| `EDA_Agent_LangGraph/code/run_vcs_once.py`、`autofix_cli.py` | 单次 VCS 和自动纠错命令行入口。 |
| `EDA_Agent_LangGraph/code/first_do.py` | 按本机环境变量惰性创建模型客户端，文件本身不含密钥。 |
| `EDA_Agent_LangGraph/code/check_env.py`、`probe_backend_env.py`、`refresh_backend_host.py` | 环境检查和虚拟机地址适配。旧 IP 仅为历史记录，新机器必须自行确认。 |
| `EDA_Agent_LangGraph/code/test_*.py`、`patches/test_autofix_offline.py` | 分析、传输、策略限制、报告验收等测试；带 remote 的测试需要真实环境，不要把离线测试输出当成 EDA 实跑。 |
| `EDA_Agent_LangGraph/requirements.txt`、`requirements-dev.txt` | 运行与可选开发依赖。 |
| `EDA_Agent_LangGraph/.env.example` | 配置模板，复制到 `code/.env` 后填写自己的密钥。 |

例如在 Windows PowerShell 中安装和启动网页：

```powershell
cd EDA_Agent_LangGraph\code
py -3.12 -m venv venv
.\venv\Scripts\python.exe -m pip install -r ..\requirements.txt
Copy-Item ..\.env.example .env
# 在本机编辑 .env，不要提交真实密钥。
.\venv\Scripts\python.exe -m streamlit run web_app_eda_v8.py
```

重新执行 DRC 修复需要先配置可用的 Linux ICC、TSMC90 工艺环境和本案例基线库，启动 `backend_session.py --host <实际IP> --fresh-session`，再按 DRC README 运行 `drc_ai_repair.py`。该功能针对本案例实现，不是安装 Python 后就能在无工艺库环境重现的通用工具。

## 七 下载包与文件校验

| 文件 | 内容 |
| --- | --- |
| `artifacts/EDA_报告与实测材料_20261025_155525.zip` | 前期 VCS/DC/ICC/PT 的完整实测材料包；其中的旧报告与残余违规说明保留当时状态。 |
| `artifacts/EDA_AI辅助DRC修复_20261026_133208.zip` | 新功能补充包，含真实模型记录、两轮工具证据、截图、源码和 AI 报告。该包在用户复制数据库前生成，不含完整 Milkyway 库。 |
| `artifacts/drc_ai_linux.tar.gz` | 本次额外生成的 Milkyway 复制件及结果归档，已恢复识别出的 Linux 版本文件名。 |
| `artifacts/drc_ai_linux_manifest.json` | Linux 归档内各文件的源名、目标名与哈希。 |
| `docs/sby_文件清单.json` | 本分支发布文件的路径、用途、大小、SHA-256 和 Git blob 标识。SHA-256 针对 Git 中保存的字节，Windows checkout 的自动换行转换可能影响普通文本；原始实验快照已禁止换行转换。 |
| `EDA_Agent_LangGraph/SHA256SUMS.txt` | 上游交接阶段的历史清单；本分支新增/修改文件以新发布清单为准。 |

各运行内部 `snapshot_manifest.json` 校验当时上传的源码，`result.json` 校验当时回收的报告；它们与发布清单的用途不同。发布不会重新运行模型或 EDA 工具，也不会把历史实验说成本机重新执行。

本次整合后通过 35 项 unittest 检查，以及分析、P2 编译配置、自动纠错的独立离线检查。原目录 `first/`、人脸检测相关 Markdown 和资产文件夹来自上游其他内容，本次未将其当作 EDA 课程设计成果。
