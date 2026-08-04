#!/usr/bin/env python3
"""
平台内容全量验证器 v1.0 — 5 Phase x 23 Lesson x 110 Step

对齐 PRD 验收标准:
  AC-S01~S05: Step渲染验证
  AC-E01~E05: 异常处理验证
  BAT 可信标准: 每个验证项有明确证据

用法:
    python src/platform_content_validator.py --all-phases     # 全量验证
    python src/platform_content_validator.py --phase phase3    # 单Phase验证
    python src/platform_content_validator.py --lesson 4        # 单Lesson验证
    python src/platform_content_validator.py --quick           # 快速冒烟(每Phase首Lesson)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platform_client import PlatformClient

# ── 验证阈值 ──
MIN_STEP_FIELDS = {"goal", "instruction"}       # Step 至少需要这些字段
EXPECTED_RENDER_LAYERS = {"guide", "detailed"}   # 期望的渲染层 (standard可选)
RESOURCE_TIMEOUT = 15                            # 资源可达性检查超时(秒)
VIDEO_RANGE_BYTES = 2048                         # 视频检查: 请求前2KB


class ContentValidator:
    """平台内容全量验证器"""

    def __init__(self, base_url: str = None, verbose: bool = True):
        self.base_url = base_url or "http://124.174.108.70"
        self.verbose = verbose
        self.client = PlatformClient(base_url=self.base_url, verbose=False)
        # 用于资源检查的独立session (不带auth)
        self.resource_session = requests.Session()
        self.resource_session.trust_env = False
        self.resource_session.proxies = {"http": None, "https": None}

    # ═══════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════

    def validate_all_phases(self) -> dict:
        """全5 Phase全量验证 → 返回完整报告"""
        self.client.login()
        phases = self.client.get_main_phases()
        results = []
        total_steps = 0
        total_valid_steps = 0
        total_resources = 0
        total_broken_resources = 0
        total_videos = 0
        total_broken_videos = 0
        all_issues = []

        for p in phases:
            phase_result = self.validate_phase(p)
            results.append(phase_result)
            total_steps += phase_result["steps_total"]
            total_valid_steps += phase_result["steps_valid"]
            total_resources += phase_result["resources_total"]
            total_broken_resources += phase_result["resources_broken"]
            total_videos += phase_result["videos_total"]
            total_broken_videos += phase_result["videos_broken"]
            all_issues.extend(phase_result.get("issues", []))

        report = {
            "validator_version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform_url": self.base_url,
            "summary": {
                "phases_total": len(phases),
                "lessons_total": sum(p["lessons_total"] for p in results),
                "steps_total": total_steps,
                "steps_valid": total_valid_steps,
                "steps_valid_pct": round(total_valid_steps / total_steps * 100, 1) if total_steps else 0,
                "resources_total": total_resources,
                "resources_broken": total_broken_resources,
                "videos_total": total_videos,
                "videos_broken": total_broken_videos,
                "issues_total": len(all_issues),
                "pass": total_broken_resources == 0 and len(all_issues) == 0,
            },
            "phases": results,
            "issues_summary": all_issues[:50],  # 最多50条issue明细
        }
        return report

    def validate_phase(self, phase: dict) -> dict:
        """验证单个Phase的所有Lesson"""
        pid = phase["id"]
        phase_title = phase.get("title", "")
        phase_code = phase.get("phase_code", "")
        lessons = self.client.get_lessons(phase_id=pid)

        lesson_results = []
        for l in lessons:
            # get_lessons返回摘要不含steps → get_lesson获取完整详情
            detail = self.client.get_lesson(l["id"])
            lesson_results.append(self.validate_lesson(detail, phase_title))

        return {
            "phase_id": pid,
            "phase_code": phase_code,
            "phase_title": phase_title,
            "lessons_total": len(lessons),
            "steps_total": sum(lr["steps_total"] for lr in lesson_results),
            "steps_valid": sum(lr["steps_valid"] for lr in lesson_results),
            "resources_total": sum(lr["resources_total"] for lr in lesson_results),
            "resources_broken": sum(lr["resources_broken"] for lr in lesson_results),
            "videos_total": sum(lr["videos_total"] for lr in lesson_results),
            "videos_broken": sum(lr["videos_broken"] for lr in lesson_results),
            "lessons": lesson_results,
            "issues": [i for lr in lesson_results for i in lr.get("issues", [])],
        }

    def validate_lesson(self, lesson: dict, phase_title: str = "") -> dict:
        """验证单个Lesson: Steps + Resources + Videos"""
        lid = lesson["id"]
        title = lesson.get("title", "")
        steps = lesson.get("steps") or []
        resources = lesson.get("resources") or []
        videos = lesson.get("videos") or []

        issues = []

        # ── Step 验证 ──
        step_results = []
        valid_count = 0
        render_layers_found = set()
        for s in steps:
            sr = self._validate_step(s, lid)
            step_results.append(sr)
            if sr["valid"]:
                valid_count += 1
            else:
                issues.append({
                    "lesson_id": lid, "lesson_title": title,
                    "type": "step_incomplete",
                    "step_title": s.get("title", "?"),
                    "detail": sr.get("issue", ""),
                })
            for layer in sr.get("render_layers", []):
                render_layers_found.add(layer)

        # ── Resource 验证 ──
        resource_results = []
        broken_count = 0
        for r in resources:
            rr = self._validate_resource(r, lid)
            resource_results.append(rr)
            if not rr["accessible"]:
                broken_count += 1
                issues.append({
                    "lesson_id": lid, "lesson_title": title,
                    "type": "resource_broken",
                    "resource_title": r.get("title", "?"),
                    "url": r.get("url", "")[:120],
                    "detail": rr.get("error", "不可访问"),
                })

        # ── Video 验证 ──
        video_results = []
        video_broken = 0
        for v in videos:
            vr = self._validate_video(v, lid)
            video_results.append(vr)
            if not vr["playable"]:
                video_broken += 1
                issues.append({
                    "lesson_id": lid, "lesson_title": title,
                    "type": "video_broken",
                    "video_title": v.get("title", "?"),
                    "url": v.get("url", "")[:120],
                    "detail": vr.get("error", "不可播放"),
                })

        # ── Knowledge Points 基线 ──
        kp_defined = sum(1 for s in steps if s.get("knowledge_points"))

        return {
            "lesson_id": lid,
            "lesson_title": title,
            "phase_title": phase_title,
            "steps_total": len(steps),
            "steps_valid": valid_count,
            "steps_detail": step_results,
            "resources_total": len(resources),
            "resources_broken": broken_count,
            "resources_detail": resource_results,
            "videos_total": len(videos),
            "videos_broken": video_broken,
            "videos_detail": video_results,
            "render_layers_found": sorted(render_layers_found),
            "knowledge_points_defined": kp_defined,
            "issues": issues,
            "pass": valid_count == len(steps) and broken_count == 0 and video_broken == 0,
        }

    # ═══════════════════════════════════════════════════════
    # 原子验证
    # ═══════════════════════════════════════════════════════

    def _validate_step(self, step: dict, lesson_id: int) -> dict:
        """验证单个Step的结构完整性 (对齐 AC-S01)"""
        rp = step.get("render_payload") or {}
        layers = list(rp.keys())
        issue = ""

        # 检查 guide 层 (主要渲染层)
        guide = rp.get("guide") or rp.get("detailed") or {}
        if not guide:
            issue = "缺少 guide/detailed 渲染层"
        else:
            missing = [f for f in MIN_STEP_FIELDS if not guide.get(f)]
            if missing:
                issue = f"缺少字段: {missing}"
            elif not guide.get("checklist"):
                issue = "checklist 为空"

        valid = issue == ""
        return {
            "step_id": step.get("id"),
            "step_title": step.get("title", ""),
            "render_layers": layers,
            "has_goal": bool(guide.get("goal")),
            "has_instruction": bool(guide.get("instruction")),
            "has_checklist": bool(guide.get("checklist")),
            "has_agent_hint": bool(guide.get("agent_help_hint")),
            "has_safety_check": bool(guide.get("safety_check")),
            "knowledge_points": step.get("knowledge_points") or [],
            "valid": valid,
            "issue": issue,
        }

    def _validate_resource(self, resource: dict, lesson_id: int) -> dict:
        """验证资源URL可访问性 (HTTP HEAD)"""
        url = resource.get("url", "")
        resource_type = resource.get("resource_type", "")
        title = resource.get("title", "")

        if not url:
            return {"title": title, "url": "", "accessible": False,
                    "error": "URL为空", "type": resource_type}

        # 相对路径 → 拼接到平台base_url
        if url.startswith("/"):
            full_url = self.base_url.rstrip("/") + url
        elif url.startswith("http"):
            full_url = url
        else:
            full_url = self.base_url.rstrip("/") + "/" + url.lstrip("/")

        try:
            r = self.resource_session.head(
                full_url, timeout=RESOURCE_TIMEOUT,
                allow_redirects=True,
                headers={"User-Agent": "PlatformContentValidator/1.0"},
            )
            accessible = r.status_code < 400
            error = "" if accessible else f"HTTP {r.status_code}"
        except Exception as e:
            accessible = False
            error = str(e)[:100]

        return {
            "title": title, "url": url, "full_url": full_url,
            "accessible": accessible, "error": error, "type": resource_type,
        }

    def _validate_video(self, video: dict, lesson_id: int) -> dict:
        """验证视频可播放性 (HTTP Range请求, 检查206+Content-Type)"""
        url = video.get("url", "")
        title = video.get("title", "")

        if not url:
            return {"title": title, "url": "", "playable": False,
                    "error": "URL为空"}

        if url.startswith("/"):
            full_url = self.base_url.rstrip("/") + url
        elif url.startswith("http"):
            full_url = url
        else:
            full_url = self.base_url.rstrip("/") + "/" + url.lstrip("/")

        try:
            r = self.resource_session.get(
                full_url, timeout=RESOURCE_TIMEOUT,
                headers={
                    "Range": f"bytes=0-{VIDEO_RANGE_BYTES}",
                    "User-Agent": "PlatformContentValidator/1.0",
                },
            )
            # 206 Partial Content 或 200 都算可访问
            is_video = "video" in r.headers.get("Content-Type", "").lower()
            playable = r.status_code in (200, 206)
            error = ""
            if playable and not is_video:
                error = f"非视频Content-Type: {r.headers.get('Content-Type', '?')}"
        except Exception as e:
            playable = False
            error = str(e)[:100]

        return {
            "title": title, "url": url, "full_url": full_url,
            "playable": playable, "error": error,
        }

    # ═══════════════════════════════════════════════════════
    # 报告输出
    # ═══════════════════════════════════════════════════════

    def print_report(self, report: dict):
        """打印验证报告 (兼容 quick / phase / full 三种模式)"""
        s = report.get("summary", {})
        print("=" * 60)
        print("  平台内容验证报告")
        print("=" * 60)
        print(f"  平台: {report.get('platform_url', '?')}")
        print(f"  时间: {report.get('timestamp', '')[:19]}")

        if s:
            rt = s.get("resources_total", 0)
            rb = s.get("resources_broken", 0)
            vt = s.get("videos_total", 0)
            vb = s.get("videos_broken", 0)
            print(f"  Phase: {s.get('phases_total','?')} | Lesson: {s.get('lessons_total','?')} | Step: {s.get('steps_total','?')}")
            sv = s.get("steps_valid", 0); st = s.get("steps_total", 1)
            print(f"  Step完整性: {sv}/{st} ({s.get('steps_valid_pct','?')}%)")
            print(f"  资源可访问: {rt - rb}/{rt} (损坏: {rb})")
            print(f"  视频可播放: {vt - vb}/{vt} (损坏: {vb})")
            p = s.get("pass")
            print(f"  总体: {'[PASS]' if p else '[FAIL]'}")

        # 每Phase明细 (full mode)
        for ph in report.get("phases", []):
            rb2 = ph.get("resources_broken", 0)
            vb2 = ph.get("videos_broken", 0)
            ok = rb2 == 0 and vb2 == 0
            print(f"\n  {'[PASS]' if ok else '[FAIL]'} [{ph.get('phase_code','?')}] {ph.get('phase_title','')[:30]}: "
                  f"{ph.get('lessons_total','?')}L/{ph.get('steps_total','?')}S")

        # Lesson明细 (quick mode)
        for lr in report.get("lessons", []):
            ok = lr.get("pass", False)
            print(f"\n  {'[PASS]' if ok else '[FAIL]'} L{lr.get('lesson_id','?')} {lr.get('lesson_title','')[:40]}: "
                  f"{lr.get('steps_valid','?')}/{lr.get('steps_total','?')} steps, "
                  f"{lr.get('resources_broken','?')} broken resources")

        # Issues
        issues = report.get("issues_summary", [])
        if issues:
            print(f"\n  问题明细 (前{min(20, len(issues))}条):")
            for i in issues[:20]:
                print(f"    [{i.get('type','?')}] L{i.get('lesson_id','?')} {i.get('lesson_title','')[:30]}: {i.get('detail','')[:80]}")


def main():
    ap = argparse.ArgumentParser(description="AI+X 平台内容全量验证器")
    ap.add_argument("--all-phases", action="store_true", help="全5 Phase验证")
    ap.add_argument("--phase", type=str, help="单Phase验证 (phase1~phase5)")
    ap.add_argument("--lesson", type=int, help="单Lesson验证 (lesson_id)")
    ap.add_argument("--quick", action="store_true", help="快速冒烟: 每Phase首Lesson")
    ap.add_argument("--output", type=str, help="JSON报告输出路径")
    ap.add_argument("--url", type=str, default="http://124.174.108.70", help="平台URL")
    args = ap.parse_args()

    validator = ContentValidator(base_url=args.url)

    if args.lesson:
        validator.client.login()
        detail = validator.client.get_lesson(args.lesson)
        phase_title = ""
        result = validator.validate_lesson(detail, phase_title)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.phase:
        validator.client.login()
        phases = validator.client.get_main_phases()
        target = None
        for p in phases:
            if p.get("phase_code") == args.phase:
                target = p
                break
        if not target:
            print(f"[ERROR] Phase not found: {args.phase}")
            sys.exit(1)
        result = validator.validate_phase(target)
        validator.print_report({"summary": {}, "phases": [result], "issues_summary": result.get("issues", [])})
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        return

    if args.quick:
        validator.client.login()
        phases = validator.client.get_main_phases()
        results = []
        for p in phases:
            lessons = validator.client.get_lessons(phase_id=p["id"])
            if lessons:
                first_lid = lessons[0]["id"]
                detail = validator.client.get_lesson(first_lid)
                results.append(validator.validate_lesson(detail, p.get("title", "")))
        report = {
            "platform_url": validator.base_url,
            "validator_version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {"quick_mode": True, "lessons_total": len(results)},
            "phases": [], "issues_summary": [],
            "lessons": results,
        }
        validator.print_report(report)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        return

    # Default: --all-phases
    report = validator.validate_all_phases()
    validator.print_report(report)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {args.output}")

    sys.exit(0 if report["summary"]["pass"] else 1)


if __name__ == "__main__":
    main()
