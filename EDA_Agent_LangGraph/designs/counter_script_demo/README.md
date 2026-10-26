# 模型生成仿真脚本补充实验

本实验补齐任务一中的“调用大模型生成仿真脚本”证据。

## 已完成

- 使用现有 `eda_agent_v8_core.run_task` 的真实 LangGraph 工作流和 DeepSeek API，生成 `generated/scripts/run_vcs.sh`。
- 提示词要求脚本执行 VCS 编译、仿真和 URG 文本覆盖率报告，工具路径针对当前 Linux 虚拟机。
- 模型静态复查通过；本地命令/路径检查和 Git Bash `bash -n` 语法检查通过。
- RTL 和 Testbench 按字节复制自 `counter_opt_round3`，不重新生成 HDL。
- 保存提示词、生成脚本的原始模型文本响应、图返回的规划/复查结果和 SHA-256。

注意：`llm_trace.jsonl` 记录文件生成阶段的文本调用；JSON 规划/复查的返回结果在 `generation_result.json`，没有保存这两个阶段的原始 API 响应。本地检查不能替代 Linux 真实执行。

## Windows PowerShell 运行

在 `D:\课程设计\czh\EDA_Agent_LangGraph\code` 运行：

```powershell
.\venv\Scripts\python.exe -u run_generated_script.py --host 192.168.142.128 --workspace ..\designs\counter_script_demo --project counter_script_demo
```

密码在本机提示处输入，不会显示或保存。脚本已经包含覆盖率参数，不依赖当前 PowerShell 是否设置 `EDA_COVERAGE`。

运行器先上传独立快照，检查远端源码字节和脚本语法，再实际执行 `.sh`；运行轨迹和 VCS/URG 原始日志自动回收到本工作空间的 `remote_runs/<运行ID>/`。每次使用新的远端运行目录，不覆盖前一次结果。前置上传的 `run_summary.json` 与本实验的 `script_run_summary.json` 分别保存。

本实验预期功能结果为 2035 次检查全部通过、14/14 个功能覆盖点；同时必须拿到 URG 汇总才标记 `passed`。覆盖率数值以本次真实日志为准。

程序还会在 `D:\课程设计\报告素材` 创建独立补充素材目录和 ZIP，包含本次日志、源码、脚本、提示词、实现代码和校验清单。终端截图需在运行结束后保存。

## 当前状态

2026 年 10 月 24 日已完成 Linux 实跑，状态为 `passed`，脚本退出码为 0。2035 次检查全部通过，功能覆盖 14/14；URG 总分 84.97%，行覆盖 91.95%，分支覆盖 80.00%，翻转覆盖 82.95%。

本地日志位于 `remote_runs/ad59f1712f2045be8395730c8a7062f4/`，远端位于 `/home/IC/Desktop/EDA_Projects/counter_script_demo/runs/upload_001`。`script_execution.log` 记录实际 bash 执行轨迹，`script_run_summary.json` 记录本次结果。生成时的 `generation_manifest.json` 保留当时“等待实跑”的状态，不回写修改历史生成记录。

此次实验验证仿真脚本生成与执行，不是新一轮覆盖率优化，也不包含综合、布局布线或 PPA 实验。
