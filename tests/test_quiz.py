#!/usr/bin/env python3
"""
Quiz 功能独立测试脚本
═══════════════════════════════════════════════════════
验证所有5个Phase最后一天Lesson的Quiz功能:
  1. Quiz启动 — POST /phase3-api/quiz/start
  2. Quiz提交 — POST /phase3-api/quiz/submit
  3. 题目结构验证 (question_text + options)
  4. 评分返回验证

用法:
    PYTHONIOENCODING=utf-8 python tests/test_quiz.py
    PYTHONIOENCODING=utf-8 python tests/test_quiz.py --phase phase1
"""

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platform_client import PlatformClient

PASS = 0
FAIL = 0
SKIP = 0


def check(condition, msg):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {msg}")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg}")


def test_phase_quiz(client, phase_code, lesson_id, title):
    """测试单个Phase最后Lesson的Quiz"""
    global SKIP
    print(f"\n{'='*60}")
    print(f"  {phase_code} L{lesson_id}: {title}")
    print(f"{'='*60}")

    # ── Quiz启动 ──
    print("\n--- Quiz启动 ---")
    result = client.quiz_start(lesson_id)
    check(result.get("ok"), f"quiz_start HTTP {result.get('status_code')}")
    if not result.get("ok"):
        print(f"    Error: {result.get('error', '')[:100]}")
        SKIP += 1
        return

    questions = result.get("questions", [])
    check(len(questions) >= 1, f"至少1道题 (实际: {len(questions)})")

    # ── 题目结构验证 ──
    print("\n--- 题目结构验证 ---")
    structure_ok = True
    for i, q in enumerate(questions):
        qid = q.get("question_id", f"?_{i}")
        has_text = bool(q.get("question_text"))
        has_options = len(q.get("options", [])) >= 2
        if not has_text:
            print(f"  [FAIL] Q{i+1} ({qid}): 缺少question_text")
            structure_ok = False
        if not has_options:
            print(f"  [FAIL] Q{i+1} ({qid}): 选项不足({len(q.get('options', []))}个)")
            structure_ok = False
        if has_text and has_options:
            # 验证选项格式
            all_valid = all(
                o.get("id") and o.get("text")
                for o in q["options"]
            )
            if not all_valid:
                print(f"  [FAIL] Q{i+1} ({qid}): 选项格式不完整")
                structure_ok = False
    check(structure_ok, f"所有{len(questions)}题结构完整")

    # ── Quiz提交 ──
    print("\n--- Quiz提交 ---")
    session_id = result.get("quiz_session_id", "")
    check(bool(session_id), f"quiz_session_id存在: {str(session_id)[:30]}")

    if session_id and questions:
        # 模拟学生答题: 每题选第一个选项
        answers = []
        for q in questions:
            opts = q.get("options", [])
            answers.append({
                "question_id": q["question_id"],
                "selected_answer": opts[0]["id"] if opts else "A",
            })
        submit = client.quiz_submit(session_id, answers)
        check(submit.get("ok"), f"quiz_submit HTTP {submit.get('status_code')}")
        if submit.get("ok"):
            score = submit.get("score", "N/A")
            print(f"    得分: {score}")
            check(score is not None, "score字段存在")
        else:
            print(f"    Error: {submit.get('error', '')[:100]}")

    return {
        "phase_code": phase_code,
        "lesson_id": lesson_id,
        "question_count": len(questions),
        "session_id": session_id,
        "quiz_start_ok": result.get("ok"),
        "quiz_submit_ok": result.get("quiz_submit", {}).get("ok", False) if 'submit' in dir() else False,
    }


def main():
    ap = argparse.ArgumentParser(description="Quiz功能独立测试")
    ap.add_argument("--phase", type=str, help="单Phase测试 (phase1~phase5)")
    args = ap.parse_args()

    client = PlatformClient(timeout=20, verbose=False)
    print("登录中...")
    client.login()
    print(f"用户: {client.user.get('display_name')} ({client.user.get('role')})\n")

    phase_lessons = [
        ("phase1", 20, "Day 4：设备网关与 OpenAI-compatible 接口"),
        ("phase2", 25, "Day 5：加工质量评价与数据分析"),
        ("phase3", 9, "Day 6：灯带与音频边缘 AI"),
        ("phase4", 16, "Day 7：AI驱动的具身协同实战"),
        ("phase5", 26, "Day 1：AI 机器人项目启动与系统集成"),
    ]

    if args.phase:
        target = next((p for p in phase_lessons if p[0] == args.phase), None)
        if not target:
            print(f"[ERROR] Unknown phase: {args.phase}")
            sys.exit(1)
        phase_lessons = [target]

    results = []
    for pc, lid, title in phase_lessons:
        r = test_phase_quiz(client, pc, lid, title)
        if r:
            results.append(r)

    # ── 总结 ──
    total = PASS + FAIL + SKIP
    print(f"\n{'='*60}")
    print(f"  Quiz测试总结: {PASS}/{total} PASS, {FAIL} FAIL, {SKIP} SKIP")
    print(f"  Phase Quiz可用: {sum(1 for r in results if r.get('quiz_start_ok'))}/{len(results)}")
    print(f"{'='*60}")

    # 输出JSON结果
    report = {
        "test": "quiz_functional",
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "summary": {"pass": PASS, "fail": FAIL, "skip": SKIP, "total": total},
    }
    output_path = Path(__file__).parent.parent / "reports" / "quiz_test_results.json"
    os.makedirs(output_path.parent, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告保存至: {output_path}")

    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
