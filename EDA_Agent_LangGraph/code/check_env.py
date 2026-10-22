"""环境自检：确认依赖装好、.env 读得到、密钥不是占位符。

用法：
    .\\venv\\Scripts\\python.exe check_env.py
"""

from __future__ import annotations

import importlib
import os
import sys
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
]


def mask(value: str) -> str:
    if not value:
        return "<未设置>"
    if len(value) <= 8:
        return value[:2] + "***"
    return f"{value[:6]}...{value[-4:]}"


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
    loaded = load_dotenv()
    print(f"  .env 已加载: {loaded}")

    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL",
                "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
        value = os.getenv(key, "")
        shown = mask(value) if key.endswith("_KEY") else (value or "<未设置>")
        print(f"  {key:<17} = {shown}")

    placeholders = [
        key for key in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY")
        if os.getenv(key, "") in ("", "sk-xxx")
    ]
    if placeholders:
        print(f"\n  提示：{', '.join(placeholders)} 仍是占位符，替换为真实密钥后才能调用 API。")
    elif not ok:
        print("\n  提示：依赖缺失，请先按 README 安装。")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
