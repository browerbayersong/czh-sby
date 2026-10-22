"""提供已接入 DeepSeek 的 llm 对象。

v8.2 压缩包不含本文件（属本机私有依赖），此处按 eda_agent_v8_core.py 的实际用法重建：

    from first_do import llm
    llm.invoke([SystemMessage(...), HumanMessage(...)]).content

设计约束：
* 导入本模块不发起任何网络请求、不进入命令行输入循环（原说明文档明确提醒过）。
* 只有真正调用 llm.invoke / .stream 时才校验密钥并创建客户端，避免离线测试被卡住。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))


def build_llm():
    """按 .env 配置创建 ChatOpenAI 客户端（DeepSeek 走 OpenAI 兼容接口）。"""
    from langchain_openai import ChatOpenAI

    api_key = os.getenv('DEEPSEEK_API_KEY') or os.getenv('OPENAI_API_KEY') or ''
    if not api_key or api_key == 'sk-xxx':
        raise RuntimeError(
            '未配置 DeepSeek 密钥：请在 E:\\LangGraph\\.env 中填写 DEEPSEEK_API_KEY'
        )

    return ChatOpenAI(
        model=os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-pro'),
        base_url=os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com'),
        api_key=api_key,
        temperature=float(os.getenv('DEEPSEEK_TEMPERATURE', '0.2')),
        timeout=float(os.getenv('DEEPSEEK_TIMEOUT', '180')),
        max_retries=2,
    )


class LazyLLM:
    """第一次使用时才建客户端；对外行为与 ChatOpenAI 一致。"""

    def __init__(self) -> None:
        self._inner = None

    def _get(self):
        if self._inner is None:
            self._inner = build_llm()
        return self._inner

    def invoke(self, *args, **kwargs):
        return self._get().invoke(*args, **kwargs)

    def stream(self, *args, **kwargs):
        return self._get().stream(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._get(), name)


llm = LazyLLM()
