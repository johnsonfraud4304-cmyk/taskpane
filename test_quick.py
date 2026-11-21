"""
快速测试：用现有 qwen2:0.5b 测改进后的 prompt
跑 5 个 case，每个 30s 超时
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 强制用 0.5b（已下载）
import os
os.environ["TASKPANE_MODEL"] = "qwen2:0.5b"

from taskpane_app import call_ollama

CASES = [
    ("@小王 紧急！明天下班前提交Q3财报分析给李总",
     {"is_task": True, "priority": "P0", "assigned_to_me": True, "auto_completable": False}),
    ("帮我查一下 600519 的最新股价",
     {"is_task": True, "auto_completable": True}),
    ("哈哈哈哈哈",
     {"is_task": False}),
    ("周末前把那个文档改了",
     {"is_task": True, "priority": "P1"}),
    ("明天放假一天",
     {"is_task": False}),
]

correct = 0
total = 0
for i, (msg, exp) in enumerate(CASES, 1):
    print(f"\n[{i}] {msg[:40]}")
    print(f"    期望: {exp}")
    p, e = call_ollama(msg)
    if e:
        print(f"    ERR: {e}")
        total += len(exp)
        continue
    actual = {k: p.get(k) for k in exp}
    print(f"    实际: {actual}")
    case_ok = 0
    for k, v in exp.items():
        if actual[k] == v:
            case_ok += 1
            print(f"      ✓ {k}")
        else:
            print(f"      ✗ {k}: 期望={v}, 实际={actual[k]}")
    correct += case_ok
    total += len(exp)

print(f"\n=== 准确率: {correct}/{total} = {correct/total*100:.1f}% ===")