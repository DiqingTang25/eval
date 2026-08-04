#!/usr/bin/env python3
"""
Quiz 专项测评器 v1.0
═══════════════════════════════════════════════════════
测试每个Phase最后一天Lesson的Quiz功能:
  - Quiz题目结构完整性 (question_text + options)
  - Quiz提交+评分
  - 各Phase Quiz覆盖率

关键发现 (2026-07-16):
  - 5个主Phase最后一天均有Quiz (共45题)
  - Phase1 L20: 10题 | Phase2 L25: 10题
  - Phase3 L9: 5题  | Phase4 L16: 10题
  - Phase5 L26: 10题
  - Quiz题目由AI Agent动态生成, 基于知识库
  - 提交后返回score, next_lesson_id (当前为null)

用法:
    python src/quiz_evaluator.py                    # 全5 Phase测试
    python src/quiz_evaluator.py --phase phase1     # 单Phase
    python src/quiz_evaluator.py --output report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platform_client import PlatformClient, DEFAULT_BASE_URL

# Phase最后一天Lesson映射
PHASE_LAST_LESSONS = {
    "phase1": {"lesson_id": 20, "title": "设备网关与 OpenAI-compatible 接口"},
    "phase2": {"lesson_id": 25, "title": "加工质量评价与数据分析"},
    "phase3": {"lesson_id": 9, "title": "灯带与音频边缘 AI"},
    "phase4": {"lesson_id": 16, "title": "AI驱动的具身协同实战"},
    "phase5": {"lesson_id": 26, "title": "AI 机器人项目启动与系统集成"},
}


class QuizEvaluator:
    """Quiz专项测评器"""

    def __init__(self, base_url: str = None, verbose: bool = True):
        self.base_url = base_url or DEFAULT_BASE_URL
        self.verbose = verbose
        self.client = PlatformClient(base_url=self.base_url, verbose=False, timeout=20)

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def evaluate_phase_quiz(self, phase_code: str) -> dict:
        """测试单个Phase最后Lesson的完整Quiz流程"""
        info = PHASE_LAST_LESSONS.get(phase_code)
        if not info:
            return {"phase_code": phase_code, "error": "Unknown phase"}

        lid = info["lesson_id"]
        title = info["title"]
        self._log(f"\n{'='*60}")
        self._log(f"  {phase_code} L{lid}: {title}")
        self._log(f"{'='*60}")

        result = {
            "phase_code": phase_code,
            "lesson_id": lid,
            "lesson_title": title,
            "quiz_start": None,
            "quiz_submit": None,
            "questions": [],
            "issues": [],
        }

        # ── 1. Quiz启动 ──
        start_resp = self.client.quiz_start(lid)
        result["quiz_start"] = {
            "ok": start_resp.get("ok"),
            "status_code": start_resp.get("status_code"),
            "error": start_resp.get("error", ""),
        }

        if not start_resp.get("ok"):
            result["issues"].append(f"Quiz启动失败: {start_resp.get('error','')[:100]}")
            return result

        questions = start_resp.get("questions", [])
        result["quiz_start"]["question_count"] = len(questions)

        # ── 2. 题目结构验证 ──
        for i, q in enumerate(questions):
            q_info = {
                "question_id": q.get("question_id", f"?_{i}"),
                "question_text": (q.get("question_text", "") or "")[:120],
                "option_count": len(q.get("options", [])),
                "issues": [],
            }
            if not q.get("question_text"):
                q_info["issues"].append("缺少question_text")
            if not q.get("options"):
                q_info["issues"].append("缺少options")
            elif len(q.get("options", [])) < 2:
                q_info["issues"].append(f"选项不足: {len(q['options'])}个")
            # 检查选项格式
            for o in q.get("options", []):
                if not o.get("id") or not o.get("text"):
                    q_info["issues"].append(f"选项格式异常: missing id or text")
                    break
            if q_info["issues"]:
                result["issues"].append(f"Q{i+1}: {q_info['issues']}")
            result["questions"].append(q_info)

        # ── 3. Quiz提交 ──
        session_id = start_resp.get("quiz_session_id", "")
        if session_id and questions:
            answers = []
            for q in questions:
                opts = q.get("options", [])
                answers.append({
                    "question_id": q["question_id"],
                    "selected_answer": opts[0]["id"] if opts else "A",
                })
            submit_resp = self.client.quiz_submit(session_id, answers)
            result["quiz_submit"] = {
                "ok": submit_resp.get("ok"),
                "status_code": submit_resp.get("status_code"),
                "score": submit_resp.get("score"),
                "next_lesson_id": submit_resp.get("next_lesson_id"),
                "error": submit_resp.get("error", ""),
            }
            if not submit_resp.get("ok"):
                result["issues"].append(f"Quiz提交失败: {submit_resp.get('error','')[:100]}")

        # ── 4. 汇总 ──
        valid_qs = sum(1 for q in result["questions"] if not q["issues"])
        result["summary"] = {
            "total_questions": len(questions),
            "valid_questions": valid_qs,
            "has_issues": len(result["issues"]) > 0,
            "quiz_working": start_resp.get("ok", False) and result.get("quiz_submit", {}).get("ok", False),
        }

        icon = "[OK]" if result["summary"]["quiz_working"] else "[FAIL]"
        score_str = result.get("quiz_submit", {}).get("score", "N/A")
        self._log(f"  {icon} {len(questions)}题, 结构完整{valid_qs}/{len(questions)}, score={score_str}")

        return result

    def evaluate_all_phases(self) -> dict:
        """全5 Phase Quiz测评"""
        self._log("=" * 60)
        self._log("  Quiz 专项测评 — 全5 Phase最后一天")
        self._log("=" * 60)
        self.client.login()

        phase_results = {}
        all_issues = []
        total_questions = 0
        total_valid = 0
        phases_working = 0

        for pc in ["phase1", "phase2", "phase3", "phase4", "phase5"]:
            pr = self.evaluate_phase_quiz(pc)
            phase_results[pc] = pr
            all_issues.extend(pr.get("issues", []))
            total_questions += pr["summary"]["total_questions"]
            total_valid += pr["summary"]["valid_questions"]
            if pr["summary"]["quiz_working"]:
                phases_working += 1

        report = {
            "evaluator": "quiz_evaluator v1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform_url": self.base_url,
            "summary": {
                "phases_with_quiz": phases_working,
                "total_phases": 5,
                "total_questions": total_questions,
                "valid_questions": total_valid,
                "structure_pass_rate": round(total_valid / total_questions * 100, 1) if total_questions else 0,
                "all_phases_quiz_available": phases_working == 5,
                "issues_count": len(all_issues),
            },
            "phase_results": phase_results,
            "issues": all_issues,
        }

        self._print_final_summary(report)
        return report

    def _print_final_summary(self, report: dict):
        s = report["summary"]
        print(f"\n{'='*60}")
        print(f"  Quiz 测评总结")
        print(f"{'='*60}")
        print(f"  Phase覆盖: {s['phases_with_quiz']}/{s['total_phases']} Phase有Quiz")
        print(f"  题目总计: {s['total_questions']}题")
        print(f"  结构完整率: {s['structure_pass_rate']}%")
        print(f"  全Phase可用: {'[OK]' if s['all_phases_quiz_available'] else '[FAIL]'}")
        if s["issues_count"]:
            print(f"  问题: {s['issues_count']}个")
            for i in report["issues"][:10]:
                print(f"    - {i}")


def main():
    ap = argparse.ArgumentParser(description="AI+X Quiz专项测评器")
    ap.add_argument("--phase", type=str, help="单Phase测试 (phase1~phase5)")
    ap.add_argument("--output", type=str, help="JSON报告输出路径")
    ap.add_argument("--url", type=str, default=DEFAULT_BASE_URL, help="平台URL")
    args = ap.parse_args()

    evaluator = QuizEvaluator(base_url=args.url)

    if args.phase:
        evaluator.client.login()
        result = evaluator.evaluate_phase_quiz(args.phase)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        report = evaluator.evaluate_all_phases()

    if args.output and not args.phase:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {args.output}")


if __name__ == "__main__":
    main()
