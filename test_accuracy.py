"""
TaskPane 准确率测试集
- 10 个真实场景消息
- 每个标注期望输出
- 跑当前 prompt，输出准确率报告
"""
import os
# 让默认模型可被环境变量覆盖（在 import taskpane_app 前设置）
os.environ.setdefault("TASKPANE_MODEL", "qwen2:0.5b")

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from taskpane_app import call_ollama


# 测试集：(消息, 期望字段 dict)
TEST_CASES = [
    # 1. 紧急 + @我 + 截止明天
    ("@小王 紧急！明天下班前提交Q3财报分析给李总", {
        "is_task": True, "priority": "P0", "assigned_to_me": True
    }),

    # 2. 普通任务 + 截止本周
    ("请张老师帮忙看下这周的课件，thanks", {
        "is_task": True, "priority": "P1"
    }),

    # 3. 闲聊（应该判定非任务）
    ("哈哈哈哈哈笑死我了", {
        "is_task": False
    }),

    # 4. 数据查询（应该 auto_completable=true）
    ("帮我查一下 600519 的最新股价", {
        "is_task": True, "auto_completable": True
    }),

    # 5. 写作任务（应该 auto_completable=false）
    ("写一份技术报告，比较 LeanDojo 和 Lean Copilot 的差异", {
        "is_task": True, "auto_completable": False
    }),

    # 6. 会议通知（截止明确）
    ("明天下午 3 点在 301 会议室开项目讨论会，请准时到", {
        "is_task": True, "priority": "P1"
    }),

    # 7. 模糊截止
    ("周末前把那个文档改了", {
        "is_task": True, "priority": "P1"
    }),

    # 8. 寒暄（应该非任务）
    ("大家晚上好啊，吃了吗？", {
        "is_task": False
    }),

    # 9. 隐式任务（无@但有动作请求）
    ("麻烦大家把各自的进度更新一下，发到群里", {
        "is_task": True
    }),

    # 10. 决策性问题（auto_completable=false）
    ("Q4 应该重点发展哪个方向？大家讨论一下", {
        "is_task": True, "auto_completable": False
    }),
]


def run_test():
    import os
    os.environ.setdefault("TASKPANE_MODEL", "qwen2:0.5b")
    print("=" * 70)
    print(f"TaskPane 准确率测试 · {len(TEST_CASES)} 个测试用例")
    print(f"模型: {os.environ.get('TASKPANE_MODEL', 'qwen2:0.5b')} via Ollama")
    print("=" * 70)

    correct = 0
    total = 0
    failures = []

    for i, (msg, expected) in enumerate(TEST_CASES, 1):
        print(f"\n[{i:2d}] 消息: {msg}")
        print(f"     期望: {expected}")

        parsed, err = call_ollama(msg)
        if err:
            print(f"     ❌ 错误: {err}")
            failures.append((i, msg, expected, None, err))
            total += len(expected)
            continue

        # 比对每个期望字段
        case_correct = 0
        case_total = len(expected)
        actual = {}
        for key, exp_val in expected.items():
            actual_val = parsed.get(key)
            actual[key] = actual_val
            if (isinstance(exp_val, bool) and isinstance(actual_val, bool) and exp_val == actual_val) or \
               (not isinstance(exp_val, bool) and actual_val == exp_val):
                case_correct += 1
                status = "✓"
            else:
                status = "✗"
            print(f"     {status} {key}: 期望={exp_val}, 实际={actual_val}")

        correct += case_correct
        total += case_total
        if case_correct < case_total:
            failures.append((i, msg, expected, actual, "字段不匹配"))

    print("\n" + "=" * 70)
    print(f"准确率: {correct}/{total} = {correct/total*100:.1f}%")
    print("=" * 70)

    if failures:
        print(f"\n失败的 {len(failures)} 个用例:")
        for i, msg, expected, actual, reason in failures:
            print(f"  [{i}] {msg[:40]}... ({reason})")


if __name__ == "__main__":
    run_test()