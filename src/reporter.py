"""
评测报告生成器 v3.4

输出 JSON + Markdown 双格式报告，含9维度评分 + 边界检测统计 +
文字解释 + 自动改进方案 (v3.4 集成 ImprovementEngine)
"""

import json
import os
from datetime import datetime


# ── 维度解释模板 ──

DIM_EXPLANATIONS = {
    "correctness": {
        "name": "事实正确性",
        "levels": {
            (4.5, 5.0): "回答完全准确，无事实性错误，严格基于课程内容",
            (3.5, 4.5): "回答基本准确，存在极少量不影响理解的微小偏差",
            (2.5, 3.5): "回答部分准确，有1-2处事实性错误或模糊表述",
            (1.5, 2.5): "回答存在多处明显错误，影响信息的可信度",
            (0, 1.5): "回答严重失实，存在幻觉或完全错误的信息",
        },
    },
    "relevancy": {
        "name": "答案相关性",
        "levels": {
            (4.5, 5.0): "回答完全切题，精准回应用户问题的每个要点",
            (3.5, 4.5): "回答整体切题，少量内容略微偏离主题",
            (2.5, 3.5): "回答部分切题，存在较明显的偏离或泛泛而谈",
            (1.5, 2.5): "回答多次偏离主题，核心问题未得到回应",
            (0, 1.5): "答非所问，与用户问题几乎无关",
        },
    },
    "completeness": {
        "name": "内容完整性",
        "levels": {
            (4.5, 5.0): "全面覆盖所有关键知识点，无重要遗漏",
            (3.5, 4.5): "覆盖大部分关键知识点，少量次要内容未涉及",
            (2.5, 3.5): "覆盖约一半关键知识点，存在明显的信息缺口",
            (1.5, 2.5): "仅覆盖少数知识点，内容严重不完整",
            (0, 1.5): "几乎未覆盖任何关键知识点",
        },
    },
    "guidance": {
        "name": "教学引导力",
        "levels": {
            (4.5, 5.0): "卓越引导 — Socratic教学法，分层递进，诊断性提问+支架式引导",
            (3.5, 4.5): "良好引导 — 结构清晰有递进，引导意识强但策略不够灵活",
            (2.5, 3.5): "一般引导 — 有基本结构但跳跃，偏向灌输式",
            (1.5, 2.5): "引导混乱 — 逻辑不清，信息堆砌，缺乏教学意识",
            (0, 1.5): "无教学引导 — 直接给答案/代码，无解释无提问",
        },
    },
    "followup_quality": {
        "name": "追问响应质量",
        "levels": {
            (4.5, 5.0): "追问后高质量回答，上下文连贯，深度回应新问题",
            (3.5, 4.5): "追问后回答良好，基本衔接上下文",
            (2.5, 3.5): "追问后质量下降，出现重复或未能深入回应",
            (1.5, 2.5): "追问后内容重复或答非所问，未能理解追问意图",
            (0, 1.5): "追问后完全混乱，无法形成有效对话",
        },
    },
    "boundary_compliance": {
        "name": "边界合规性",
        "levels": {
            (4.5, 5.0): "回答完全基于课程知识，可追溯到具体课程内容",
            (3.5, 4.5): "主要基于课程知识，有少量合理的通用知识补充",
            (2.5, 3.5): "部分课程知识混合较明显的通用大模型内容",
            (1.5, 2.5): "大部分为通用大模型知识，课程内容占比较低",
            (0, 1.5): "完全脱离课程大纲，属于通用大模型能力输出",
        },
    },
    "turn_consistency": {
        "name": "跨轮一致性",
        "levels": {
            (4.5, 5.0): "多轮间信息完全一致，前后呼应，知识体系连贯",
            (3.5, 4.5): "基本一致，个别细节前后略有出入但不影响理解",
            (2.5, 3.5): "存在矛盾或跳跃，需要用户自行补全缺失信息",
            (1.5, 2.5): "多次出现前后矛盾，Agent出现失忆现象",
            (0, 1.5): "完全不一致，每轮独立回答无关联",
        },
    },
    "knowledge_scaffolding": {
        "name": "知识递进性",
        "levels": {
            (4.5, 5.0): "每轮在上一轮基础上递进深化，形成完整学习阶梯",
            (3.5, 4.5): "有递进但不明显，部分回答较为独立",
            (2.5, 3.5): "回答独立缺乏递进，未利用之前的对话积累",
            (1.5, 2.5): "出现退步或重复，知识层次不升反降",
            (0, 1.5): "完全无递进，每轮都是重新开始",
        },
    },
    # ── v3.4 新增 ──
    "overhelping": {
        "name": "过度帮助",
        "levels": {
            (4.5, 5.0): "完全无过度帮助 — 始终引导先行，提示→引导→确认→示例",
            (3.5, 4.5): "基本无过度帮助 — 引导为主，偶尔提示偏多但不直接暴露答案",
            (2.5, 3.5): "轻度过度帮助 — 部分回答直接给出关键信息而非引导",
            (1.5, 2.5): "明显过度帮助 — 多次直接给出答案/代码，引导缺失",
            (0, 1.5): "严重过度帮助 — 所有回答直接给答案，无任何引导尝试",
        },
    },
}


def explain_score(dimension: str, score: float) -> str:
    """根据维度和分数生成文字解释"""
    dim_info = DIM_EXPLANATIONS.get(dimension)
    if not dim_info:
        return ""
    for (lo, hi), text in dim_info["levels"].items():
        if lo <= score <= hi:
            return f"{dim_info['name']} {score:.1f}分 — {text}"
    return ""


class Reporter:
    """评测报告生成器 v3.4 — 含自动改进方案生成"""

    def __init__(self, api_key=None):
        self.api_key = api_key
        self._last_report = None
        self._improvement_engine = None  # 延迟初始化

    @property
    def improvement_engine(self):
        """延迟加载改进引擎"""
        if self._improvement_engine is None and self.api_key:
            try:
                from src.improvement_engine import ImprovementEngine
                self._improvement_engine = ImprovementEngine(api_key=self.api_key)
            except Exception as e:
                print(f"  ⚠️ 改进引擎加载失败: {e}")
        return self._improvement_engine

    def get_last_report(self) -> dict:
        """获取最后一次生成的报告数据"""
        return self._last_report or {}

    def generate_report(
        self, results, boundary_summary: dict = None,
        improvement_plan=None, rule_evidence: list[str] = None,
        extra: dict = None, config_snapshot: dict = None,
    ):
        """
        生成完整评测报告（含文字解释 + v3.4改进方案 + v3.5证据链）

        :param results: 评测结果列表
        :param boundary_summary: 边界检测汇总
        :param improvement_plan: ImprovementPlan 对象 (v3.4)
        :param rule_evidence: L1规则层证据 (v3.4)
        :param extra: 附加数据 (final_total/importance_weights/fairness_detail/personas), 供HTML多模态呈现
        :param config_snapshot: 评测配置快照 (v3.5: 用于证据链)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("reports", exist_ok=True)

        total = len(results)
        success = sum(1 for r in results if r.get("score") is not None)
        timeout = sum(
            1 for r in results
            if (turns := r.get("conversation_turns") or [])
            and turns[-1].get("response", {}).get("status") == "timeout"
        )
        error = total - success

        scores = [r["score"] for r in results if r.get("score")]
        dims = [
            "correctness", "relevancy", "completeness",
            "guidance", "followup_quality", "boundary_compliance",
            "turn_consistency", "knowledge_scaffolding", "overhelping",
            "fairness_bias", "overall",
        ]
        avg = {
            k: round(sum(s.get(k, 0) for s in scores) / len(scores), 2)
            if scores else 0
            for k in dims
        }

        # ── 生成维度解释 ──
        explanations = {}
        for dim in dims:
            if dim == "overall":
                continue
            val = avg.get(dim, 0)
            explanations[dim] = explain_score(dim, val)

        summary = {
            "total": total, "success": success,
            "timeout": timeout, "error": error,
            "avg_scores": avg,
            "explanations": explanations,
        }
        if boundary_summary:
            summary["boundary"] = boundary_summary

        # ── 每个场景也加解释 ──
        detailed_results = []
        for r in results:
            sc = r.get("score", {})
            sc_explanations = {}
            if sc:
                for dim in dims:
                    if dim == "overall":
                        continue
                    val = sc.get(dim, 0)
                    if val > 0:
                        sc_explanations[dim] = explain_score(dim, val)
            detailed_results.append({
                **r,
                "score_explanations": sc_explanations,
            })

        # ── 构建报告 (先不含 evidence, 用于计算自校验哈希) ──
        report = {
            "timestamp": timestamp,
            "summary": summary,
            "details": detailed_results,
            "extra": extra or {},
        }

        # ── v3.5: 计算自校验哈希 (在添加 evidence 之前) ──
        # 自校验哈希证明评测内容的完整性, 与证据链(证明原始文件完整性)互补
        try:
            from src.evidence_builder import EvidenceBuilder
            eb = EvidenceBuilder()
            self_hash = eb.compute_report_self_hash(report)

            # 构建证据链并嵌入 self_hash
            evidence_manifest = eb.build(results, config_snapshot, extra)
            evidence_manifest["report_self_hash"] = self_hash

            # 注入 evidence 到 report (仅顶层, 不污染 extra)
            report["evidence"] = evidence_manifest

            print(f"  🔐 报告自校验哈希: {self_hash[:16]}...")
        except Exception as e:
            print(f"  ⚠️ 证据链构建失败(不影响报告): {e}")

        self._last_report = report

        # ── JSON ──
        json_file = f"reports/report_{timestamp}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # ── Markdown ──
        md_file = f"reports/report_{timestamp}.md"
        dim_labels = {
            "correctness": "事实正确性",
            "relevancy": "答案相关性",
            "completeness": "内容完整性",
            "guidance": "教学引导力",
            "followup_quality": "追问响应质量",
            "boundary_compliance": "边界合规性",
            "turn_consistency": "跨轮一致性",
            "knowledge_scaffolding": "知识递进性",
            "overhelping": "过度帮助",
        }
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# 🤖 AI Agent 评测报告\n\n")
            f.write(f"**生成时间**: {timestamp}\n\n")

            f.write(f"## 📊 总览\n\n")
            f.write(f"| 指标 | 值 |\n")
            f.write(f"|------|----|\n")
            f.write(f"| 测试场景数 | {total} |\n")
            f.write(f"| 成功 | {success} |\n")
            f.write(f"| 超时 | {timeout} |\n")
            f.write(f"| 错误 | {error} |\n")
            f.write(f"| **综合得分** | **{avg.get('overall', 0):.2f} / 5.00** |\n\n")

            f.write("## 📈 6维度评分\n\n")
            f.write("| 维度 | 得分 | 解释 |\n")
            f.write("|------|------|------|\n")
            for k, v in avg.items():
                if k == "overall":
                    continue
                label = dim_labels.get(k, k)
                exp = explanations.get(k, "")
                f.write(f"| {label} ({k}) | **{v:.2f}** / 5.00 | {exp} |\n")

            if boundary_summary:
                f.write(f"\n## 🛡️ 边界检测\n\n")
                f.write(f"| 状态 | 数量 | 占比 |\n")
                f.write(f"|------|------|------|\n")
                f.write(f"| 在范围内 | {boundary_summary['in_scope']} | {boundary_summary['in_scope_pct']:.0%} |\n")
                f.write(f"| 部分匹配 | {boundary_summary['partial_match']} | {boundary_summary['partial_pct']:.0%} |\n")
                f.write(f"| 超出范围 | {boundary_summary['out_of_scope']} | {boundary_summary['out_of_scope_pct']:.0%} |\n")
                f.write(f"\n> 💡 **边界合规性说明**: 该指标衡量Agent回答是否基于课程知识体系，而非通用大模型能力。\n")
                f.write(f"> 分数越高说明Agent越能\"知道该知道什么\"，严格在课程边界内回答。\n")

            f.write(f"\n## 📋 场景详情\n\n")
            for i, r in enumerate(detailed_results):
                qd = r.get("question_data", {})
                sc = r.get("score", {})
                bd = r.get("boundary", {})
                sc_exp = r.get("score_explanations", {})

                f.write(f"### 场景 {i+1}: {qd.get('question', 'N/A')[:80]}...\n\n")
                f.write(f"- **阶段**: {qd.get('phase', 'N/A')} | **类型**: {qd.get('type', 'N/A')}\n")
                f.write(f"- **QA ID**: {qd.get('qa_id', 'N/A')}\n\n")

                if sc:
                    f.write(f"#### 评分明细\n\n")
                    f.write(f"| 维度 | 得分 | 解释 |\n")
                    f.write(f"|------|------|------|\n")
                    for dim in dims:
                        if dim == "overall":
                            continue
                        val = sc.get(dim, 0)
                        if val > 0:
                            label = dim_labels.get(dim, dim)
                            exp_text = sc_exp.get(dim, explain_score(dim, val))
                            f.write(f"| {label} | **{val}** / 5.00 | {exp_text} |\n")
                    f.write(f"| **综合** | **{sc.get('overall', 0)}** / 5.00 | |\n\n")

                if bd:
                    f.write(f"#### 边界检测\n\n")
                    f.write(f"- **状态**: {bd.get('status', 'N/A')}\n")
                    f.write(f"- **关键词命中率**: {bd.get('max_score', 0):.1%}\n")
                    f.write(f"- **命中关键词**: {', '.join(bd.get('matched_keywords', [])[:8])}\n")
                    f.write(f"- **证据**: {bd.get('evidence', '')[:300]}\n")
                    f.write(f"- **建议**: {bd.get('recommendation', '')}\n\n")

                # 对话记录
                turns = r.get("conversation_turns", [])
                if turns:
                    f.write(f"#### 对话记录\n\n")
                    for turn in turns:
                        resp = turn.get("response", {})
                        f.write(f"**第{turn['turn']}轮** ({resp.get('status', '?')}, {resp.get('duration', 0):.1f}s)\n\n")
                        f.write(f"> 用户: {turn['question']}\n\n")
                        f.write(f"> 助手: {resp.get('response', '')[:300]}\n\n")

                f.write("---\n\n")

            # ── v3.5: 证据链 & 置信度 (Markdown) ──
            evidence = report.get("evidence", {})
            if evidence:
                f.write(f"## 🔐 证据链 · 报告完整性证明\n\n")
                self_hash = evidence.get("report_self_hash", "")
                if self_hash:
                    f.write(f"- **报告自校验哈希**: `{self_hash}`\n")
                    f.write(f"- **验证方法**: 下载 TOS 原始文件 → 重算 SHA-256 → 比对哈希值\n")
                chain = evidence.get("scenario_chain", [])
                if chain:
                    f.write(f"\n### 场景哈希链\n\n")
                    f.write(f"| 场景 | 哈希 | 画像 | 总分 |\n")
                    f.write(f"|------|------|------|------|\n")
                    for node in chain:
                        f.write(f"| {node.get('index','')} | `{node.get('hash','')}` | {node.get('persona_id','')} | {node.get('overall',0):.2f} |\n")
                    chain_root = evidence.get("chain_root", "")
                    if chain_root:
                        f.write(f"\n**链根哈希**: `{chain_root[:32]}...`\n")

                # 置信度
                conf = evidence.get("confidence", {})
                dims_conf = conf.get("dimensions", {})
                if dims_conf:
                    f.write(f"\n## 📊 置信度 & 可靠性分析\n\n")
                    f.write(f"| 维度 | 均值 | CV | 95%CI | 可靠性 |\n")
                    f.write(f"|------|------|-----|-------|--------|\n")
                    for dim_key, info in dims_conf.items():
                        if dim_key == "overall":
                            continue
                        cv = info.get("cv")
                        cv_str = f"{cv*100:.1f}%" if cv is not None and cv != float("inf") else "N/A"
                        ci = info.get("ci_95")
                        ci_str = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "—"
                        f.write(f"| {info.get('label', dim_key)} | {info.get('mean', '—')} | {cv_str} | {ci_str} | {info.get('reliability', '—')} |\n")
                    overall_rel = conf.get("overall_reliability", "")
                    if overall_rel:
                        f.write(f"\n**整体可靠性**: {overall_rel}\n")

                # Judge 共识
                jc = evidence.get("judge_consensus", {})
                if jc:
                    f.write(f"\n## ⚖️ 多 Judge 共识分析\n\n")
                    f.write(f"- **平均 Judge 数**: {jc.get('avg_judges_per_scenario', 0):.1f} 人/场景\n")
                    f.write(f"- **平均方差**: {jc.get('avg_variance', 0):.3f}\n")
                    f.write(f"- **共识评级**: {jc.get('consensus_level', '—')}\n")
                    f.write(f"- **否决场景**: {jc.get('veto_scenarios', 0)} | **跳过LLM**: {jc.get('skip_scenarios', 0)}\n")

            # 总结
            f.write(f"## 💡 综合评价\n\n")
            overall = avg.get("overall", 0)
            if overall >= 4.0:
                verdict = "优秀"
                suggestion = "Agent表现良好，可继续关注追问质量和边界合规性的持续优化。"
            elif overall >= 3.0:
                verdict = "良好"
                suggestion = "Agent基本能满足教学需求，建议重点关注完整性和引导力的提升。"
            elif overall >= 2.0:
                verdict = "需改进"
                suggestion = "Agent存在较明显的能力短板，建议针对性优化低分维度。"
            else:
                verdict = "不合格"
                suggestion = "Agent当前表现不足以支持教学场景，需要进行系统性改进。"

            f.write(f"**综合评定**: {verdict}（{overall:.1f}/5.0）\n\n")
            f.write(f"{suggestion}\n\n")

            # 短板分析
            weak_dims = [(dim_labels.get(k, k), v) for k, v in avg.items()
                         if k != "overall" and v < 3.0]
            if weak_dims:
                f.write("### ⚠️ 主要短板\n\n")
                for name, val in weak_dims:
                    f.write(f"- **{name}** ({val:.1f}/5.0): 建议优先改进\n")

            strong_dims = [(dim_labels.get(k, k), v) for k, v in avg.items()
                           if k != "overall" and v >= 4.0]
            if strong_dims:
                f.write("### ✅ 优势维度\n\n")
                for name, val in strong_dims:
                    f.write(f"- **{name}** ({val:.1f}/5.0): 表现优秀\n")

            # ── v3.4: 改进方案 ──
            if improvement_plan and improvement_plan.actions:
                f.write(f"\n## 🔧 自动生成改进方案\n\n")
                f.write(f"> 以下方案由改进引擎根据评分结果自动生成，共 {len(improvement_plan.actions)} 条措施。\n")
                f.write(f"> 生成时间: {improvement_plan.generated_at} | 模型: {improvement_plan.model_used}\n\n")

                if improvement_plan.urgent_actions:
                    f.write(f"### 🔴 紧急改进 ({len(improvement_plan.urgent_actions)}条)\n\n")
                    for i, action in enumerate(improvement_plan.urgent_actions):
                        f.write(f"**{i+1}. {action.title}**\n\n")
                        f.write(f"- 类别: `{action.category}` | 工作量: {action.effort} | 风险: {action.risk}\n")
                        f.write(f"- 问题: {action.description[:200]}\n")
                        f.write(f"- 方案: {action.implementation[:300]}...\n")
                        f.write(f"- 预期: {action.expected_effect[:150]}\n\n")

                if improvement_plan.important_actions:
                    f.write(f"### 🟡 重点改进 ({len(improvement_plan.important_actions)}条)\n\n")
                    for i, action in enumerate(improvement_plan.important_actions):
                        f.write(f"**{i+1}. {action.title}**\n\n")
                        f.write(f"- 类别: `{action.category}` | 工作量: {action.effort}\n")
                        f.write(f"- 预期: {action.expected_effect[:150]}\n\n")

                if improvement_plan.optimize_actions:
                    f.write(f"### 🟢 优化建议 ({len(improvement_plan.optimize_actions)}条)\n\n")
                    for i, action in enumerate(improvement_plan.optimize_actions[:3]):
                        f.write(f"- **{action.title}** — {action.expected_effect[:100]}\n")

            # ── v3.4: 过度帮助专项报告 ──
            if avg.get("overhelping", 5.0) < 3.5:
                f.write(f"\n## ⚠️ 过度帮助警告\n\n")
                f.write(f"过度帮助得分: **{avg['overhelping']:.1f}/5.0**\n\n")
                f.write(f"Agent可能存在以下问题:\n")
                f.write(f"- 直接给出完整答案/代码而非引导学生思考\n")
                f.write(f"- Agent输出远超学生输入（独角戏模式）\n")
                f.write(f"- 回答中缺乏引导性提问\n\n")
                f.write(f"> 💡 建议: 在System Prompt中加入Socratic教学法指令，禁止第一轮直接给出代码。\n")

        self._last_report["markdown_path"] = md_file

        # ── HTML (v3.5 显性化报告, 含证据链) ──
        try:
            from src.html_reporter import HTMLReporter
            # 使用含有 self_hash 的更新版 report
            html = HTMLReporter.render_agent_eval(report)
            html_file = f"reports/report_{timestamp}.html"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(html)
            self._last_report["html_path"] = html_file
            print(f"  📄 HTML: {html_file}")
        except Exception as e:
            print(f"  ⚠️ HTML生成失败: {e}")

        return json_file
