"""LangGraph 起步图：retrieve -> answer。

这个文件同时是：
  * 命令行脚本：python graph.py "你的问题"
  * LangGraph Studio 的入口：langgraph.json 里指向 graph.py:graph
  * Notebook 的 import 目标：from graph import graph

没配 API Key 时走离线分支，图照样能跑通，方便先熟悉结构。
"""

from __future__ import annotations

import os
import sys
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

if not sys.stdout.isatty():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()


class State(TypedDict, total=False):
    question: str
    context: str
    answer: str


def has_real_key() -> bool:
    key = os.getenv("DEEPSEEK_API_KEY", "")
    return bool(key) and key != "sk-xxx"


def retrieve(state: State) -> State:
    """检索节点：真实项目里换成向量库或搜索工具。"""
    question = state.get("question", "")
    return {"context": f"（示例假数据）与「{question}」相关的三条笔记。"}


def answer(state: State) -> State:
    """回答节点：有 Key 调 DeepSeek，没 Key 返回离线结果。"""
    question = state.get("question", "")
    context = state.get("context", "")

    if not has_real_key():
        return {"answer": f"[离线模式] 已收到检索结果：{context}"}

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        temperature=0.3,
    )
    msg = llm.invoke([
        ("system", "你是一个简洁的中文助手，回答控制在两句话内。"),
        ("user", f"问题：{question}\n资料：{context}"),
    ])
    return {"answer": msg.content}


def build_graph():
    builder = StateGraph(State)
    builder.add_node("retrieve", retrieve)
    builder.add_node("answer", answer)
    builder.add_edge(START, "retrieve")
    builder.add_edge("retrieve", "answer")
    builder.add_edge("answer", END)
    return builder.compile()


# Studio / langgraph.json 需要的模块级变量
graph = build_graph()


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "LangGraph 是什么？"
    result = graph.invoke({"question": q})
    print(f"模式: {'live' if has_real_key() else 'offline'}")
    print(f"问题: {result['question']}")
    print(f"上下文: {result['context']}")
    print(f"回答: {result['answer']}")
    print("\n图结构：")
    print(graph.get_graph().draw_ascii())
