"""
L1.7: 交互式 Step 发现层

核心问题: React SPA 中 step 数据在 DOM 中渲染, 不经过 API 调用。
解决: 导航进入每个 course → 从 DOM/React state 提取 step 列表。

策略:
  1. 从 graph-source 获取 course→lessonId 映射
  2. 在页面上点击 course card → 导航到 lesson 页面
  3. page.evaluate() 提取 DOM 中的 step 列表
  4. 也尝试 React fiber 提取更丰富的数据
"""

from __future__ import annotations

import json
import time
import re as _re
from typing import Optional

from playwright.sync_api import Page

from .models import StepInfo, StepType


def discover_steps(
    page: Page,
    base_url: str,
    graph_source_data: dict,
    max_courses: int = 10,
    verbose: bool = True,
) -> dict[str, list[StepInfo]]:
    """
    交互式发现: 点击进入每个 course → 从 DOM 提取 step 列表

    :param page: Playwright Page (已登录)
    :param base_url: 平台URL
    :param graph_source_data: graph-source API 的 response_sample
    :param max_courses: 最多探索的 course 数量
    :returns: {lesson_id: [StepInfo, ...], ...}
    """
    courses = graph_source_data.get("courses", [])
    if not courses:
        if verbose:
            print("  [step discovery] No courses in graph-source data")
        return {}

    # 限制数量避免超时
    courses = courses[:max_courses]

    if verbose:
        print(f"\n{'='*60}")
        print(f"L1.7: 交互式 Step 发现 — {len(courses)} courses")
        print(f"{'='*60}")

    all_steps: dict[str, list[StepInfo]] = {}

    # ── 先在当前页面找 course cards ──
    for i, course in enumerate(courses):
        course_id = course.get("id", "")
        course_title = course.get("title", "")
        lesson_id = str(course.get("lessonId", ""))

        if verbose:
            print(f"\n  [{i+1}/{len(courses)}] {course_title[:50]} (id={course_id})")

        try:
            steps = _enter_course_and_scrape_steps(
                page, base_url, course_id, course_title, verbose=verbose)
            if steps:
                all_steps[lesson_id or course_id] = steps
                if verbose:
                    for s in steps:
                        print(f"    Step: {s.title[:60]} [{s.type.value}]")
            else:
                if verbose:
                    print(f"    ⚠ 未发现 steps")
        except Exception as e:
            if verbose:
                print(f"    ❌ 失败: {str(e)[:100]}")

        # 回到首页
        try:
            page.goto(base_url, wait_until="domcontentloaded", timeout=10000)
            time.sleep(1.5)
        except Exception:
            pass

    if verbose:
        total = sum(len(v) for v in all_steps.values())
        print(f"\n  ✅ Step发现完成: {total} steps in {len(all_steps)} courses")

    return all_steps


def _enter_course_and_scrape_steps(
    page: Page,
    base_url: str,
    course_id: str,
    course_title: str,
    verbose: bool = True,
) -> list[StepInfo]:
    """进入单个 course → 抓取 step 列表"""

    # ── 策略1: 点击 course card ──
    card_selectors = [
        f"[class*='career-card']", f"[class*='course-card']",
        f"[class*='module-card']", f"[class*='phase-card']",
        f"button.ci-shell-career-card",
        f"[class*='ant-card']", f"[class*='card']",
        f"a[class*='course']", f"a[class*='lesson']",
    ]

    clicked = False
    for sel in card_selectors:
        try:
            cards = page.locator(sel).all()
            for card in cards:
                if not card.is_visible():
                    continue
                text = card.inner_text().strip()[:80]
                # 匹配: card 文本包含 course title
                if course_title[:30] not in text and course_id[:15] not in text:
                    continue

                old_url = page.url
                card.evaluate("el => el.click()")
                time.sleep(2.5)

                new_url = page.url
                if new_url != old_url:
                    if verbose:
                        print(f"    🖱️ 点击 → {new_url[:80]}")
                    clicked = True
                    break

                # 即使URL没变也等 — SPA可能只是内容变了
                time.sleep(1)
                new_title = page.title()
                if new_title != course_title and len(new_title) > 1:
                    clicked = True
                    break
            if clicked:
                break
        except Exception:
            continue

    if not clicked:
        # ── 策略2: 直接URL导航 ──
        url_patterns = [
            f"{base_url}/courses/{course_id}",
            f"{base_url}/course/{course_id}",
            f"{base_url}/lessons/{course_id}",
            f"{base_url}/phase/{course_id}",
            f"{base_url}?course={course_id}",
        ]
        for url in url_patterns:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=8000)
                time.sleep(2)
                if page.url != base_url:
                    if verbose:
                        print(f"    🌐 导航 → {page.url[:80]}")
                    clicked = True
                    break
            except Exception:
                continue

    if not clicked:
        return []

    # ── 等React渲染 ──
    time.sleep(2)

    # ── 从DOM提取steps ──
    return _scrape_steps_from_dom(page, course_id, verbose=verbose)


def _scrape_steps_from_dom(
    page: Page,
    course_id: str,
    verbose: bool = True,
) -> list[StepInfo]:
    """从当前页面DOM抓取step列表 (多种策略)"""

    steps_data = page.evaluate("""() => {
        const results = [];

        // ── 策略1: 找step列表容器 ──
        const stepSelectors = [
            '[class*="step-list"]', '[class*="steps-list"]',
            '[class*="step-container"]', '[class*="stepper"]',
            '[class*="progress-steps"]', '[class*="timeline"]',
            '[role="list"][class*="step"]', '[class*="ant-steps"]',
            'nav[class*="step"]', 'ul[class*="step"]',
            '[class*="lesson-nav"]', '[class*="course-nav"]',
            // 侧边栏可能是step导航
            '[class*="sidebar"] [class*="menu"]',
            '[class*="sidebar"] ul li',
        ];

        for (const sel of stepSelectors) {
            try {
                const containers = document.querySelectorAll(sel);
                for (const container of containers) {
                    // 找step项: li, div with title, button
                    const items = container.querySelectorAll(
                        'li, [class*="step-item"], [class*="step"], ' +
                        'a[class*="item"], div[class*="item"], button[class*="item"]'
                    );

                    if (items.length >= 2) {
                        for (const item of items) {
                            const text = (item.textContent || '').trim();
                            if (text.length > 2 && text.length < 200) {
                                results.push({
                                    title: text.substring(0, 120),
                                    selector: sel.substring(0, 60),
                                    method: 'step_list_container'
                                });
                            }
                        }
                        if (results.length > 0) return results;
                    }
                }
            } catch(e) {}
        }

        // ── 策略2: 找编号列表 (1. xxx, Step 1: xxx, etc.) ──
        const bodyText = document.body.innerText || '';
        const patterns = [
            /(?:Step|步骤|Task|任务|Activity|活动)\\s*\\d+[：:.]?\\s*(.+)/gi,
            /^\\d+[.)]\\s+(.+)/gm,
            /\\(\\d+\\)\\s+(.+)/g,
        ];

        for (const pat of patterns) {
            let match;
            while ((match = pat.exec(bodyText)) !== null) {
                const title = (match[1] || match[0]).trim();
                if (title.length > 2 && title.length < 150) {
                    results.push({
                        title: title.substring(0, 120),
                        selector: 'text_pattern',
                        method: 'numbered_list'
                    });
                }
            }
            if (results.length >= 3) return results;
        }

        // ── 策略3: 找带有step进度指示器的区域 ──
        const progressEls = document.querySelectorAll(
            '[class*="progress"], [class*="Progress"], ' +
            '[class*="stepper"], [class*="Stepper"]'
        );
        for (const el of progressEls) {
            const text = (el.textContent || '').trim();
            // 找 "Step X of Y" 或 "X/Y" 模式
            const progressMatch = text.match(
                /(?:Step|步骤)?\\s*(\\d+)\\s*(?:of|\\/)\\s*(\\d+)/
            );
            if (progressMatch) {
                const totalSteps = parseInt(progressMatch[2]);
                if (totalSteps >= 2 && totalSteps <= 50) {
                    // 生成了totalSteps个占位step
                    const prefix = text.split(/\\d+/)[0].trim() || 'Step';
                    for (let i = 1; i <= totalSteps; i++) {
                        results.push({
                            title: prefix + ' ' + i,
                            selector: 'progress_indicator',
                            method: 'progress_counter'
                        });
                    }
                    return results;
                }
            }
        }

        // ── 策略4: React fiber 提取 ──
        try {
            const rootKey = Object.keys(document).find(k =>
                k.startsWith('__reactFiber$') ||
                k.startsWith('__reactInternalInstance$')
            );
            if (rootKey) {
                // 遍历fiber树找文本节点
                const texts = [];
                function walkFiber(fiber, depth) {
                    if (!fiber || depth > 30 || texts.length > 50) return;
                    // 找memoizedProps中的step数据
                    if (fiber.memoizedProps) {
                        const p = fiber.memoizedProps;
                        if (p.steps && Array.isArray(p.steps)) {
                            for (const s of p.steps) {
                                texts.push({
                                    title: (s.title || s.name || s.label || '').substring(0, 120),
                                    selector: 'react_fiber',
                                    method: 'react_steps_prop'
                                });
                            }
                            if (texts.length > 0) return;
                        }
                        if (p.items && Array.isArray(p.items)) {
                            for (const item of p.items) {
                                const t = item.title || item.name || item.label || '';
                                if (t) texts.push({
                                    title: t.substring(0, 120),
                                    selector: 'react_fiber',
                                    method: 'react_items_prop'
                                });
                            }
                        }
                        // 常见的教学平台step组件props
                        for (const key of ['steps', 'lessons', 'modules', 'chapters', 'tasks']) {
                            if (p[key] && Array.isArray(p[key])) {
                                for (const item of p[key]) {
                                    if (typeof item === 'string') {
                                        texts.push({title: item, selector: 'react_fiber', method: 'react_' + key});
                                    } else if (item && typeof item === 'object') {
                                        const t = item.title || item.name || item.label || item.id || '';
                                        if (t) texts.push({title: String(t).substring(0, 120), selector: 'react_fiber', method: 'react_' + key});
                                    }
                                }
                            }
                        }
                    }
                    if (fiber.child) walkFiber(fiber.child, depth + 1);
                    if (fiber.sibling) walkFiber(fiber.sibling, depth + 1);
                }
                const rootFiber = document[rootKey];
                walkFiber(rootFiber, 0);
                if (texts.length > 0) {
                    // 去重
                    const seen = new Set();
                    const unique = texts.filter(t => {
                        const key = t.title.substring(0, 30);
                        if (seen.has(key)) return false;
                        seen.add(key);
                        return true;
                    });
                    return unique;
                }
            }
        } catch(e) {}

        return results;
    }""")

    steps = []
    for i, s in enumerate(steps_data):
        title = s.get("title", "").strip()
        if not title or len(title) < 2:
            continue

        # 推断step类型
        step_type = StepType.UNKNOWN
        title_lower = title.lower()
        if any(kw in title_lower for kw in ["video", "视频", "watch", "播放"]):
            step_type = StepType.VIDEO
        elif any(kw in title_lower for kw in ["quiz", "测试", "题目", "question"]):
            step_type = StepType.QUIZ
        elif any(kw in title_lower for kw in ["code", "编程", "代码", "editor"]):
            step_type = StepType.CODING
        elif any(kw in title_lower for kw in ["read", "阅读", "文档", "article"]):
            step_type = StepType.READING

        steps.append(StepInfo(
            id=f"step_{course_id}_{i:03d}",
            title=title[:120],
            type=step_type,
            type_confidence=0.6 if step_type != StepType.UNKNOWN else 0.4,
            order_index=i,
        ))

    return steps


def inject_steps_into_structure(
    teaching_structure,
    all_steps: dict[str, list[StepInfo]],
    verbose: bool = True,
):
    """将交互发现的steps注入到TeachingStructure中"""
    if not all_steps:
        return teaching_structure

    # 展平所有steps
    flat_steps = []
    for lesson_id, steps in all_steps.items():
        for s in steps:
            s.lesson_id = lesson_id
            flat_steps.append(s)

    if flat_steps:
        teaching_structure.steps = flat_steps
        # 更新lessons的step_count
        for lesson in teaching_structure.lessons:
            if lesson.id in all_steps:
                lesson.step_count = len(all_steps[lesson.id])

        if verbose:
            print(f"  ✅ 注入 {len(flat_steps)} steps 到结构")

    return teaching_structure
