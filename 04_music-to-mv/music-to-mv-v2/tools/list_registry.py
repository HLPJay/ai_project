"""
列出注册表中所有已注册的 prompt 模板
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.llm.registry import PromptRegistry

reg = PromptRegistry()
print(f"注册表版本: {reg._data.get('version')}")
print(f"更新时间: {reg._data.get('last_updated')}")
print()

items = sorted(reg._data.get("prompts", {}).items())
for key, info in items:
    dv = info.get("default_version", "N/A")
    desc = info.get("description", "")
    print(f"  [{dv:>6}] {key}")
    print(f"          {desc[:70]}")

