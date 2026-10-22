# EDA Agent v8.3 交接包

基于 v8.2 的「国产大模型 + LangGraph 自动化 EDA」项目，新增：

- **自动纠错闭环**：StateGraph 子图（stage → simulate → analyze → patch），失败后自动打补丁并重跑
- **覆盖率采集**：VCS `-cm` + `urg`，结果写入 `run_summary.json`
- **结果分析面板**：网页内指标卡 / 逐轮表 / 趋势图 / 失败模式，一键导出 Markdown

对应课设：题目三 · 任务一 —— 仿真与验证平台的自动化生成。

---

## 当前进度（2026-10-22）

| 项 | 状态 |
| --- | --- |
| 五阶段 StateGraph | ✅ 生成层 + 闭环层两张图 |
| 自动纠错闭环 | ✅ 语法错 / 断言错各 1 次重试修复 |
| 迭代实验 | ✅ 基线 + 4 次优化（v1→v5），含 1 次负结果对照 |
| 代码覆盖率 | 88.53% → **93.05%** |
| 功能覆盖 | **11/11 bins** |
| 工程通用性 | ✅ 计数器 / FIFO / 256 位加法器（7 源文件） |
| 正式课程设计报告 | ❌ 未开始（仅有进度报告） |

## 目录结构

```
EDA_Agent_handover_2026-10-22/
├── README.md                 本文件：包索引与快速验证
├── 使用说明.md               安装、启动、四个按钮、常见问题
├── 交接说明.md               项目现状、架构、代码地图、已知问题、后续优先级
├── requirements.txt          依赖清单（已验证版本组合）
├── .env.example              配置模板（复制为 code/.env 后填密钥）
├── SHA256SUMS.txt            全包文件校验值
├── code/                     14 个源码/脚本文件
├── designs/                  第二个设计（同步 FIFO），用于验证工程通用性
├── docs/                     进度报告 + 两张 StateGraph 图（PNG/Mermaid 源）
├── patches/                  Testbench v2 / v3 与闭环离线测试
└── evidence/                 计数器三轮、两个故障案例、FIFO 的真实日志
```

## 5 分钟验证

```powershell
# 1. 装依赖
cd code
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r ..\requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 2. 配置
copy ..\.env.example .env      # 然后填入 DEEPSEEK_API_KEY 与 EDA_SSH_HOST

# 3. 离线回归（不连虚拟机，应输出 3 条 PASS）
.\venv\Scripts\python.exe test_v8_2_offline.py

# 4. 启动网页
.\venv\Scripts\streamlit.exe run web_app_eda_v8.py --server.headless true --server.port 8501
```

浏览器打开 `http://localhost:8501`，见《使用说明》第 2 节。

## 文档索引

| 想知道 | 看 |
| --- | --- |
| 怎么装、怎么点、报错怎么办 | `使用说明.md` |
| 做到了哪、还差什么、代码怎么组织 | `交接说明.md` |
| 三轮迭代数据、覆盖率分析、闭环验收 | `docs/项目进度报告_2026-10-22.md` |
| 工作流长什么样 | `docs/gen_graph.png`、`docs/loop_graph.png` |

## 快速判断这份包是否可信

| 你想验证 | 打开 |
| --- | --- |
| 真的有 VCS 跑过 | `evidence/counter_v82/vcs_007/vcs_compile.log` 首行是 `Chronologic VCS (TM) I-2014.03_Full64` |
| 真的修好了 bug | 对比 `evidence/case1_compile_failed/` 与 `case1_fixed/` 的 `run_summary.json`（`compile_failed` → `passed_by_marker`） |
| 覆盖率不是编的 | `evidence/counter_v82/vcs_007/coverage_dashboard.txt` 里有 `Total Coverage Summary` 原始表格 |
| 换一个工程也能跑 | `evidence/fifo_sync_v1/run_summary.json`：独立工程、351 检查点、覆盖率 96.61% |
| 多文件层次设计也能跑 | `evidence/cla256_v1/run_summary.json`：7 个源文件、1005 检查点、覆盖率 99.47% |
| 本地也能复现 | `designs/fifo/` 可用 ModelSim 直接编译仿真（351 检查点全过） |

## 安全声明

- 包内**不含** `.env`（密钥）、`venv/`、聊天历史、虚拟机镜像。
- SSH 密码不落盘，每次在网页/命令行临时输入。
- 远程执行只使用固定命令模板，不执行模型生成的 `.sh/.tcl`。
- 旧工程 `adder` / `ref` 在代码层被强制拒绝接管。

## 仓库

GitHub：<https://github.com/chenzhaoho/czh>（子目录 `EDA_Agent_LangGraph/`）
