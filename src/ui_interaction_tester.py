"""
非 Agent 功能覆盖检查 (UIInteractionTester)

诚实原则: 只报告能真实验证的东西。
  - ✅ ok:  DOM 存在且可达 / 资源 HTTP 可加载 (已验证)
  - ⚠️ partial: 功能存在但完整交互需逐页逆向(如自测作答/前端解锁状态机)
  - ❌ na: 需真实硬件, 自动化不可测(串口/烧录/传感器)

实测依据(scripts/probe_*.py): 平台是单文件 SPA, 登录为 modal, 全部功能区一次性渲染在 DOM。
因此"存在性/可达性"可稳定检测; 视频用 HTTP 请求验证真实可加载性。
"""
from __future__ import annotations
import os
import requests

DEFAULT_BASE = "http://124.174.108.70"

# 功能清单: (key, 名称, 关键词, 状态, 说明)
FEATURE_CHECKS = [
    ("login", "登录流程", ["登录平台", "演示密码", "我是学生"], "ok", "modal 登录, 账号/密码/提交齐全, 后端JWT"),
    ("learning_mode", "学习方式选择", ["带带我", "我自己来"], "ok", "引导式 vs 自主式两种模式入口"),
    ("self_test", "课前自测", ["课前自测", "判断题", "10 题自测", "10题自测"], "partial", "自测题存在且有提交入口; 作答为排序/判断式(非标准表单), 完整作答需逐页逆向"),
    ("unlock", "课程解锁机制", ["课程未解锁", "完成当前课时", "才会解锁", "已完成事项"], "partial", "解锁状态可读; 真正触发解锁是前端状态机(无后端API), 不能凭API直接解锁"),
    ("panel_troubleshoot", "故障急诊室", ["故障急诊室"], "ok", "排错辅助面板"),
    ("panel_kb", "知识库 & FAQ", ["知识库", "FAQ"], "ok", "课程知识库检索面板"),
    ("panel_doc", "文档解释器", ["文档解释器", "datasheet"], "ok", "datasheet→大白话, 有输入textarea"),
    ("panel_notes", "实验笔记", ["实验笔记"], "ok", "学生记录面板(textarea)"),
    ("panel_dashboard", "教学驾驶舱", ["教学驾驶舱"], "ok", "教师端数据面板"),
    ("panel_editor", "课程编辑器", ["课程编辑器"], "ok", "教师录入课程/Demo视频链接"),
    ("learning_map", "学习路径地图", ["学习路径地图", "五个阶段"], "ok", "Phase 01-03 阶段导航"),
]


class UIInteractionTester:
    """非 Agent 功能覆盖检查 (存在性/可达性 + 视频可加载性)"""

    def __init__(self, base_url: str = DEFAULT_BASE, username: str = "student001",
                 password: str = "123456", verbose: bool = True):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verbose = verbose

    def _log(self, m):
        if self.verbose:
            print(m)

    def run(self) -> dict:
        self._log(f"\n{'='*60}\n🧩 非Agent功能覆盖检查: {self.base_url}")
        checks = []
        # ── 抓取认证后整页文本(SPA 一次性渲染全部功能区) ──
        page_text, videos = self._load_authenticated_dom()
        if page_text is None:
            self._log("  ⚠️ 页面加载失败, 功能覆盖检查跳过")
            return {}

        # ── 功能存在性/可达性 ──
        for key, name, kws, status, note in FEATURE_CHECKS:
            hit = any(kw in page_text for kw in kws)
            st = status if hit else "missing"
            checks.append({"key": key, "name": name, "status": st,
                           "detail": note if hit else "页面未检出该功能"})
            icon = {"ok": "✅", "partial": "⚠️", "missing": "❌"}[st]
            self._log(f"  {icon} {name}: {st}")

        # ── 视频真实可加载性(HTTP 请求验证) ──
        checks.append(self._check_videos(videos))

        # ── 硬件(诚实标注不可测) ──
        checks.append({"key": "hardware", "name": "真实硬件交互(串口/烧录/传感器)",
                       "status": "na", "detail": "物理层, 浏览器自动化不可测(需真实设备)"})

        ok = sum(1 for c in checks if c["status"] == "ok")
        partial = sum(1 for c in checks if c["status"] == "partial")
        na = sum(1 for c in checks if c["status"] == "na")
        missing = sum(1 for c in checks if c["status"] == "missing")
        total = len(checks)
        # 覆盖分: ok=1, partial=0.5, na/ missing 不计入可测分母
        testable = total - na
        cov = round((ok + 0.5 * partial) / testable * 100) if testable else 0
        self._log(f"  📊 功能覆盖: 可稳定测{ok} / 部分{partial} / 不可测(硬件){na} / 缺失{missing} → 覆盖率{cov}%")
        return {"checks": checks, "coverage_pct": cov,
                "ok": ok, "partial": partial, "na": na, "missing": missing, "total": total}

    def _load_authenticated_dom(self):
        """API登录拿JWT → 注入SPA → 返回(整页文本, 视频src列表)"""
        os.environ.pop("PLAYWRIGHT_PROXY", None)
        try:
            s = requests.Session(); s.trust_env = False; s.proxies = {"http": None, "https": None}
            tok = s.post(self.base_url + "/api/auth/login",
                         json={"username": self.username, "password": self.password},
                         timeout=15).json().get("token", "")
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                b = p.chromium.launch(headless=True,
                                      args=["--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server"])
                ctx = b.new_context(viewport={"width": 1440, "height": 900})
                for pat in ["**/fonts.googleapis.com/**", "**/fonts.gstatic.com/**",
                            "**/*.{woff,woff2,ttf,otf,eot}"]:
                    ctx.route(pat, lambda r: r.abort())
                pg = ctx.new_page()
                pg.goto(self.base_url, wait_until="commit", timeout=60000)
                pg.wait_for_timeout(2000)
                if tok:
                    pg.evaluate("(t)=>{for(const k of ['token','jwt','authToken','access_token','auth_token','userToken']) localStorage.setItem(k,t);}", tok)
                    pg.reload(wait_until="commit")
                pg.wait_for_timeout(3500)
                text = pg.evaluate("() => document.body.textContent")
                videos = pg.evaluate("() => Array.from(document.querySelectorAll('video')).map(v => v.src || v.currentSrc || (v.querySelector('source')||{}).src || '')")
                b.close()
                return text, [v for v in videos if v]
        except Exception as e:
            self._log(f"  加载异常: {str(e)[:80]}")
            return None, []

    def _check_videos(self, videos: list[str]) -> dict:
        """用 HTTP 请求验证视频资源真实可加载"""
        if not videos:
            return {"key": "video", "name": "教学视频加载", "status": "missing",
                    "detail": "页面未检出 <video> 资源"}
        s = requests.Session(); s.trust_env = False; s.proxies = {"http": None, "https": None}
        results = []
        real_video = False
        for url in videos[:3]:
            full = url if url.startswith("http") else self.base_url + "/" + url.lstrip("/")
            try:
                r = s.get(full, headers={"Range": "bytes=0-2047"}, timeout=15, stream=True)
                ct = r.headers.get("Content-Type", "")
                cl = r.headers.get("Content-Length") or r.headers.get("Content-Range", "")
                is_video = r.status_code in (200, 206) and ct.startswith("video")
                if is_video:
                    real_video = True
                    results.append(f"✅HTTP{r.status_code} {ct} {cl}")
                elif r.status_code in (200, 206):
                    # 200 但不是视频(多为 SPA 回退返回 HTML) → 资源实际不存在
                    results.append(f"⚠️HTTP{r.status_code} 非视频({ct}) — 资源缺失/SPA回退")
                else:
                    results.append(f"❌HTTP{r.status_code}")
                r.close()
            except Exception as e:
                results.append(f"❌ {str(e)[:40]}")
        return {"key": "video", "name": "教学视频加载",
                "status": "ok" if real_video else "partial",
                "detail": ("视频资源真实可加载: " if real_video
                           else "检出<video>元素但资源未真正提供视频流(实测): ") + " | ".join(results)}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    t = UIInteractionTester()
    import json
    print(json.dumps(t.run(), ensure_ascii=False, indent=2))
