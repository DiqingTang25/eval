"""
L1.8: LLM增强的 Step 提取

不靠点击导航 (太慢), 直接用 LLM 分析页面 DOM 文本 + VLM 看截图。
策略: text分析为主 (快), VLM截图为辅 (准), 两者互补。
"""

from __future__ import annotations

import base64
import json
import logging
import time
import re as _re
from typing import Optional

from playwright.sync_api import Page

from .models import StepInfo, StepType

logger = logging.getLogger(__name__)


def extract_steps_with_llm(
    page: Page,
    text_api_key: str = "",
    text_model: str = "deepseek-chat",
    text_base_url: str = "https://api.deepseek.com/v1",
    vlm_api_key: str = "",
    vlm_model: str = "",
    vlm_base_url: str = "",
    verbose: bool = True,
) -> list[dict]:
    """
    LLM分析当前页面DOM → 提取step结构

    1. 取页面文本 (3000字符)
    2. LLM直接从文本中解析step列表
    3. 如果失败, VLM看截图补充
    4. 返回 [{title, type_guess, order_index}, ...]
    """
    title = page.title()
    body_text = ""
    try:
        body_text = page.inner_text("body")[:3000]
    except Exception:
        pass

    # 收集可见的交互元素文本
    element_texts = []
    try:
        for el in page.locator("li, a, button, [class*=step], [class*=item], [class*=nav]").all()[:30]:
            try:
                t = el.inner_text().strip()
                if t and 2 < len(t) < 150:
                    element_texts.append(t[:120])
            except Exception:
                pass
    except Exception:
        pass

    # ── 策略1: LLM文本分析 ──
    if text_api_key and body_text:
        steps = _llm_extract_steps(
            title, body_text, element_texts,
            text_api_key, text_model, text_base_url, verbose)
        if steps:
            return steps

    # ── 策略2: VLM看截图 ──
    if vlm_api_key and vlm_model:
        steps = _vlm_extract_steps(
            page, title,
            vlm_api_key, vlm_model, vlm_base_url, verbose)
        if steps:
            return steps

    # ── 策略3: 纯DOM匹配 (不上LLM) ──
    return _dom_extract_steps(body_text, element_texts)


def _llm_extract_steps(title, body_text, elements, key, model, url, verbose) -> list[dict]:
    """LLM从文本提取steps"""
    import requests as req

    prompt = f"""Extract the TEACHING STEP structure from this page and classify each step's type.

Page title: {title}

Page text content:
{body_text[:2500]}

Interactive elements:
{json.dumps(elements[:15], ensure_ascii=False)}

TASK: Find teaching STEPS on this page and classify each one.

A step is a numbered/sequential learning unit (e.g. "Step 1: Introduction", "1. Variables", "Task 1: Setup").

STEP TYPE CLASSIFICATION — look for evidence in the page text and element names:

  video — evidence: play button, "watch", "video", "播放", duration timestamps, transcript mentions, "Video" labels
  quiz  — evidence: "question", "quiz", "test", "multiple choice", "true/false", radio buttons, "submit answer", score/points, "correct/incorrect"
  coding — evidence: "code", "editor", "console", "terminal", "python"/"javascript", "run", "compile", "IDE", syntax highlighting, "output"
  reading — evidence: article/document text blocks, "read", "reading", paragraphs with headings, markdown, PDF mentions, long-form text
  chat — evidence: "chat", "assistant", "AI", "ask", "message", "conversation", dialog/messaging UI pattern, input+send button combo
  upload — evidence: "upload", "file", "submit", "attachment", file picker, drag-and-drop zone, "choose file", "photo"
  unknown — ONLY use this if NO evidence exists for any of the above types

IMPORTANT: Prefer a specific type over "unknown". Look at element names, labels, surrounding text, and page structure for evidence. If you see a "play" icon or "video" label near a step, it's likely video. If you see questions with answer choices, it's quiz.

Return ONLY a JSON array:
[
  {{"title": "Step title", "type_guess": "video|quiz|coding|reading|chat|upload|unknown", "order_index": 1, "evidence": "brief reason for type choice"}},
  ...
]

If no steps are visible, return empty array []."""

    try:
        resp = req.post(
            f"{url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You extract teaching step structures from web page text. Return ONLY valid JSON array. No markdown, no explanation."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 1500,
            },
            timeout=20,
        )
        if resp.status_code != 200:
            logger.warning("LLM text analysis HTTP %d", resp.status_code)
            return []

        content = resp.json()["choices"][0]["message"]["content"]
        try:
            result = json.loads(content)
            if isinstance(result, list):
                if result:
                    logger.info("LLM text analysis: %d steps", len(result))
                return result
        except json.JSONDecodeError:
            m = _re.search(r'\[[\s\S]*\]', content)
            if m:
                try:
                    result = json.loads(m.group(0))
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass
        logger.info("LLM text analysis: 0 steps found")
        return []
    except Exception as e:
        logger.warning("LLM text analysis failed: %s", e)
        return []


def _vlm_extract_steps(page, title, key, model, url, verbose) -> list[dict]:
    """VLM看截图提取steps"""
    import requests as req

    try:
        screenshot = page.screenshot(type="png", full_page=False)
        b64 = base64.b64encode(screenshot).decode("ascii")

        resp = req.post(
            f"{url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"""This is a teaching platform page titled "{title}".
Look at the screenshot. Is there a STEP LIST visible?
Steps are numbered items in a sidebar, top navigation bar, or main content area.
If you see steps, list each with title and type_guess.

Step types and visual evidence:
  video — play button icon, thumbnail, duration, progress bar
  quiz  — multiple choice, radio buttons, score, correct/incorrect
  coding — code editor, terminal, syntax highlighting, run button
  reading — long text blocks, article layout, headings, paragraphs
  chat — messaging UI, input+send, conversation bubbles
  upload — file picker, drag-drop zone, "choose file" button
  unknown — only if NO visual evidence exists

Return ONLY a JSON array:
[{{"title": "Step title", "type_guess": "video", "order_index": 1}}]
If no steps visible, return []."""},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "low",
                        }},
                    ],
                }],
                "max_tokens": 1500,
                "temperature": 0.1,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            return []

        content = resp.json()["choices"][0]["message"]["content"]
        try:
            result = json.loads(content)
            if isinstance(result, list):
                if verbose and result:
                    print(f"  [VLM] 截图分析提取 {len(result)} steps")
                return result
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
            print(f"  [VLM] 截图分析失败: {e}")
        return []


def _dom_extract_steps(body_text: str, elements: list[str]) -> list[dict]:
    """纯DOM正则匹配提取steps (fallback)"""
    steps = []
    seen = set()

    # 模式: "Step N: Title", "步骤N：Title", "N. Title", "(N) Title"
    patterns = [
        r'(?:Step|步骤|Task|任务|Activity|活动)\s*(\d+)[：:.\s]+(.+?)(?=(?:Step|步骤|Task|任务|Activity|活动)\s*\d+|$)',
        r'^(\d+)[.)]\s+(.+?)$',
        r'\((\d+)\)\s+(.+?)(?=\s*\(\d+\)|$)',
    ]

    for pat in patterns:
        for m in _re.finditer(pat, body_text, _re.IGNORECASE | _re.MULTILINE):
            if len(m.groups()) >= 2:
                order = int(m.group(1)) if m.group(1).isdigit() else len(steps) + 1
                title = m.group(2).strip()[:120]
            else:
                order = len(steps) + 1
                title = m.group(0).strip()[:120]

            if title and title not in seen and len(title) > 2:
                seen.add(title)
                steps.append({
                    "title": title,
                    "type_guess": "unknown",
                    "order_index": order,
                })

    return steps


# ═══════════════════════════════════════════════════════════════
# 第二层导航: 通用平台无关的前向导航 (借鉴 Explorbot + KaBOOM)
# ═══════════════════════════════════════════════════════════════
#
# 设计原则 (零硬编码文本):
#   1. Explorbot Research: 先索引所有交互元素, 再理解页面结构
#   2. KaBOOM 语义优先级: role > accessible-name > text > CSS (最后手段)
#   3. LLM 作为理解层: 将页面结构发给 LLM, 让它识别"前向导航"元素
#      → 这是真正的语言无关方案, LLM 理解所有语言
#   4. 启发式评分回退: 当 LLM 不可用时, 用框架通用的 CSS class 模式 + 视觉显著性
#
# 核心洞察: 不猜测按钮文字, 而是让 LLM 理解页面语义后告诉我们哪个元素是"下一层入口"

def _extract_page_structure(page: Page, max_elements: int = 40) -> dict:
    """提取页面结构摘要 — 借鉴 Explorbot Research 阶段.

    索引所有交互元素, 附带 KaBOOM 风格的语义属性
    (role, accessible name, text, position, size).
    不依赖任何语言/平台的硬编码文本.

    :returns: {title, url, body_text, landmarks, elements: [{index, role, tag,
                text, aria_label, classes, x, y, w, h}]}
    """
    structure = {
        "title": page.title(),
        "url": page.url,
        "body_text": "",
        "landmarks": [],
        "elements": [],
    }

    # ── 页面文本 (前2000字符) ──
    try:
        structure["body_text"] = page.inner_text("body")[:2000]
    except Exception:
        pass

    # ── ARIA landmarks (语义地标) ──
    try:
        for role in ["main", "navigation", "banner", "contentinfo", "complementary"]:
            try:
                els = page.locator(f"[role='{role}']").all()
                if els:
                    structure["landmarks"].append(role)
            except Exception:
                pass
    except Exception:
        pass

    # ── 索引所有交互元素 (KaBOOM 风格: role + accessible name 优先) ──
    element_index = 0
    seen_texts: set[str] = set()

    # 常见交互选择器 — 只匹配可见元素
    for locator_str in [
        "button:visible", "a:visible", "[role='button']:visible",
        "[role='link']:visible", "[role='menuitem']:visible",
        "[role='tab']:visible", "input[type='submit']:visible",
        "input[type='button']:visible",
    ]:
        if element_index >= max_elements:
            break
        try:
            for el in page.locator(locator_str).all():
                if element_index >= max_elements:
                    break
                try:
                    if not el.is_visible():
                        continue

                    # ── KaBOOM 优先级: text → 去重 ──
                    text = ""
                    try:
                        text = el.inner_text().strip()[:80]
                    except Exception:
                        pass
                    if text and text in seen_texts:
                        continue  # 去重: 同一个元素可能匹配多个选择器
                    if text:
                        seen_texts.add(text)

                    # ── 语义属性 ──
                    tag = el.evaluate("el => el.tagName.toLowerCase()") if hasattr(el, 'evaluate') else ""
                    aria_label = el.get_attribute("aria-label") or ""
                    role_attr = el.get_attribute("role") or ""
                    classes = el.get_attribute("class") or ""
                    el_id = el.get_attribute("id") or ""

                    # ── 推断 role ──
                    if role_attr:
                        inferred_role = role_attr
                    elif tag == "button" or "button" in locator_str:
                        inferred_role = "button"
                    elif tag == "a":
                        inferred_role = "link"
                    elif tag == "input":
                        inferred_role = "button"
                    else:
                        inferred_role = tag or "unknown"

                    # ── 位置与大小 (视觉显著性) ──
                    box = None
                    try:
                        box = el.bounding_box()
                    except Exception:
                        pass

                    # ── 是否在 main/导航/页脚区域内 ──
                    in_nav = False
                    in_footer = False
                    try:
                        parent_nav = el.evaluate("""el => {
                            let p = el.parentElement;
                            for (let i = 0; i < 8 && p; i++) {
                                const tag = p.tagName ? p.tagName.toLowerCase() : '';
                                const role = p.getAttribute('role') || '';
                                const cls = (p.className || '').toLowerCase();
                                if (tag === 'nav' || role === 'navigation' ||
                                    cls.includes('nav') || cls.includes('menu') ||
                                    cls.includes('sidebar') || cls.includes('header')) {
                                    return true;
                                }
                                p = p.parentElement;
                            }
                            return false;
                        }""")
                        in_nav = bool(parent_nav)
                    except Exception:
                        pass

                    try:
                        parent_footer = el.evaluate("""el => {
                            let p = el.parentElement;
                            for (let i = 0; i < 8 && p; i++) {
                                const tag = p.tagName ? p.tagName.toLowerCase() : '';
                                const cls = (p.className || '').toLowerCase();
                                if (tag === 'footer' || cls.includes('footer')) {
                                    return true;
                                }
                                p = p.parentElement;
                            }
                            return false;
                        }""")
                        in_footer = bool(parent_footer)
                    except Exception:
                        pass

                    structure["elements"].append({
                        "index": element_index,
                        "role": inferred_role,
                        "tag": tag,
                        "text": text,
                        "aria_label": aria_label,
                        "classes": classes[:120],
                        "id": el_id[:60],
                        "x": round(box["x"]) if box else 0,
                        "y": round(box["y"]) if box else 0,
                        "w": round(box["width"]) if box else 0,
                        "h": round(box["height"]) if box else 0,
                        "in_nav": in_nav,
                        "in_footer": in_footer,
                    })
                    element_index += 1
                except Exception:
                    continue
        except Exception:
            continue

    return structure


def _llm_identify_forward_element(
    structure: dict,
    text_api_key: str,
    text_model: str,
    text_base_url: str,
    verbose: bool = True,
) -> int | None:
    """LLM 识别「前向导航」元素 — 语言无关, LLM 理解任何语言的页面.

    借鉴 Explorbot: 将页面结构摘要发给廉价/快速模型,
    让它分析语义后告诉我们哪个元素是"进入下一层内容"的入口.

    :returns: element index, or None if not identified
    """
    import requests as req

    elements_json = json.dumps(structure["elements"], ensure_ascii=False, indent=2)

    prompt = f"""You are analyzing a web page. A user navigated here by clicking a card/item on a previous page. This page is a detail/overview/summary page.

Your task: Identify which interactive element would take the user FORWARD to the actual content — the "next level" in the content hierarchy (e.g., entering a course, starting a lesson, opening the main material).

Page title: {structure["title"]}
URL: {structure["url"]}
ARIA landmarks: {json.dumps(structure["landmarks"])}

Page text (first 2000 chars):
{structure["body_text"][:2000]}

All interactive elements (indexed):
{elements_json[:4000]}

How to identify the FORWARD navigation element:
1. It is typically a BUTTON (not a nav link) — visually prominent, often with distinct styling
2. It appears AFTER descriptive/summary text about the item
3. It is in the MAIN content area, NOT in navigation/header/sidebar/footer
4. It is often visually larger than surrounding elements
5. Semantically, its purpose is: starting, entering, beginning, opening, going to actual content
6. IGNORE: "back", "home", "menu", "search", "profile", "settings", "logout", "login", "register" elements

Return ONLY a valid JSON object (no markdown, no explanation):
{{"index": <int>, "confidence": <float 0-1>, "reasoning": "<one brief sentence>"}}

If no clear forward navigation element exists, return: {{"index": -1, "confidence": 0, "reasoning": "no forward element found"}}"""

    try:
        resp = req.post(
            f"{text_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {text_api_key}",
                     "Content-Type": "application/json"},
            json={
                "model": text_model,
                "messages": [
                    {"role": "system",
                     "content": "You are a web page structure analyzer. You identify navigation elements based on page semantics. Return ONLY valid JSON. No markdown, no explanation."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 300,
            },
            timeout=20,
        )

        if resp.status_code != 200:
            if verbose:
                print(f"  [StepEx:LLM] HTTP {resp.status_code}")
            return None

        content = resp.json()["choices"][0]["message"]["content"]
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            m = _re.search(r'\{[^}]+\}', content)
            if m:
                result = json.loads(m.group(0))
            else:
                return None

        idx = result.get("index", -1)
        if isinstance(idx, int) and 0 <= idx < len(structure["elements"]):
            el = structure["elements"][idx]
            if verbose:
                print(f"  [StepEx:LLM] 识别到前向导航: "
                      f"#{idx} '{el['text'][:50]}' "
                      f"(confidence={result.get('confidence', 0):.0%}, "
                      f"reason={result.get('reasoning', '?')[:50]})")
            return idx
        elif verbose:
            print(f"  [StepEx:LLM] LLM未找到前向导航元素 "
                  f"(index={idx}, reason={result.get('reasoning', '?')[:50]})")
        return None

    except Exception as e:
        if verbose:
            print(f"  [StepEx:LLM] LLM识别失败: {e}")
        return None


def _heuristic_score_elements(elements: list[dict]) -> list[tuple[int, float]]:
    """启发式评分 — 不依赖任何语言/平台特定文本.

    借鉴 KaBOOM: 语义属性优先 (role), CSS class 只是辅助信号.
    所用 CSS class 模式均为全球框架通用 (Bootstrap/Ant Design/Material UI/...).

    评分维度:
      - CSS class 含 primary/cta/accent/success/main → +0.25 (框架通用)
      - role=button (非 link) → +0.15 (按钮比链接更可能是CTA)
      - 元素尺寸大 → +0.20 (视觉显著性)
      - 不在 nav/footer 内 → +0.20 (内容区内)
      - 不是明显的导航/功能文本 → +0.10
    """
    scored: list[tuple[int, float]] = []

    # ── 框架通用的 CSS class 模式 (全球统一使用英文) ──
    # 这些 class 名称在任何国家/语言的网站上都会出现,
    # 因为 CSS 框架 (Bootstrap, Ant Design, Element UI, Material UI,
    # Tailwind) 全球使用英文 class 名.
    UNIVERSAL_CTA_CLASSES = [
        "primary", "btn-primary", "cta", "accent",
        "success", "action", "main", "hero",
        "highlight", "featured", "important",
    ]

    # ── 功能性的非前向导航文本模式 (通用, 任何语言都可能出现) ──
    # 这些是功能按钮/链接, 几乎不可能是"进入下一层内容"的入口
    FUNCTIONAL_CLASS_PATTERNS = [
        "nav", "menu", "sidebar", "header", "footer",
        "search", "profile", "setting", "logout", "login",
        "back", "close", "dismiss", "cancel", "delete",
        "edit", "save", "share", "print", "download",
    ]

    for el in elements:
        score = 0.0
        classes = el.get("classes", "").lower()
        text = el.get("text", "").lower()
        role = el.get("role", "")
        tag = el.get("tag", "")
        w = el.get("w", 0)
        h = el.get("h", 0)
        in_nav = el.get("in_nav", False)
        in_footer = el.get("in_footer", False)

        # ── CSS class 信号 (+0.25) ──
        for pat in UNIVERSAL_CTA_CLASSES:
            if pat in classes:
                score += 0.25
                break

        # ── Role 信号 (+0.15) — button > link ──
        if role == "button" or tag == "button":
            score += 0.15

        # ── 视觉显著性 (+0.20) — 较大元素更可能是 CTA ──
        size = w * h
        if size > 15000:   # > ~120x120
            score += 0.20
        elif size > 6000:  # > ~80x80
            score += 0.12
        elif size > 2000:  # > ~50x40
            score += 0.06

        # ── 位置信号 (+0.20) — 不在导航/页脚 ──
        if not in_nav and not in_footer:
            score += 0.20
        elif not in_nav:
            score += 0.08

        # ── 减分: 在导航区域 ──
        if in_nav:
            score -= 0.25
        if in_footer:
            score -= 0.40

        # ── 减分: CSS class 包含功能性模式 ──
        for pat in FUNCTIONAL_CLASS_PATTERNS:
            if pat in classes:
                score -= 0.15
                break

        # ── 减分: 极小元素 (可能是图标按钮) ──
        if w < 30 or h < 20:
            score -= 0.10

        # ── 文字长度合理 (2-60字符) ──
        text_len = len(text)
        if 2 <= text_len <= 60:
            score += 0.05

        scored.append((el["index"], max(0.0, min(1.0, score))))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _click_and_verify_navigation(page: Page, old_url: str, old_title: str,
                                 verbose: bool = True) -> bool:
    """点击后验证是否发生了有意义的导航.

    检查 URL 变化 / 标题变化 / DOM 大幅变化.
    """
    time.sleep(2.5)
    new_url = page.url
    new_title = page.title()

    # URL 变化 (remove hash-only changes)
    old_url_base = old_url.split("#")[0]
    new_url_base = new_url.split("#")[0]
    url_changed = old_url_base != new_url_base

    # 标题变化
    title_changed = old_title != new_title

    # 页面文本长度变化 (DOM 内容大幅变化)
    text_changed = False
    try:
        old_len = len(page.inner_text("body"))
        time.sleep(0.3)
        new_len = len(page.inner_text("body"))
        text_changed = abs(new_len - old_len) > 200
    except Exception:
        pass

    navigated = url_changed or title_changed or text_changed

    if verbose and navigated:
        reason = []
        if url_changed:
            reason.append(f"URL → {new_url[:80]}")
        if title_changed:
            reason.append(f"title → '{new_title[:50]}'")
        if text_changed and not url_changed and not title_changed:
            reason.append("DOM内容变化")
        print(f"  [StepEx:Nav] ✅ 导航成功 ({', '.join(reason)})")

    return navigated


def _navigate_to_next_level(
    page: Page,
    text_api_key: str = "",
    text_model: str = "",
    text_base_url: str = "",
    verbose: bool = True,
    diag: list | None = None,
) -> bool:
    """平台无关的前向导航: 从 detail/overview 页 → 实际内容页."""
    if diag is None:
        diag = []
    old_url = page.url
    old_title = page.title()

    # ── Phase 1: 提取页面结构 (Explorbot Research) ──
    structure = _extract_page_structure(page)
    elements = structure["elements"]

    diag.append(f"Nav Phase1: {len(elements)} elements, landmarks={structure['landmarks']}")
    if elements:
        # Show top elements by score for diagnostics
        scored_preview = _heuristic_score_elements(elements)
        top3 = [(idx, s) for idx, s in scored_preview[:3]]
        for idx, s in top3:
            el = elements[idx]
            diag.append(f"  Nav top[{idx}]: text='{el['text'][:60]}' role={el['role']} "
                       f"size={el['w']}x{el['h']} nav={el['in_nav']} score={s:.2f}")

    if verbose:
        print(f"  [StepEx:Nav] 页面结构: {len(elements)} 个交互元素, "
              f"landmarks={structure['landmarks']}")

    if not elements:
        diag.append(f"Nav: 0 interactive elements on page")
        if verbose:
            print(f"  [StepEx:Nav] ⚠️ 页面无交互元素")
        return False

    # ── Phase 2: LLM 语义识别 (优先) ──
    if text_api_key and text_model and text_base_url:
        llm_index = _llm_identify_forward_element(
            structure, text_api_key, text_model, text_base_url, verbose)
        diag.append(f"Nav Phase2 LLM: identified index={llm_index}")
        if llm_index is not None:
            el = elements[llm_index]
            diag.append(f"  LLM pick: text='{el['text'][:60]}' role={el['role']}")
            if verbose:
                print(f"  [StepEx:Nav] 尝试 LLM 识别的元素 "
                      f"#{llm_index}: '{el['text'][:50]}'")
            try:
                target = page.locator("button:visible, a:visible, "
                                      "[role='button']:visible").nth(llm_index)
                if target.is_visible():
                    target.evaluate("el => el.click()")
                    if _click_and_verify_navigation(page, old_url, old_title, verbose):
                        diag.append(f"Nav Phase2 LLM: SUCCESS")
                        return True
                    else:
                        diag.append(f"Nav Phase2 LLM: click didn't navigate")
            except Exception as e:
                diag.append(f"Nav Phase2 LLM: click exception: {e}")
    else:
        diag.append(f"Nav Phase2 LLM: skipped (no API key)")

    # ── Phase 3: 启发式评分回退 ──
    scored = _heuristic_score_elements(elements)
    top_candidates = [(idx, score) for idx, score in scored[:8] if score > 0.15]
    diag.append(f"Nav Phase3 heuristics: {len(top_candidates)} candidates above 0.15")

    if verbose:
        print(f"  [StepEx:Nav] 启发式评分: {len(top_candidates)} 个候选 "
              f"(top: #{top_candidates[0][0]} score={top_candidates[0][1]:.2f})"
              if top_candidates else f"  [StepEx:Nav] 启发式评分: 无高分候选")

    for idx, score in top_candidates:
        el = elements[idx]
        try:
            if el.get("text") and len(el["text"]) > 1:
                locator = page.locator(f"{el['tag']}:visible").filter(
                    has_text=el["text"][:30])
            else:
                locator = page.locator(f"{el['tag']}:visible").nth(
                    sum(1 for e in elements[:idx] if e["tag"] == el["tag"]))

            if locator.count() > 0 and locator.first.is_visible():
                if verbose:
                    print(f"  [StepEx:Nav] 尝试候选 #{idx}: "
                          f"'{el['text'][:50]}' (score={score:.2f})")
                locator.first.evaluate("el => el.click()")
                if _click_and_verify_navigation(page, old_url, old_title, verbose):
                    diag.append(f"Nav Phase3: SUCCESS candidate #{idx} '{el['text'][:50]}' score={score:.2f}")
                    return True
        except Exception:
            continue

    # ── Phase 4: 遍历所有 buttons (最后回退) ──
    diag.append(f"Nav Phase4 brute force: trying all visible buttons")
    try:
        buttons = page.locator("button:visible").all()
        for i, btn in enumerate(buttons[:6]):
            try:
                text = btn.inner_text().strip()[:50]
                if not text:
                    continue
                skip_classes = ["nav", "menu", "back", "close", "search",
                                "profile", "setting", "logout"]
                cls = (btn.get_attribute("class") or "").lower()
                if any(s in cls for s in skip_classes):
                    continue

                if verbose:
                    print(f"  [StepEx:Nav] 遍历回退 [{i}]: '{text}'")
                btn.evaluate("el => el.click()")
                if _click_and_verify_navigation(page, old_url, old_title, verbose):
                    diag.append(f"Nav Phase4: SUCCESS button[{i}] '{text}'")
                    return True
            except Exception:
                continue
    except Exception:
        pass

    diag.append(f"Nav: ALL phases failed, no forward navigation found")
    if verbose:
        print(f"  [StepEx:Nav] ⚠️ 未找到前向导航元素 "
              f"(当前页: {old_title[:50]})")
    return False


def _snap(page: Page) -> dict:
    """Capture current page state for diagnostics."""
    try:
        body = page.inner_text("body")[:500]
        buttons = page.locator("button:visible").count()
        links = page.locator("a:visible").count()
        return {
            "title": page.title(),
            "url": page.url,
            "body_preview": body[:300].replace("\n", " "),
            "buttons": buttons,
            "links": links,
        }
    except Exception:
        return {"title": "?", "url": "?", "body_preview": "", "buttons": 0, "links": 0}


def extract_steps_deep(
    page: Page,
    base_url: str,
    text_api_key: str = "",
    text_model: str = "deepseek-chat",
    text_base_url: str = "https://api.deepseek.com/v1",
    vlm_api_key: str = "",
    vlm_model: str = "",
    vlm_base_url: str = "",
    max_careers: int = 5,
    verbose: bool = True,
    diag: list | None = None,
) -> list[dict]:
    """两层导航提取教学 steps — 平台无关, 零硬编码文本.

    第一层: 首页 → 点击卡片 (通用选择器)
    第二层: detail页 → LLM/启发式识别前向导航 → 实际内容页 → LLM提取steps

    借鉴:
      - Explorbot Research: 索引页面结构, LLM 理解语义
      - KaBOOM: role + accessible-name 优先于 CSS
      - A2A论文: LLM 辅助推断隐藏入口

    :param diag: 如果传入 list, 会向其中追加全链路诊断信息
    """
    if diag is None:
        diag = []
    all_steps: list[dict] = []
    home_url = base_url.rstrip("/")

    # ── 回到首页 ──
    diag.append(f"--- StepExtractor: start ---")
    diag.append(f"base_url: {home_url}")
    if verbose:
        print(f"\n  [StepEx:Deep] 回到首页: {home_url}")
    try:
        page.goto(home_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(3)
    except Exception as e:
        diag.append(f"goto home failed: {e}")
        if verbose:
            print(f"  [StepEx:Deep] ⚠️ 回首页失败: {e}")
        try:
            page.reload(wait_until="domcontentloaded", timeout=15000)
            time.sleep(3)
        except Exception:
            pass

    snap_home = _snap(page)
    diag.append(f"HOME: title={snap_home['title'][:80]}, buttons={snap_home['buttons']}, links={snap_home['links']}")
    diag.append(f"HOME body: {snap_home['body_preview'][:200]}")

    # ── 第一层: 用通用选择器找卡片 ──
    card_selectors = [
        "[class*='card']:visible",
        "[class*='tile']:visible",
        "[class*='item']:visible",
    ]

    cards_clicked = 0
    clicked_texts: set[str] = set()
    total_cards_found = 0

    for sel in card_selectors:
        if cards_clicked >= max_careers:
            break
        try:
            all_cards = page.locator(sel).all()
            cards = []
            for c in all_cards:
                try:
                    if not c.is_visible():
                        continue
                    box = c.bounding_box()
                    if not box:
                        continue
                    if not (80 < box["width"] < 700 and 40 < box["height"] < 500):
                        continue
                    text = c.inner_text().strip()
                    if len(text) < 3 or len(text) > 200:
                        continue
                    cards.append(c)
                except Exception:
                    continue

            total_cards_found += len(cards)
            diag.append(f"Selector '{sel}': {len(all_cards)} raw → {len(cards)} valid cards")
            if verbose and cards:
                print(f"  [StepEx:Deep] '{sel}': {len(cards)} 个有效卡片 "
                      f"(过滤自 {len(all_cards)} 个)")
        except Exception:
            continue

        for card in cards:
            if cards_clicked >= max_careers:
                break
            try:
                card_text = card.inner_text().strip()[:60]
                if not card_text or card_text in clicked_texts:
                    continue
                clicked_texts.add(card_text)

                diag.append(f"--- Card [{cards_clicked+1}/{max_careers}]: '{card_text}' ---")
                if verbose:
                    print(f"\n  [StepEx:Deep] [{cards_clicked+1}/{max_careers}] "
                          f"点击卡片: '{card_text}'")

                # ── 第一层: 点击卡片 ──
                old_url = page.url
                old_title = page.title()
                card.evaluate("el => el.click()")
                time.sleep(3)

                snap_l1 = _snap(page)
                card_navigated = (page.url != old_url or page.title() != old_title)
                diag.append(f"L1 after click: title={snap_l1['title'][:80]}")
                diag.append(f"L1 URL: {snap_l1['url'][:120]}")
                diag.append(f"L1 buttons={snap_l1['buttons']}, links={snap_l1['links']}")
                diag.append(f"L1 navigated={card_navigated}")
                diag.append(f"L1 body: {snap_l1['body_preview'][:200]}")

                if card_navigated:
                    if verbose:
                        print(f"  [StepEx:Deep] → 进入: {page.title()[:60]}")
                else:
                    # SPA toggle: card click just selected/deselected, no navigation.
                    # Don't skip — try to find a forward navigation button on this page.
                    diag.append(f"L1: card is SPA toggle (no navigation), looking for forward button on page")
                    if verbose:
                        print(f"  [StepEx:Deep] SPA toggle, 寻找前向导航...")

                # ── 第二层: 平台无关的前向导航 → 实际内容页 ──
                # Always try: if the card already navigated, this goes deeper.
                # If the card only toggled, this finds the "next step" button.
                nav_result = _navigate_to_next_level(
                    page,
                    text_api_key=text_api_key,
                    text_model=text_model,
                    text_base_url=text_base_url,
                    verbose=verbose,
                    diag=diag,
                )
                diag.append(f"L2 navigate result: {'SUCCESS' if nav_result else 'FAILED'}")

                if nav_result:
                    time.sleep(2)

                    snap_l2 = _snap(page)
                    content_title = snap_l2["title"]
                    diag.append(f"L2 content page: title={content_title[:80]}")
                    diag.append(f"L2 URL: {snap_l2['url'][:120]}")
                    diag.append(f"L2 buttons={snap_l2['buttons']}, links={snap_l2['links']}")
                    diag.append(f"L2 body: {snap_l2['body_preview'][:300]}")
                    if verbose:
                        print(f"  [StepEx:Deep] → 内容页: {content_title[:60]}")

                    # ── LLM 提取 steps ──
                    steps = extract_steps_with_llm(
                        page=page,
                        text_api_key=text_api_key,
                        text_model=text_model,
                        text_base_url=text_base_url,
                        vlm_api_key=vlm_api_key,
                        vlm_model=vlm_model,
                        vlm_base_url=vlm_base_url,
                        verbose=verbose,
                    )

                    diag.append(f"LLM extract result: {len(steps)} steps")
                    if steps:
                        for i, s in enumerate(steps[:10]):
                            diag.append(f"  step[{i}]: title='{s.get('title','')[:80]}' type={s.get('type_guess','?')}")
                        for s in steps:
                            s["source_card"] = card_text
                            s["source_page"] = content_title
                        all_steps.extend(steps)
                        if verbose:
                            print(f"  [StepEx:Deep] ✅ 提取 {len(steps)} steps")
                    else:
                        diag.append(f"LLM: 0 steps returned (page body preview: {snap_l2['body_preview'][:200]})")
                        if verbose:
                            print(f"  [StepEx:Deep] ⚠️ 内容页无steps")
                else:
                    diag.append(f"L2: forward navigation FAILED, trying current page instead")
                    if verbose:
                        print(f"  [StepEx:Deep] ⚠️ 前向导航失败, 在当前页尝试")
                    steps = extract_steps_with_llm(
                        page=page,
                        text_api_key=text_api_key,
                        text_model=text_model,
                        text_base_url=text_base_url,
                        vlm_api_key=vlm_api_key,
                        vlm_model=vlm_model,
                        vlm_base_url=vlm_base_url,
                        verbose=verbose,
                    )
                    diag.append(f"LLM extract (L1 fallback): {len(steps)} steps")
                    if steps:
                        for s in steps:
                            s["source_card"] = card_text
                        all_steps.extend(steps)

                cards_clicked += 1

                # ── 回到首页 ──
                try:
                    page.goto(home_url, wait_until="domcontentloaded", timeout=10000)
                    time.sleep(2)
                except Exception:
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=10000)
                        time.sleep(2)
                    except Exception:
                        pass

            except Exception as e:
                import traceback
                diag.append(f"Card exception: {e}")
                diag.append(traceback.format_exc()[:300])
                if verbose:
                    print(f"  [StepEx:Deep] ❌ 卡片处理失败: {e}")
                try:
                    page.goto(home_url, wait_until="domcontentloaded", timeout=10000)
                    time.sleep(2)
                except Exception:
                    pass
                continue

    diag.append(f"--- StepExtractor: DONE ---")
    diag.append(f"Total: {len(all_steps)} steps from {cards_clicked} cards (found {total_cards_found} total valid cards)")
    if verbose:
        print(f"\n  [StepEx:Deep] 完成: {len(all_steps)} steps "
              f"from {cards_clicked} cards")

    return all_steps
