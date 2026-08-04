#!/usr/bin/env python3
"""
视频播放验证工具 v1.0 — 全量视频URL可访问性检查

对齐交付标准: 可信 → 所有教学资源可访问, 视频能正常播放

验证维度:
  1. URL可访问性 (HTTP HEAD → Content-Type)
  2. 视频元数据 (Content-Length, Accept-Ranges)
  3. Range请求支持 (部分下载验证)
  4. 响应时间

用法:
    python scripts/test_video_playback.py                       # 全量检查
    python scripts/test_video_playback.py --phase phase3        # 单Phase
    python scripts/test_video_playback.py --json-only           # JSON输出
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.platform_client import PlatformClient

# ── 配置 ──
TARGET_URL = "http://124.174.108.70"
REQUEST_TIMEOUT = 15
HEAD_BYTES = 2048  # 请求前2KB验证视频流
MAX_WORKERS = 6


# ═══════════════════════════════════════════════════════════
# 验证器
# ═══════════════════════════════════════════════════════════

class VideoPlaybackVerifier:
    """视频播放验证器"""

    # 有效的视频Content-Type
    VIDEO_MIME_TYPES = {
        "video/mp4", "video/webm", "video/ogg",
        "video/x-msvideo", "video/quicktime",
        "video/x-flv", "video/MP2T",
        "application/x-mpegURL",  # HLS
        "video/mp2t",             # HLS segment
        "application/dash+xml",   # MPEG-DASH
    }

    def __init__(self, base_url: str = TARGET_URL, verbose: bool = True):
        self.base_url = base_url.rstrip("/")
        self.verbose = verbose
        self.client = PlatformClient(base_url=self.base_url, verbose=False)
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.proxies = {"http": None, "https": None}
        self.results: list[dict] = []

    def collect_videos(self) -> list[dict]:
        """从所有Lesson中收集视频URL"""
        self.client.login()
        phases = self.client.get_main_phases()
        videos = []

        for p in phases:
            lessons = self.client.get_lessons(p["id"])
            for l in lessons:
                detail = self.client.get_lesson(l["id"])
                for v in detail.get("videos", []):
                    videos.append({
                        "phase_code": p["phase_code"],
                        "phase_title": p.get("title", ""),
                        "lesson_id": l["id"],
                        "lesson_title": l.get("title", ""),
                        "video_id": v.get("id"),
                        "video_title": v.get("title", ""),
                        "url": v.get("url", ""),
                    })
        return videos

    def check_video(self, video: dict) -> dict:
        """检查单个视频的可访问性"""
        result = dict(video)
        url = video["url"]
        result["accessible"] = False
        result["valid_video"] = False
        result["supports_range"] = False
        result["content_type"] = None
        result["content_length"] = None
        result["issues"] = []

        if not url:
            result["issues"].append("url_missing")
            return result

        # 处理相对路径
        if url.startswith("/"):
            url = self.base_url + url
        elif not url.startswith("http"):
            url = self.base_url + "/" + url.lstrip("/")

        result["resolved_url"] = url

        # 1. HEAD请求 — 检查URL可访问性 + Content-Type
        try:
            head_r = self.session.head(
                url, timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            result["status_code"] = head_r.status_code
            result["content_type"] = head_r.headers.get("Content-Type", "")
            content_length = head_r.headers.get("Content-Length")
            if content_length:
                result["content_length"] = int(content_length)

            if head_r.status_code < 400:
                result["accessible"] = True
            else:
                result["issues"].append(f"HTTP {head_r.status_code}")
                return result

        except requests.Timeout:
            result["status_code"] = -1
            result["issues"].append("timeout")
            return result
        except requests.ConnectionError:
            result["status_code"] = -2
            result["issues"].append("connection_error")
            return result
        except Exception as e:
            result["status_code"] = -3
            result["issues"].append(f"error:{str(e)[:50]}")
            return result

        # 2. 验证Content-Type是视频
        ct = (result["content_type"] or "").lower()
        is_video = any(vt in ct for vt in self.VIDEO_MIME_TYPES)
        result["valid_video"] = is_video
        if not is_video and ct:
            result["issues"].append(f"non_video_content_type:{ct}")

        # 3. 检查Range支持
        accept_ranges = head_r.headers.get("Accept-Ranges", "")
        result["supports_range"] = "bytes" in accept_ranges.lower()

        # 4. Range请求 — 获取前2KB验证数据流
        try:
            range_r = self.session.get(
                url,
                headers={"Range": f"bytes=0-{HEAD_BYTES - 1}"},
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            if range_r.status_code == 206:
                result["range_request_ok"] = True
                result["bytes_received"] = len(range_r.content)
            elif range_r.status_code == 200:
                # 不支持Range但能返回数据
                result["range_request_ok"] = True
                result["bytes_received"] = min(len(range_r.content), HEAD_BYTES)
            else:
                result["range_request_ok"] = False
                result["issues"].append(f"range_request_HTTP_{range_r.status_code}")
        except Exception as e:
            result["range_request_ok"] = False
            result["issues"].append(f"range_error:{str(e)[:50]}")

        # 综合判定
        result["pass"] = (
            result["accessible"]
            and result["valid_video"]
            and len(result["issues"]) == 0
        )

        return result

    # ── 主流程 ──

    def verify_all(self, phase_filter: str = None) -> dict:
        """全部视频验证"""
        print(f"[VIDEO CHECK] Platform: {self.base_url}")
        print(f"   Time: {datetime.now(timezone.utc).isoformat()}")

        all_videos = self.collect_videos()

        if phase_filter:
            all_videos = [v for v in all_videos if v["phase_code"] == phase_filter]
            print(f"   Filter: {phase_filter}")

        print(f"   Videos found: {len(all_videos)}")

        if not all_videos:
            print("   No videos to check.")
            return {
                "test_name": "video_playback",
                "platform_url": self.base_url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": {"total": 0, "pass": 0, "fail": 0, "issues": 0},
                "videos": [],
            }

        # 并发检查
        results = []
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(all_videos))) as executor:
            futures = {executor.submit(self.check_video, v): v for v in all_videos}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    original = futures[future]
                    results.append({**original, "error": str(e), "pass": False})

        # 按lesson_id排序
        results.sort(key=lambda x: (x.get("lesson_id", 0), x.get("video_id", 0)))

        # 统计
        passed = sum(1 for r in results if r.get("pass"))
        failed = sum(1 for r in results if not r.get("pass"))
        total_issues = sum(len(r.get("issues", [])) for r in results)

        # 按Phase分组
        by_phase: dict[str, dict] = {}
        for r in results:
            pc = r.get("phase_code", "unknown")
            if pc not in by_phase:
                by_phase[pc] = {"total": 0, "pass": 0, "videos": []}
            by_phase[pc]["total"] += 1
            if r.get("pass"):
                by_phase[pc]["pass"] += 1
            by_phase[pc]["videos"].append(r)

        # 打印
        for pc, stats in sorted(by_phase.items()):
            icon = "PASS" if stats["pass"] == stats["total"] else "FAIL"
            print(f"  [{icon}] {pc}: {stats['pass']}/{stats['total']} videos OK")

        if failed > 0:
            print(f"\n  Failed videos:")
            for r in results:
                if not r.get("pass"):
                    print(f"    - {r.get('video_title', '?')[:50]}: {r.get('issues', [])}")

        print(f"\n  Total: {passed}/{len(results)} pass | {total_issues} issues")

        return {
            "test_name": "video_playback",
            "platform_url": self.base_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": len(results),
                "pass": passed,
                "fail": failed,
                "issues": total_issues,
                "by_phase": {
                    pc: {"total": s["total"], "pass": s["pass"]}
                    for pc, s in by_phase.items()
                },
            },
            "videos": results,
        }


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="视频播放验证工具")
    parser.add_argument("--url", default=TARGET_URL, help=f"平台URL")
    parser.add_argument("--phase", help="按Phase过滤")
    parser.add_argument("--json-only", action="store_true", help="仅输出JSON")
    parser.add_argument("-o", "--output", help="输出JSON路径")
    args = parser.parse_args()

    verifier = VideoPlaybackVerifier(base_url=args.url)
    report = verifier.verify_all(phase_filter=args.phase)

    if args.json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    # 保存
    if args.output:
        path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"reports/video_playback_{ts}.json"

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[REPORT] {path}")

    return 0 if report["summary"]["fail"] == 0 else 1


if __name__ == "__main__":
    exit(main())
