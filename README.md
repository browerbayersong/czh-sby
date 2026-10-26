# EDA 课程设计与 AI 辅助 DRC 修复

本仓库保存课程设计代码、真实 EDA 实验日志、报告，以及 LangGraph + DeepSeek 辅助 DRC 诊断与修复功能。内容基于 [chenzhaoho/czh](https://github.com/chenzhaoho/czh) 项目整理；保留其原有提交历史和后续 P2 更新。

**请查看 `sby` 分支。** `main` 保留整理时的上游版本，`sby` 包含本次课设材料与新增功能。

## 先看这些文件

| 想找什么 | 去哪里 |
| --- | --- |
| 每类文件用途、目录、运行方式与限制 | [资料目录与使用说明](docs/sby_资料目录与使用说明.md) |
| 文件清单与字节校验值 | [发布文件清单](docs/sby_文件清单.json) |
| 含 AI 修复章节的 Word | [AI 修复补充版](reports/EDA课程设计报告_AI修复补充版.docx) |
| 原有基础稿 | [现有基础稿](reports/EDA课程设计报告_现有基础稿.docx) |
| 新增功能的程序入口 | [drc_ai_repair.py](EDA_Agent_LangGraph/code/drc_ai_repair.py) |
| 新增功能说明、结果索引与复现方法 | [DRC AI README](EDA_Agent_LangGraph/designs/counter_backend/drc_ai/README.md) |
| 两轮真实提示词、模型响应与候选 Tcl | [20261026_ai_01](EDA_Agent_LangGraph/designs/counter_backend/drc_ai/20261026_ai_01/) |
| 从虚拟机复制出的修复版图与数据库 | [drc_ai](drc_ai/) |
| 恢复 Linux 文件名的数据库归档 | [drc_ai_linux.tar.gz](artifacts/drc_ai_linux.tar.gz) |
| 可整包下载的日志、报告、源码和截图 | [artifacts](artifacts/) |

## 本次修复的真实结果

初版 `result_131` 有 1 处 M1 的 Diff net spacing，涉及 `count[5]` 与 `N7`。新增流程真实调用 DeepSeek，并由 LangGraph 决定执行、复查及重试：

| 阶段 | 布线 DRC | LVS 短路 | 处理 |
| --- | ---: | ---: | --- |
| 原始版图 | 1 | 0 | 保留为基线 |
| AI 第 1 轮 | 2 | 1 | 拒绝该副本，保留失败证据 |
| AI 第 2 轮 | 0 | 0 | 检查通过，保存修复副本 |
| 保存后重新打开复查 | 0 | 0 | 独立命令行复查通过 |

同时检查了开路、电源连接、放置合法性，以及规范化网表和单元清单的一致性。完整核验摘要见 [drc_ai_verified.json](EDA_Agent_LangGraph/designs/counter_backend/drc_ai_verified.json)。

**适用范围：现有技术设置下的 ICC 内置布线检查。** 技术库与物理参考库仍有一致性警告，天线规则未定义，详细 TLU+/SPEF 与修复后布线的 PT 尚未执行，不能称为晶圆厂完整签核。报告中的旧 PT 数值属于此前的统计线负载估算。

## 下载和使用

只阅读报告和结果，不需要配置模型 API 或启动虚拟机。要运行网页、重新仿真或重新调用模型，请按 [资料说明](docs/sby_资料目录与使用说明.md) 配置自己的环境。

仓库不包含 API Key、SSH 密码、Python 虚拟环境或整套工艺库。`drc_ai/counter_mw` 是本案例自身的 Milkyway 工作数据库，不是完整 PDK。Windows 复制件中的版本分隔符已变成 `^%`；在 Linux 上使用时优先解包 `artifacts/drc_ai_linux.tar.gz`，不要直接把 Windows 文件名当作原始 ICC 文件名。

报告保留了个人信息和个人心得的待填写栏位，不将其标作无需完善即可提交的终稿。
