"""
Deep Explorer: LLM驱动的递归深度探索 Agent

借鉴:
  - Explorbot: Research → Plan → Execute → Recursive exploration
  - A2A 论文: LLM 自主决定交互目标 (91.9% 发现率)
  - Web Agent: 状态去重 + 深度递归 + 特征发现

核心创新: LLM 在每一页自主规划"接下来探索什么", 不需要任何平台预设知识。
"""

from __future__ import annotations

import hashlib
import json
import time
import re as _re
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page

logger = __import__("logging").getLogger(__name__)

# ── 策略记忆文件路径 ──
STRATEGY_MEMORY_PATH = Path(__file__).parent.parent.parent / "output" / "platform_probe" / "exploration_strategies.json"


# ═══════════════════════════════════════════════════════════════
# 页面状态追踪 (避免重复探索)
# ═══════════════════════════════════════════════════════════════

def _page_fingerprint(page: Page) -> str:
    """生成页面指纹用于去重: URL + 标题 + body 文本前500字符的hash"""
    try:
        url = page.url.split("?")[0].split("#")[0]  # 去掉query和hash
        title = page.title()
        body = page.inner_text("body")[:500]
        raw = f"{url}|{title}|{body}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]
    except Exception:
        return hashlib.md5(str(time.time()).encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════════
# 交互元素提取 (全类型)
# ═══════════════════════════════════════════════════════════════

def _extract_all_interactive(page: Page, max_elements: int = 80) -> list[dict]:
    """提取页面上所有可交互元素 — 不只按钮/链接, 还包括输入框/上传/编辑器等.

    返回结构:
      [{index, tag, type, role, text, aria_label, classes, id, href,
        x, y, w, h, is_visible, in_form, input_type, placeholder}]
    """
    elements = []
    seen = set()

    # 多种交互元素
    selectors = [
        "button:visible", "a:visible", "[role='button']:visible",
        "[role='tab']:visible", "[role='menuitem']:visible",
        "input:visible", "select:visible", "textarea:visible",
        "[contenteditable='true']:visible",
        "[role='textbox']:visible", "[role='combobox']:visible",
        "[role='radio']:visible", "[role='checkbox']:visible",
        "[role='switch']:visible", "[role='slider']:visible",
        # 文件上传
        "input[type='file']",
        # 视频/音频
        "video, audio",
    ]

    for sel in selectors:
        if len(elements) >= max_elements:
            break
        try:
            for el in page.locator(sel).all():
                if len(elements) >= max_elements:
                    break
                try:
                    # 去重
                    try:
                        text = el.inner_text().strip()[:80]
                    except Exception:
                        text = ""
                    tag = el.evaluate("el => el.tagName.toLowerCase()")
                    el_id = el.get_attribute("id") or ""
                    dedup_key = f"{tag}|{text[:40]}|{el_id}"
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    # 属性
                    aria_label = el.get_attribute("aria-label") or ""
                    role_attr = el.get_attribute("role") or ""
                    classes = el.get_attribute("class") or ""
                    href = el.get_attribute("href") or ""
                    input_type = el.get_attribute("type") or ""
                    placeholder = el.get_attribute("placeholder") or ""

                    # 推断 role
                    if role_attr:
                        inferred_role = role_attr
                    elif tag == "button":
                        inferred_role = "button"
                    elif tag == "a":
                        inferred_role = "link"
                    elif tag == "input":
                        inferred_role = input_type if input_type else "textbox"
                    elif tag in ("select", "textarea"):
                        inferred_role = tag
                    else:
                        inferred_role = tag

                    # 位置大小
                    box = None
                    try:
                        box = el.bounding_box()
                    except Exception:
                        pass

                    # 是否可见
                    visible = True
                    try:
                        visible = el.is_visible()
                    except Exception:
                        pass

                    # 是否在表单内
                    in_form = False
                    try:
                        in_form = el.evaluate("""el => {
                            let p = el.parentElement;
                            for (let i = 0; i < 6 && p; i++) {
                                if (p.tagName && p.tagName.toLowerCase() === 'form') return true;
                                p = p.parentElement;
                            }
                            return false;
                        }""")
                    except Exception:
                        pass

                    elements.append({
                        "index": len(elements),
                        "tag": tag,
                        "type": input_type,
                        "role": inferred_role,
                        "text": text,
                        "aria_label": aria_label,
                        "classes": classes[:120],
                        "id": el_id[:60],
                        "href": href[:200],
                        "placeholder": placeholder[:80],
                        "x": round(box["x"]) if box else 0,
                        "y": round(box["y"]) if box else 0,
                        "w": round(box["width"]) if box else 0,
                        "h": round(box["height"]) if box else 0,
                        "is_visible": visible,
                        "in_form": in_form,
                    })
                except Exception:
                    continue
        except Exception:
            continue

    return elements


# ═══════════════════════════════════════════════════════════════
# 页面特征检测 (quiz/upload/chat/code/video)
# ═══════════════════════════════════════════════════════════════

def _detect_features(page: Page) -> dict:
    """检测当前页面的功能特征 — 不做假设, 只看DOM证据."""
    features = {
        "has_quiz": False,
        "has_file_upload": False,
        "has_chat": False,
        "has_code_editor": False,
        "has_video": False,
        "has_form": False,
        "quiz_evidence": [],
        "chat_evidence": [],
        "code_evidence": [],
    }

    try:
        html = page.content().lower()
        body_text = page.inner_text("body").lower()

        # Quiz 检测: 多选题/单选题/判断题模式
        quiz_indicators = [
            "multiple choice", "single choice", "true or false",
            "单选题", "多选题", "判断题", "选择题",
            "radio", "checkbox", "submit answer", "提交答案",
            "question", "题目", "score", "得分",
        ]
        for ind in quiz_indicators:
            if ind in html or ind in body_text:
                features["has_quiz"] = True
                features["quiz_evidence"].append(ind)

        # 文件上传检测
        if page.locator("input[type='file']").count() > 0:
            features["has_file_upload"] = True
        upload_texts = ["upload", "上传", "choose file", "选择文件",
                        "drag and drop", "拖拽", "attachment", "附件"]
        for ut in upload_texts:
            if ut in html:
                features["has_file_upload"] = True
                break

        # 聊天/AI助手检测
        chat_classes = ["chat", "message", "assistant", "agent", "conversation",
                        "dialog", "messaging", "chatbot", "bot", "copilot"]
        for cc in chat_classes:
            if cc in html:
                features["has_chat"] = True
                features["chat_evidence"].append(cc)
        # 常见聊天UI元素
        if page.locator("[class*='chat'], [class*='message'], [class*='assistant']").count() > 0:
            features["has_chat"] = True
            features["chat_evidence"].append("chat_widget_found")

        # 代码编辑器检测
        code_indicators = ["codemirror", "monaco", "ace-editor", "ace_editor",
                           "python", "javascript", "console", "terminal",
                           "代码", "编程", "coding", "editor", "sandbox"]
        for ci in code_indicators:
            if ci in html:
                features["has_code_editor"] = True
                features["code_evidence"].append(ci)

        # 视频检测
        if page.locator("video").count() > 0:
            features["has_video"] = True

        # 表单检测
        if page.locator("form").count() > 0:
            features["has_form"] = True

    except Exception:
        pass

    return features


# ═══════════════════════════════════════════════════════════════
# LLM 探索规划 (核心: 让LLM决定探索什么)
# ═══════════════════════════════════════════════════════════════

def _llm_plan_exploration(
    page: Page,
    elements: list[dict],
    features: dict,
    already_clicked: set[str],
    text_api_key: str,
    text_model: str,
    text_base_url: str,
    max_actions: int = 8,
    verbose: bool = True,
    past_strategies: str = "",
) -> list[dict]:
    """让LLM分析当前页面, 规划探索动作.

    LLM看到: 页面文本 + 交互元素列表 + 已探索状态
    LLM决定: 接下来点击/交互什么来发现新内容

    这是纯粹的语义理解, 没有任何平台预设.
    """
    import requests as req

    # 页面摘要
    try:
        body = page.inner_text("body")[:3000]
    except Exception:
        body = ""
    title = page.title()
    url = page.url

    # 元素摘要 (给LLM足够信息但不过量)
    el_summary = []
    for el in elements[:60]:
        el_summary.append({
            "idx": el["index"],
            "role": el["role"],
            "tag": el["tag"],
            "text": el["text"][:60],
            "type": el.get("type", ""),
            "placeholder": el.get("placeholder", ""),
            "href": el.get("href", "")[:80] if el.get("href") else "",
            "size": f"{el['w']}x{el['h']}" if el["w"] > 0 else "?",
        })

    # 已点击摘要
    clicked_summary = list(already_clicked)[:20] if already_clicked else ["(none)"]

    # ── 如果有过去的策略记忆, 加入prompt ──
    past_strategies_text = ""
    if past_strategies:
        past_strategies_text = f"""
PAST EXPLORATION STRATEGIES (learned from previous platforms — use these principles):
{past_strategies}
"""

    prompt = f"""You are an autonomous web exploration agent. You are exploring a web application to discover ALL its content, features, and interactive capabilities.
{past_strategies_text}
CURRENT PAGE:
  URL: {url}
  Title: {title}
  Features detected: {json.dumps({k: v for k, v in features.items() if v})}

PAGE TEXT (first 3000 chars):
{body[:3000]}

INTERACTIVE ELEMENTS (indexed):
{json.dumps(el_summary, ensure_ascii=False, indent=2)}

ALREADY EXPLORED (text signatures of clicked elements — DO NOT repeat these):
{json.dumps(clicked_summary, ensure_ascii=False)}

YOUR TASK: Plan up to {max_actions} interactions to discover NEW content and features on this page.
Think like an explorer:
  1. What leads to DEEPER content? (lessons, exercises, quizzes, projects)
  2. What reveals HIDDEN features? (tabs, accordions, modals, dropdowns, side panels)
  3. What interactive widgets exist? (file uploads, code editors, chat, video players)
  4. What multi-step flows exist? (wizards with next/prev, forms, multi-tab content)
  5. Are there navigation elements that go to completely different sections?

PRIORITIZE (in order):
  - Links/buttons that navigate to lesson/course content pages
  - Widgets that reveal interactive features (quizzes, coding, chat)
  - Multi-step navigation (next page, pagination, tabs)
  - File uploads and forms
  - Sidebar navigation and breadcrumbs

AVOID:
  - Elements already in "ALREADY EXPLORED" list
  - Logout, account settings, language switchers, help/about links
  - External links (different domain)
  - Pure decorative elements

Return ONLY a JSON array (no markdown, no explanation):
[
  {{"index": <int>, "action": "click", "priority": 1, "reason": "<1 sentence>"}},
  {{"index": <int>, "action": "click", "priority": 2, "reason": "<1 sentence>"}},
  ...
]
If the page has no more unexplored meaningful elements, return []."""

    try:
        resp = req.post(
            f"{text_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {text_api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": text_model,
                "messages": [
                    {"role": "system",
                     "content": "You are an autonomous web exploration agent. You plan which elements to interact with to discover new content. Return ONLY valid JSON array. No markdown, no explanation outside JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2000,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            if verbose:
                print(f"  [DeepEx:Plan] LLM HTTP {resp.status_code}")
            return []

        content = resp.json()["choices"][0]["message"]["content"]
        try:
            plan = json.loads(content)
            if isinstance(plan, list):
                # 按 priority 排序
                plan.sort(key=lambda x: x.get("priority", 99))
                if verbose:
                    print(f"  [DeepEx:Plan] LLM 规划了 {len(plan)} 个探索动作")
                    for a in plan[:5]:
                        print(f"    #{a['index']}: {a.get('reason', '?')[:80]}")
                return plan
        except json.JSONDecodeError:
            m = _re.search(r'\[[\s\S]*\]', content)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        return []
    except Exception as e:
        if verbose:
            print(f"  [DeepEx:Plan] LLM 规划失败: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
# 启发式动作评分 (LLM不可用时的回退)
# ═══════════════════════════════════════════════════════════════

def _heuristic_plan(elements: list[dict], already_clicked: set[str],
                    max_actions: int = 10) -> list[dict]:
    """当LLM不可用时, 用启发式规则规划探索."""
    plan = []

    # 导航友好 CSS class 模式 (框架通用)
    nav_patterns = ["card", "lesson", "course", "module", "phase", "step",
                    "item", "link", "nav-item", "menu-item", "tab", "chapter",
                    "unit", "topic", "exercise", "quiz", "project"]
    widget_patterns = ["upload", "chat", "editor", "code", "video", "player",
                       "form", "input", "submit", "question", "answer"]

    for el in elements:
        if len(plan) >= max_actions:
            break
        text = el.get("text", "")
        classes = el.get("classes", "").lower()
        role = el.get("role", "")
        tag = el.get("tag", "")

        # 去重
        dedup_key = f"{text[:30]}|{el.get('id','')}"
        if dedup_key in already_clicked:
            continue
        if len(text) < 1:
            continue

        # 跳过危险的
        danger = ["logout", "delete", "remove", "退出", "删除"]
        if any(d in (text + classes).lower() for d in danger):
            continue

        score = 0

        # 导航元素加分
        if tag == "a" and el.get("href", ""):
            score += 0.5  # 链接可能导航到新页面
        if any(p in classes for p in nav_patterns):
            score += 0.3
        if role in ("tab", "menuitem"):
            score += 0.3

        # 交互组件加分
        if any(p in classes for p in widget_patterns):
            score += 0.4

        # 按钮加分 (可能有交互)
        if tag == "button":
            score += 0.2

        # 输入框加分
        if tag == "input" and el.get("type") == "file":
            score += 0.5

        if score > 0.3:
            plan.append({
                "index": el["index"],
                "action": "click",
                "priority": int((1 - score) * 10),
                "reason": f"heuristic score={score:.2f} role={role}",
            })

    plan.sort(key=lambda x: x["priority"])
    return plan[:max_actions]


# ═══════════════════════════════════════════════════════════════
# 核心: 递归深度探索器
# ═══════════════════════════════════════════════════════════════

class DeepExplorer:
    """LLM驱动的递归深度探索器.

    每一页: 提取元素 → LLM规划动作 → 逐个执行 → 新状态 → 递归探索 → 回退.
    不做任何平台假设, 纯靠 LLM 语义理解决定探索路径.
    """

    def __init__(
        self,
        page: Page,
        home_url: str,
        text_api_key: str = "",
        text_model: str = "deepseek-chat",
        text_base_url: str = "https://api.deepseek.com/v1",
        max_depth: int = 8,
        max_total_interactions: int = 150,
        verbose: bool = True,
        diag: list | None = None,
    ):
        self.page = page
        self.home_url = home_url.rstrip("/")
        self.text_api_key = text_api_key
        self.text_model = text_model
        self.text_base_url = text_base_url
        self.max_depth = max_depth
        self.max_total_interactions = max_total_interactions
        self.verbose = verbose
        self.diag = diag if diag is not None else []

        # 状态追踪
        self.visited_fingerprints: set[str] = set()
        self.already_clicked: set[str] = set()
        self.interaction_count = 0
        self._past_strategies = ""  # 从策略记忆加载

        # 发现结果
        self.discovered_steps: list[dict] = []
        self.discovered_features: list[dict] = []
        self.exploration_path: list[dict] = []  # 探索路径记录

    def explore(self) -> tuple[list[dict], list[dict], list[dict]]:
        """主入口: 加载过去策略 → 递归探索 → LLM反思写入新策略."""
        self.diag.append("=== DeepEx Deep Explorer started ===")
        self.diag.append(f"max_depth={self.max_depth}, max_interactions={self.max_total_interactions}")
        self.diag.append(f"LLM: {'available' if self.text_api_key else 'N/A'}")

        # ── 加载过去策略记忆 ──
        self._past_strategies = self._load_strategy_memory()

        # 回到首页
        self._go_home()

        # 开始递归探索 (可能因 browser crash 等原因部分失败)
        try:
            self._explore(depth=0, source="home")
        except Exception as e:
            self.diag.append(f"Explore interrupted: {e}")

        # ── LLM 反思并保存新策略 (即使探索部分失败, 仍保存已学到的) ──
        try:
            self._save_strategy_memory()
        except Exception as e:
            self.diag.append(f"Strategy save failed: {e}")

        self.diag.append(f"=== DeepEx Deep Explorer DONE ===")
        self.diag.append(f"Steps: {len(self.discovered_steps)}, "
                        f"Features: {len(self.discovered_features)}, "
                        f"Interactions: {self.interaction_count}, "
                        f"Visited states: {len(self.visited_fingerprints)}")

        return self.discovered_steps, self.discovered_features, self.exploration_path

    # ── 内部方法 ──

    def _go_home(self):
        """回到首页."""
        try:
            self.page.goto(self.home_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(3)
        except Exception:
            try:
                self.page.reload(wait_until="domcontentloaded", timeout=15000)
                time.sleep(3)
            except Exception:
                pass

    def _explore(self, depth: int, source: str):
        """递归探索当前页面.

        :param depth: 当前深度
        :param source: 从哪里来的 (用于日志)
        """
        # 检查预算
        if depth > self.max_depth:
            self.diag.append(f"[d={depth}] max depth reached, stopping")
            return
        if self.interaction_count >= self.max_total_interactions:
            self.diag.append(f"[d={depth}] interaction budget exhausted ({self.interaction_count})")
            return

        # 状态去重
        fp = _page_fingerprint(self.page)
        if fp in self.visited_fingerprints:
            return
        self.visited_fingerprints.add(fp)

        title = self.page.title()
        url = self.page.url
        self.diag.append(f"\n[d={depth}] Exploring: {title[:80]} | {url[:100]}")
        self.diag.append(f"[d={depth}] Interaction {self.interaction_count}/{self.max_total_interactions}, "
                        f"states visited: {len(self.visited_fingerprints)}")

        if self.verbose:
            print(f"\n  [DeepEx d={depth}] {title[:60]}")

        # Step 1: 提取当前页面的 steps
        from .step_extractor import extract_steps_with_llm
        try:
            steps = extract_steps_with_llm(
                page=self.page,
                text_api_key=self.text_api_key,
                text_model=self.text_model,
                text_base_url=self.text_base_url,
                verbose=False,
            )
            if steps:
                for s in steps:
                    s["discovered_at_depth"] = depth
                    s["discovered_from"] = source
                self.discovered_steps.extend(steps)
                self.diag.append(f"[d={depth}] Found {len(steps)} steps")
                if self.verbose:
                    for s in steps[:5]:
                        print(f"    Step: {s['title'][:80]}")
        except Exception as e:
            self.diag.append(f"[d={depth}] Step extraction failed: {e}")

        # Step 2: 检测页面特征
        features = _detect_features(self.page)
        active_features = {k: v for k, v in features.items() if v and k != "quiz_evidence"
                          and k != "chat_evidence" and k != "code_evidence"}
        if active_features:
            self.discovered_features.append({
                "depth": depth,
                "url": url,
                "title": title,
                "features": active_features,
                "evidence": {k: features.get(k, []) for k in
                            ["quiz_evidence", "chat_evidence", "code_evidence"]},
            })
            self.diag.append(f"[d={depth}] Features: {list(active_features.keys())}")
            if self.verbose:
                print(f"    🔍 Features: {list(active_features.keys())}")

        # Step 3: 提取交互元素
        elements = _extract_all_interactive(self.page)
        self.diag.append(f"[d={depth}] Elements: {len(elements)} interactives")
        if not elements:
            return

        # Step 4: LLM 规划探索动作
        if self.text_api_key:
            plan = _llm_plan_exploration(
                self.page, elements, features, self.already_clicked,
                self.text_api_key, self.text_model, self.text_base_url,
                max_actions=10, verbose=self.verbose,
                past_strategies=self._past_strategies,
            )
        else:
            plan = []

        # Step 5: LLM 不可用或返回空 → 启发式回退
        if not plan:
            self.diag.append(f"[d={depth}] LLM plan empty, using heuristic fallback")
            plan = _heuristic_plan(elements, self.already_clicked, max_actions=15)

        if not plan:
            self.diag.append(f"[d={depth}] No actions planned, leaf node")
            return

        # Step 6: 执行探索计划
        actions_taken = 0
        for action in plan:
            if self.interaction_count >= self.max_total_interactions:
                break
            if depth >= self.max_depth:
                break

            idx = action.get("index", -1)
            if idx < 0 or idx >= len(elements):
                continue

            el = elements[idx]
            el_text = el.get("text", "")[:40]
            action_text = f"{action.get('action', 'click')} #{idx} '{el_text}'"
            dedup_key = f"{el_text}|{el.get('id', '')}"

            # 跳过已点击的
            if dedup_key in self.already_clicked and dedup_key != "":
                continue
            if len(el_text) < 1:
                continue

            self.already_clicked.add(dedup_key)

            # 记录探索路径
            self.exploration_path.append({
                "depth": depth,
                "action": action,
                "element_text": el_text,
                "element_role": el["role"],
                "source": source,
            })

            if self.verbose:
                print(f"    [{self.interaction_count+1}/{self.max_total_interactions}] "
                      f"{action.get('reason', '?')[:60]}")

            # 执行点击
            old_fp = _page_fingerprint(self.page)
            old_url = self.page.url

            try:
                # 用 KaBOOM 风格定位: 文本优先
                if el.get("text") and len(el["text"]) > 1:
                    loc = self.page.locator(f"{el['tag']}:visible").filter(
                        has_text=el["text"][:30])
                elif el.get("id"):
                    loc = self.page.locator(f"#{el['id']}")
                else:
                    loc = self.page.locator(f"{el['tag']}:visible").nth(
                        max(0, idx // 4))  # 近似位置
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.evaluate("el => el.click()")
                else:
                    continue
            except Exception:
                continue

            self.interaction_count += 1
            actions_taken += 1
            time.sleep(2)

            # 检查是否产生了新状态
            new_fp = _page_fingerprint(self.page)
            new_url = self.page.url

            if new_fp != old_fp or new_url != old_url:
                self.diag.append(f"[d={depth}] Action #{idx} → NEW STATE "
                                f"(url={'changed' if new_url != old_url else 'same'}, "
                                f"fp={'changed' if new_fp != old_fp else 'same'})")

                # 递归探索新状态!
                self._explore(depth + 1, source=f"clicked #{idx} '{el_text}'")

                # 回退: 尝试回到之前的页面
                if new_url != old_url and not new_url.startswith(self.home_url):
                    # 跨页面导航 → 回到首页重新开始这条路径
                    self._go_home()
                elif new_url != old_url:
                    # 同站内页面 → 尝试回退
                    try:
                        self.page.go_back(timeout=5000)
                        time.sleep(2)
                    except Exception:
                        self._go_home()
                else:
                    # SPA 内状态变化 → 无法简单回退, 重新加载首页
                    self._go_home()
            else:
                self.diag.append(f"[d={depth}] Action #{idx} '{el_text}' → no state change")

        if actions_taken == 0:
            self.diag.append(f"[d={depth}] No actions taken on this page (all already explored)")

    # ── 自进化策略记忆 ──

    def _load_strategy_memory(self) -> str:
        """加载过去探索积累的策略记忆 (LLM自己写的).

        返回所有历史策略的合并文本, 供当前探索的 LLM 规划参考.
        如果文件不存在或为空, 返回空字符串.
        """
        try:
            if STRATEGY_MEMORY_PATH.exists():
                data = json.loads(STRATEGY_MEMORY_PATH.read_text(encoding="utf-8"))
                entries = data.get("entries", [])
                if entries:
                    summary = [f"## Past Exploration Strategies ({len(entries)} sessions)\n"]
                    for e in entries[-5:]:  # 最近5次
                        summary.append(f"### Session {e.get('timestamp', '?')[:19]}")
                        summary.append(f"Platform: {e.get('platform_url', '?')[:80]}")
                        summary.append(f"Strategies that worked:\n{e.get('strategies', '')}")
                        summary.append("")
                    result = "\n".join(summary)
                    self.diag.append(f"Loaded {len(entries)} past strategy entries ({len(result)} chars)")
                    return result
            return ""
        except Exception as e:
            self.diag.append(f"Failed to load strategy memory: {e}")
            return ""

    def _save_strategy_memory(self):
        """探索后让 LLM 自我反思, 写出新的策略记忆.

        LLM 阅读本次探索的完整路径, 提炼出平台无关的探索策略.
        这些策略会被保存, 下次探索自动加载.
        """
        if not self.text_api_key or self.interaction_count < 3:
            return

        import requests as req

        # 构建本次探索的摘要
        path_summary = json.dumps(self.exploration_path[-30:], ensure_ascii=False, indent=2)
        features_summary = json.dumps(
            [{"depth": f["depth"], "title": f["title"][:60],
              "features": list(f.get("features", {}).keys())}
             for f in self.discovered_features[-10:]],
            ensure_ascii=False, indent=2)

        prompt = f"""You just finished an autonomous exploration of a web platform. Reflect on what you learned and write general exploration strategies for future use.

IMPORTANT: Write platform-agnostic strategies. Do NOT mention specific URLs, button texts, or platform names. Write principles that would work on ANY web application.

Exploration summary:
- Total interactions: {self.interaction_count}
- States visited: {len(self.visited_fingerprints)}
- Steps discovered: {len(self.discovered_steps)}
- Features discovered: {len(self.discovered_features)}

Exploration path (what was clicked and what happened):
{path_summary[:3000]}

Features found at each depth:
{features_summary[:2000]}

TASK: Write 3-8 general exploration strategies based on this experience. For each strategy:
1. What pattern did you observe?
2. What general principle should be applied next time?
3. How should the exploration agent prioritize actions?

Focus on:
- How to escape multi-step wizards and reach deeper content
- How to distinguish navigation elements from interactive widgets
- How to detect hidden content (tabs, modals, accordions)
- How to avoid getting stuck in loops
- When to stop exploring a branch

Return ONLY a JSON object (no markdown, no explanation):
{{
  "timestamp": "{time.strftime('%Y-%m-%dT%H:%M:%SZ')}",
  "platform_url": "{self.home_url}",
  "strategies": "<your 3-8 strategies, one per line, in English, platform-agnostic>",
  "lessons_learned": "<1-3 sentences about what you learned this session>"
}}"""

        try:
            resp = req.post(
                f"{self.text_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.text_api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": self.text_model,
                    "messages": [
                        {"role": "system",
                         "content": "You are an AI that reflects on web exploration experiences and writes general strategies. Return ONLY valid JSON. No markdown, no explanation outside JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500,
                },
                timeout=30,
            )

            if resp.status_code != 200:
                return

            content = resp.json()["choices"][0]["message"]["content"]
            try:
                entry = json.loads(content)
            except json.JSONDecodeError:
                m = _re.search(r'\{[\s\S]*\}', content)
                if m:
                    entry = json.loads(m.group(0))
                else:
                    return

            # 加载现有记忆, 追加新条目
            memory = {"entries": []}
            if STRATEGY_MEMORY_PATH.exists():
                try:
                    memory = json.loads(STRATEGY_MEMORY_PATH.read_text(encoding="utf-8"))
                except Exception:
                    pass

            memory["entries"].append(entry)
            # 只保留最近20条
            memory["entries"] = memory["entries"][-20:]

            STRATEGY_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            STRATEGY_MEMORY_PATH.write_text(
                json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")

            self.diag.append(f"Strategy memory saved: {len(memory['entries'])} total entries")
            self.diag.append(f"New strategies: {entry.get('strategies', '')[:200]}")

        except Exception as e:
            self.diag.append(f"Failed to save strategy memory: {e}")
