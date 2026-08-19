"""
L2.5: 视觉语义理解层 (Visual Semantic Understanding)

借鉴: KaBOOM! (语义选择器 + Shadow DOM穿透)
      Explorbot Research (UI分块)
      多模态VLM (Doubao Seed 2.1 / GPT-4o / Qwen-VL)

职责:
  1. 对页面进行区块截图 → VLM识别语义区域
  2. 输出: 区域类型 (导航/内容/广告/AI面板/表单) + 文本内容
  3. Shadow DOM检测 + 穿透

支持的VLM Provider:
  - xjtlu_doubao: XJTLU Gateway Doubao Seed 2.1 (当前唯一可用VLM)
  - openai: GPT-4o (需独立配置 OPENAI_API_KEY 指向 openai.com)
  - anthropic: Claude Vision (需配置 ANTHROPIC_API_KEY)

用法:
  from .l2_vision import VisualAnalyzer
  va = VisualAnalyzer()  # 自动检测可用VLM
  regions = va.analyze_page(page)
"""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page


class VisualAnalyzer:
    """
    视觉语义分析器

    使用VLM对页面截图进行语义分块:
      - 导航区 (sidebar, topbar, breadcrumb)
      - 内容区 (article, lesson content, video player)
      - 交互区 (chat panel, quiz form, code editor)
      - 广告/无关区 (ads, footer, tracking pixels)

    Phase 1: 纯DOM启发式分析 (不依赖VLM API)
    Phase 2: 接入VLM (优先 Qwen3-VL-8B > Doubao) 进行视觉理解

    自动检测: 无需传参, 从环境变量自动读API Key
    XJTLU Gateway 使用标准 OpenAI-compatible 格式 ("model" 字段传 model_id)
    """

    def __init__(self, api_key: str = "", model: str = "",
                 base_url: str = "", provider: str = "",
                 verbose: bool = True):
        # 自动检测 (如果未显式提供)
        if not api_key or not base_url:
            from .api_keys import get_api_keys
            store = get_api_keys()
            vlm = store.get_vision_llm()
            if vlm:
                api_key = api_key or vlm.api_key
                base_url = base_url or vlm.base_url
                # XJTLU Gateway: model_id 就是 "model" 字段的值
                model = model or vlm.model_id or vlm.models[0]
                provider = provider or vlm.provider
                if verbose:
                    print(f"  🎯 自动检测VLM: {vlm.name} (model={model})")

        self.api_key = api_key
        self.model = model or "qwen3-vl-8b"
        self.base_url = base_url or "https://aiagent.xjtlu.edu.cn/api/aigw/v1"
        self.provider = provider
        self.verbose = verbose
        self._vlm_enabled = bool(api_key)

    def analyze_page(self, page: Page) -> dict:
        """
        分析单个页面 — 返回语义区域划分

        :returns: {
            "regions": [
                {"type": "navigation", "selector": "nav.sidebar", "text": "...", "confidence": 0.9},
                {"type": "content", "selector": "main", "text": "...", "confidence": 0.85},
                {"type": "ai_panel", "selector": "[class*='agent']", "text": "...", "confidence": 0.7},
            ],
            "framework": "react",
            "has_shadow_dom": false,
            "has_agent_panel": true,
        }
        """
        result = {
            "regions": [],
            "framework": "",
            "has_shadow_dom": False,
            "has_agent_panel": False,
        }

        # Step 1: DOM启发式分块 (不依赖VLM, Phase 1即可用)
        dom_regions = self._dom_heuristic_regions(page)
        result["regions"] = dom_regions

        # Step 2: Shadow DOM检测
        result["has_shadow_dom"] = self._detect_shadow_dom(page)

        # Step 3: AI面板检测
        result["has_agent_panel"] = any(
            r["type"] == "ai_panel" for r in dom_regions
        )

        # Step 4: VLM增强 (Phase 2, 仅当有API key)
        if self._vlm_enabled:
            vlm_regions = self._vlm_analyze(page, dom_regions)
            if vlm_regions:
                result["regions"] = self._merge_regions(
                    dom_regions, vlm_regions)

        if self.verbose:
            types = [r["type"] for r in result["regions"]]
            print(f"  👁️ 视觉分析: {len(result['regions'])} 区域 → {types}")
            if result["has_shadow_dom"]:
                print(f"     ⚠️ 检测到Shadow DOM")
            if result["has_agent_panel"]:
                print(f"     🤖 检测到AI对话面板")

        return result

    def _dom_heuristic_regions(self, page: Page) -> list[dict]:
        """
        DOM启发式区域划分 — 不依赖VLM

        基于CSS选择器和语义标签推断页面区域
        """
        regions = []
        viewport = page.viewport_size or {"width": 1280, "height": 800}

        # ── 区域检测规则 ──
        region_specs = [
            # (type, selectors, priority)
            ("navigation", [
                "nav", "[role='navigation']",
                "[class*='sidebar']", "[class*='Sidebar']",
                "[class*='navbar']", "[class*='Navbar']",
                "[class*='topbar']", "[class*='header']",
                "[class*='menu']:not([class*='context'])",
                "[class*='ant-menu']", "[class*='el-menu']",
                "header", "[role='banner']",
            ], 0.85),
            ("ai_panel", [
                "[class*='agent']", "[class*='Agent']",
                "[class*='chat']", "[class*='Chat']",
                "[class*='assistant']", "[class*='Assistant']",
                "[class*='conversation']", "[class*='dialog']",
                "[class*='ai-panel']", "[class*='help-panel']",
                "[class*='coach']", "[class*='tutor']",
            ], 0.80),
            ("content", [
                "main", "[role='main']",
                "article", "[role='article']",
                "[class*='content']", "[class*='Content']",
                "[class*='lesson']", "[class*='course']",
                "[class*='article']", "[class*='document']",
                "[class*='markdown']", "[class*='viewer']",
            ], 0.80),
            ("form", [
                "form", "[role='form']",
                "input[type='text']", "input[type='password']",
                "[class*='login']", "[class*='Login']",
                "[class*='quiz']", "[class*='Quiz']",
                "[class*='question']", "[class*='Question']",
            ], 0.75),
            ("media", [
                "video", "[class*='video']", "[class*='Video']",
                "[class*='player']", "[class*='Player']",
                "iframe[src*='youtube']", "iframe[src*='bilibili']",
                "iframe[src*='vimeo']",
            ], 0.90),
            ("code", [
                "[class*='monaco']", "[class*='CodeMirror']",
                "[class*='ace_editor']", "[class*='code-editor']",
                "[class*='ide']", "[class*='editor']",
            ], 0.90),
        ]

        for region_type, selectors, base_conf in region_specs:
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if el.count() == 0:
                        continue
                    if not el.is_visible():
                        continue

                    # 获取元素信息
                    text = ""
                    try:
                        text = el.inner_text().strip()[:500]
                    except Exception:
                        pass

                    # 获取位置/尺寸
                    box = None
                    try:
                        box = el.bounding_box()
                    except Exception:
                        pass

                    region = {
                        "type": region_type,
                        "selector": sel,
                        "text": text[:200],
                        "confidence": base_conf,
                    }
                    if box:
                        region["bbox"] = {
                            "x": int(box["x"]),
                            "y": int(box["y"]),
                            "w": int(box["width"]),
                            "h": int(box["height"]),
                        }
                    regions.append(region)
                    break  # 找到第一个匹配就跳出
                except Exception:
                    continue

        # ── 去重: 同一区域类型只保留置信度最高的 ──
        deduped = {}
        for r in regions:
            t = r["type"]
            if t not in deduped or r["confidence"] > deduped[t]["confidence"]:
                deduped[t] = r

        return sorted(deduped.values(),
                     key=lambda r: r.get("bbox", {}).get("y", 0))

    def _detect_shadow_dom(self, page: Page) -> bool:
        """检测页面是否包含Shadow DOM"""
        try:
            result = page.evaluate("""() => {
                function countShadowRoots(root) {
                    let count = 0;
                    const walker = document.createTreeWalker(
                        root, NodeFilter.SHOW_ELEMENT);
                    let node;
                    while (node = walker.nextNode()) {
                        if (node.shadowRoot) {
                            count++;
                            count += countShadowRoots(node.shadowRoot);
                        }
                    }
                    return count;
                }
                return countShadowRoots(document);
            }""")
            return result > 0
        except Exception:
            return False

    def _vlm_analyze(self, page: Page,
                     dom_regions: list[dict]) -> list[dict]:
        """
        VLM视觉分析 — 将页面截图发送给多模态模型

        Phase 2: 需要 OpenAI/GPT-4o API key
        """
        try:
            # 截取全页
            screenshot_bytes = page.screenshot(type="png", full_page=False)
            b64 = base64.b64encode(screenshot_bytes).decode("ascii")

            prompt = self._build_vlm_prompt(dom_regions)

            import requests as req

            # 构建请求体 — XJTLU Gateway 使用标准 OpenAI-compatible 格式
            # "model" 字段传 model_id (如 d95koqj7u3anoctav5sg)
            req_body = {
                "model": self.model,  # XJTLU Gateway: model_id 就是 model 的值
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "low",
                        }},
                    ],
                }],
                "max_tokens": 1000,
                "temperature": 0.1,
            }

            resp = req.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=req_body,
                timeout=45,  # 视觉模型较慢
            )

            if resp.status_code != 200:
                return []

            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # 尝试解析JSON
            import re
            m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if m:
                content = m.group(1)
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict) and "regions" in parsed:
                    return parsed["regions"]
            except json.JSONDecodeError:
                pass

            return []

        except Exception as e:
            if self.verbose:
                print(f"  ⚠️ VLM分析失败: {e}")
            return []

    def _build_vlm_prompt(self, dom_regions: list[dict]) -> str:
        """构建VLM Prompt"""
        dom_desc = "\n".join(
            f"  - {r['type']}: \"{r.get('text', '')[:80]}\""
            for r in dom_regions
        )
        return f"""Analyze this web page screenshot. The DOM-based analysis found these regions:
{dom_desc}

For each distinct visual region in the screenshot, provide:
1. type: "navigation" | "content" | "ai_panel" | "form" | "media" | "code" | "ad" | "footer"
2. description: short description of what this region contains
3. confidence: 0.0-1.0

Return ONLY a JSON array:
```json
[{{"type": "navigation", "description": "...", "confidence": 0.9}}]
```
Focus on finding AI chat panels, login forms, and main content areas."""

    def _merge_regions(self, dom_regions: list[dict],
                       vlm_regions: list[dict]) -> list[dict]:
        """
        合并DOM和VLM分析结果
        VLM结果置信度更高时覆盖DOM结果
        """
        # 简单策略: VLM结果优先
        merged = {r["type"]: r for r in dom_regions}
        for vr in vlm_regions:
            vr_type = vr.get("type", "unknown")
            # VLM结果: 转换description → text
            vr["text"] = vr.get("description", "")
            vr["selector"] = f"vlm:{vr_type}"
            vr["confidence"] = vr.get("confidence", 0.7)
            merged[vr_type] = vr
        return sorted(merged.values(),
                     key=lambda r: r.get("bbox", {}).get("y", 0))


# ═══════════════════════════════════════════════════════════════
# 便捷入口
# ═══════════════════════════════════════════════════════════════

def run_l2_vision(
    page: Page,
    api_key: str = "",
    model: str = "gpt-4o",
    base_url: str = "",
    verbose: bool = True,
) -> dict:
    """
    L2.5 视觉分析入口

    :param page: Playwright Page 对象
    :param api_key: VLM API key (Phase 2)
    :param model: VLM模型名
    :param base_url: API base URL
    :returns: 语义区域分析结果
    """
    analyzer = VisualAnalyzer(
        api_key=api_key,
        model=model,
        base_url=base_url,
        verbose=verbose,
    )
    return analyzer.analyze_page(page)
