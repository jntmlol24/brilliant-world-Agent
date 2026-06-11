"""共享测试 fixtures。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# 确保 src 在 path 中（兼容 pytest 单独运行）
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# 测试期间禁用 OTLP
os.environ.setdefault("OTLP_ENABLED", "false")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
