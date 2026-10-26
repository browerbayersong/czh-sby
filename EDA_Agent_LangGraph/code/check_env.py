"""环境自检：确认依赖装好、.env 读得到、密钥不是占位符。

用法：
    .\\venv\\Scripts\\python.exe check_env.py
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version

from dotenv import load_dotenv

# 被管道/重定向捕获时用 UTF-8，避免 Windows 控制台编码造成中文乱码；
# 直接在终端里运行时沿用系统默认编码。
if not sys.stdout.isatty():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REQUIRED = [
    ("langgraph", "langgraph"),
    ("langchain", "langchain"),
    ("langchain-openai", "langchain_openai"),
    ("python-dotenv", "dotenv"),
    ("streamlit", "streamlit"),
    ("paramiko", "paramiko"),
]


def main() -> int:
    print(f"Python: {sys.version.split()[0]}  ({sys.executable})")
    print("\n[依赖版本]")
    ok = True
    for pkg, module in REQUIRED:
        try:
            importlib.import_module(module)
            print(f"  OK  {pkg:<16} {version(pkg)}")
        except (ImportError, PackageNotFoundError) as exc:
            ok = False
            print(f"  FAIL {pkg:<16} {exc!r}")

    print("\n[.env 配置]")
    loaded = load_dotenv(Path(__file__).with_name('.env'))
    print(f"  .env 已加载: {loaded}")

    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL",
                "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        value = os.getenv(key, "")
        if key.endswith('_KEY'):
            shown = '<已设置>' if value and value != 'sk-xxx' else '<未设置>'
        else:
            shown = value or '<未设置>'
        print(f"  {key:<17} = {shown}")

    api_key = os.getenv('DEEPSEEK_API_KEY') or os.getenv('OPENAI_API_KEY') or ''
    if api_key in ('', 'sk-xxx'):
        print("\n  提示：尚未配置模型 API Key；可运行离线测试，真实生成与纠错需要配置密钥。")
    if not ok:
        print("\n  提示：依赖缺失，请先按 README 安装。")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
