"""
Prompt Optimizer - 自动找失败 case 并迭代优化
- 跑测试集
- 识别失败 case
- 输出具体优化建议
- 可以自动 patch prompt
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 在 import 前设置模型
os.environ["TASKPANE_MODEL"] = sys.argv[1] if len(sys.argv) > 1 else "qwen2:0.5b"

from taskpane_app import call_ollama, PARSE_PROMPT

# 测试集（扩展版）
TEST_CASES = [
    # is_task 测试
    ("@小王 紧急！明天下班前提交Q3财报分析给李总",
     {"is_task": True, "priority": "P0", "assigned_to_me": True, "auto_completable": False}),
    ("请张老师帮忙看下这周的课件，thanks",
     {"is_task": True, "priority": "P1"}),
    ("哈哈哈哈哈笑死我了",
     {"is_task": False}),
    ("大家晚上好啊，吃了吗？",
     {"is_task": False}),
    ("明天放假一天",
     {"is_task": False}),
    # auto_completable 测试
    ("帮我查一下 600519 的最新股价",
     {"is_task": True, "auto_completable": True}),
    ("写一份技术报告，比较 LeanDojo 和 Lean Copilot 的差异",
     {"is_task": True, "auto_completable": False}),
    ("Q4 应该重点发展哪个方向？大家讨论一下",
     {"is_task": True, "auto_completable": False}),
    # deadline 测试
    ("周末前把那个文档改了",
     {"is_task": True, "priority": "P1"}),
    ("明天下午 3 点在 301 会议室开项目讨论会，请准时到",
     {"is_task": True, "priority": "P1"}),
]


def diagnose_failure(msg, expected, actual):
    """诊断失败 case，给出优化建议"""
    issues = []
    if expected.get('is_task') != actual.get('is_task'):
        issues.append(f"is_task 误判: 期望 {expected['is_task']} → 实际 {actual.get('is_task')}")
    if expected.get('priority') and actual.get('priority') != expected['priority']:
        issues.append(f"priority 误判: 期望 {expected['priority']} → 实际 {actual.get('priority')}")
    if 'auto_completable' in expected and actual.get('auto_completable') != expected['auto_completable']:
        issues.append(f"auto_completable 误判: 期望 {expected['auto_completable']} → 实际 {actual.get('auto_completable')}")
    return issues


def run():
    print("=" * 70)
    print(f"Prompt Optimizer · 模型: {os.environ['TASKPANE_MODEL']}")
    print("=" * 70)

    correct, total = 0, 0
    failures = []

    for i, (msg, expected) in enumerate(TEST_CASES, 1):
        parsed, err = call_ollama(msg)
        if err:
            print(f"[{i:2d}] ✗ ERR: {err}")
            print(f"     消息: {msg}")
            failures.append((i, msg, expected, None, err))
            total += len(expected)
            continue

        actual = {k: parsed.get(k) for k in expected}
        ok = sum(1 for k in expected if actual[k] == expected[k])
        correct += ok
        total += len(expected)

        status = "✓" if ok == len(expected) else "✗"
        print(f"[{i:2d}] {status} {msg[:40]}")
        if ok < len(expected):
            issues = diagnose_failure(msg, expected, actual)
            for issue in issues:
                print(f"     → {issue}")
            failures.append((i, msg, expected, actual, "; ".join(issues)))

    accuracy = correct / total if total else 0
    print()
    print("=" * 70)
    print(f"准确率: {correct}/{total} = {accuracy*100:.1f}%")
    print("=" * 70)

    if failures:
        print(f"\n失败的 {len(failures)} 个 case:")
        for i, msg, exp, act, reason in failures:
            print(f"  [{i}] {msg[:30]}... | {reason}")

        # 输出 prompt 优化建议
        print()
        print("=" * 70)
        print("Prompt 优化建议（手动 patch 或让 AI 帮你改）：")
        print("=" * 70)
        print()
        print("在 scripts/taskpane_app.py 的 PARSE_PROMPT 里：")
        print()
        if any('is_task' in r for _, _, _, _, r in failures):
            print("1. 加更明确的 is_task 边界规则")
            print("   - true 关键词: @, 麻烦, 请, 提交, 修改, 完成, 把...改/做/写")
            print("   - false 关键词: 大家好, 晚上好, 哈哈, 吃了吗, 在吗")
        if any('priority' in r for _, _, _, _, r in failures):
            print("2. 检查 priority 关键词覆盖")
            print("   - P0: 紧急, 今天, 截止明天")
            print("   - P1: 尽快, 本周, 这周, 重要, 周五")
        if any('auto_completable' in r for _, _, _, _, r in failures):
            print("3. auto_completable 判断要更严格")
            print("   - true: 单纯数据查询 / 信息检索")
            print("   - false: 写报告/做决策/分析/创作")

    return accuracy


if __name__ == "__main__":
    acc = run()
    sys.exit(0 if acc == 1.0 else 1)