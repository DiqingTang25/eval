"""
全自动化测评流水线编排器

支持: 多 Agent (Platform HiAgent API / WebTest Playwright) / 边界检测 / 多维度评分 / 对抗性测试
支持: 进度回调 (progress_callback) 用于 Dashboard 实时展示
P0-15: Watchdog 超时保护 + 取消检查点 + 单场景超时
"""

import concurrent.futures
import os
import time
import yaml
from src.evaluator import Evaluator
from src.question_generator import QuestionGenerator
from src.followup_generator import FollowupGenerator
from src.reporter import Reporter
from src.boundary_detector import BoundaryDetector
from src.agents.base import AgentStatus
from src.agents.agent_registry import AgentRegistry


class TestRunner:
    """全自动化测评流水线 — P0-15: 带 Watchdog 保护"""

    def __init__(self, config_path="config/test_config.yaml", progress_callback=None,
                 watchdog=None):
        """
        :param config_path: 配置文件路径
        :param progress_callback: 进度回调函数 callback(event_type, data)
        :param watchdog: P0-15: Watchdog 实例,用于超时保护和取消检查
        """
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)["test"]
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.progress = progress_callback

        # P0-15: Watchdog 引用
        self.watchdog = watchdog

        # 初始化模块
        self.q_gen = QuestionGenerator(self.api_key)
        self.evaluator = Evaluator(self.api_key, config=self.config)
        self.followup_gen = FollowupGenerator(self.api_key)
        self.reporter = Reporter(api_key=self.api_key)
        self.boundary_detector = (
            BoundaryDetector(self.api_key)
            if self.config.get("use_boundary", True) else None
        )

        self.agent_id = self.config.get("agent_id", "hiagent")

    def _emit(self, event: str, data: dict = None):
        """发送进度事件"""
        if self.progress:
            self.progress(event, data or {})

    def _check_cancelled(self):
        """P0-15: 检查是否被取消 — 在关键检查点调用"""
        if self.watchdog:
            self.watchdog.check_cancelled()

    def _load_golden_questions(self, count: int) -> list[dict]:
        """从黄金QA库加载问题 — 分层多样性抽样 (v3.2)

        优先保证阶段/题型/难度三维覆盖，不足时随机补充。
        """
        import json

        bank_path = "data/golden_qa_bank.json"
        if not os.path.exists(bank_path):
            print("  ℹ️  黄金QA库不存在，使用LLM生成问题")
            return []
        try:
            with open(bank_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 支持两种格式: 纯list 或 {version, items} 包装
            if isinstance(data, list):
                bank = data
            elif isinstance(data, dict):
                bank = data.get("items", data.get("qa_pairs", []))
            else:
                bank = []

            if len(bank) < count:
                print(f"  ℹ️  黄金QA库仅有{len(bank)}条（需要{count}条），全部使用")
                return bank

            # ── 分层多样性抽样 ──
            return self._stratified_sample(bank, count)

        except Exception as e:
            print(f"  ⚠️ 加载黄金QA库失败: {e}")
            return []

    def _stratified_sample(self, bank: list, count: int) -> list:
        """分层采样：保证阶段、题型、难度三维覆盖

        算法：Maximal Coverage Sampling
        1. 先按 (phase, type, difficulty) 分组
        2. 每组至少选1条
        3. 剩余名额按组大小比例分配
        4. 组内随机
        """
        import random
        from collections import defaultdict

        # 去重（按qa_id）
        seen = set()
        unique = []
        for q in bank:
            qid = q.get("qa_id", "")
            if qid and qid not in seen:
                seen.add(qid)
                unique.append(q)

        if len(unique) <= count:
            return unique

        # 分组
        groups = defaultdict(list)
        for q in unique:
            key = (q.get("phase", "?"), q.get("type", "?"), q.get("difficulty", "?"))
            groups[key].append(q)

        # 第1轮：每组至少1条
        selected = []
        selected_ids = set()
        group_keys = list(groups.keys())
        random.shuffle(group_keys)

        for key in group_keys:
            if len(selected) >= count:
                break
            candidates = [q for q in groups[key] if q.get("qa_id") not in selected_ids]
            if candidates:
                choice = random.choice(candidates)
                selected.append(choice)
                selected_ids.add(choice.get("qa_id"))

        # 第2轮：剩余名额按优先级分配
        def priority(q):
            score = 0
            atype = q.get("adversarial_type", "")
            qtype = q.get("type", "")
            diff = q.get("difficulty", "")
            if atype:
                score += 100
            if qtype == "多轮对话":
                score += 50
            if diff == "困难":
                score += 10
            elif diff == "中等":
                score += 5
            return -score

        remaining = [q for q in unique if q.get("qa_id") not in selected_ids]
        remaining.sort(key=priority)

        while len(selected) < count and remaining:
            selected.append(remaining.pop(0))

        random.shuffle(selected)
        print(f"  📊 分层抽样: {len(selected)}/{len(unique)} 条, "
              f"覆盖{len(set(q.get('phase','?') for q in selected))}阶段/"
              f"{len(set(q.get('type','?') for q in selected))}题型/"
              f"{len(set(q.get('difficulty','?') for q in selected))}难度")

        return selected[:count]

    def run_single_question(self, question_data):
        """运行单场景测试 — P0-15: 带单场景超时保护"""
        # P0-15: 取消检查点 #1 — 场景开始前
        self._check_cancelled()

        agent = AgentRegistry.get_agent(
            self.agent_id,
            headless=self.config.get("headless", False),
            debug=self.config.get("debug", True),
        )
        if not agent:
            return {
                "question_data": question_data,
                "conversation_turns": [],
                "full_conversation": "",
                "score": None,
                "boundary": None,
                "error": f"Agent '{self.agent_id}' 未注册",
            }

        # P0-15: 单场景超时配置
        scenario_timeout = self.config.get("scenario_timeout", 600)

        try:
            self._emit("agent_start", {"agent": self.agent_id})
            if not agent.start():
                agent.close()
                self._emit("error", {"message": "Agent 启动失败"})
                return {
                    "question_data": question_data,
                    "conversation_turns": [],
                    "full_conversation": "",
                    "score": None,
                    "boundary": None,
                    "error": "Agent 启动失败",
                }

            self._emit("agent_ready", {"agent": self.agent_id})

            # 开场白
            first_message = ""
            if hasattr(agent, 'get_first_message'):
                first_message = agent.get_first_message()
                if first_message:
                    self._emit("prologue", {"text": first_message[:200]})

            max_turns = self.config.get("max_turns", 3)
            conversation_turns = []
            current_question = question_data["question"]
            scenario_start = time.monotonic()

            for turn_idx in range(max_turns):
                # P0-15: 取消检查点 #2 — 每轮对话前
                self._check_cancelled()

                # P0-15: 单场景运行时间检查
                scenario_elapsed = time.monotonic() - scenario_start
                if scenario_elapsed > scenario_timeout:
                    raise TimeoutError(
                        f"场景超时: 已运行 {scenario_elapsed:.0f}s > {scenario_timeout}s"
                    )

                self._emit("send", {
                    "turn": turn_idx + 1,
                    "question": current_question,
                    "max_turns": max_turns,
                })

                result = agent.send_message(
                    current_question, timeout=self.config.get("step_timeout", 300)
                )

                turn_data = {
                    "turn": turn_idx + 1,
                    "question": current_question,
                    "response": {
                        "status": result.status.value,
                        "response": result.text,
                        "duration": result.duration_seconds,
                    },
                }
                conversation_turns.append(turn_data)

                self._emit("response", {
                    "turn": turn_idx + 1,
                    "status": result.status.value,
                    "text": result.text[:500],
                    "text_full": result.text,
                    "duration": round(result.duration_seconds, 1),
                })

                if result.status != AgentStatus.SUCCESS:
                    err_detail = result.metadata.get("error", "未知错误")
                    print(f"  ⚠️ 第 {turn_idx+1} 轮 {result.status.value}: {err_detail[:200]}")
                    break

                if agent.is_ended(result):
                    self._emit("conversation_end", {"reason": "Agent 表达结束意图"})
                    break

                if turn_idx < max_turns - 1:
                    self._emit("generating_followup", {})
                    history = "\n".join([
                        f"用户: {t['question']}\n助手: {t['response']['response'][:200]}..."
                        for t in conversation_turns
                        if t["response"]["status"] == "success"
                    ])
                    next_q = self.followup_gen.generate_followup(
                        original_question=question_data["question"],
                        agent_response=result.text,
                        conversation_history=history,
                    )
                    if next_q and "无需追问" not in next_q:
                        current_question = next_q
                        self._emit("followup", {"question": next_q[:100]})
                    else:
                        self._emit("followup_end", {})
                        break

            self._emit("turns_done", {"total_turns": len(conversation_turns)})
            agent.close()

            # P0-15: 取消检查点 #3 — 对话完成后,评分前
            self._check_cancelled()

            # 拼接完整对话
            full_text = "\n".join([
                f"第{t['turn']}轮 - 用户: {t['question']}\n助手: {t['response']['response']}"
                for t in conversation_turns
                if t["response"]["status"] == "success"
            ])

            # ── 边界检测 (L2 KB增强, 自动降级) ──
            boundary_result = None
            if self.boundary_detector and full_text:
                self._emit("boundary_start", {})
                boundary = self.boundary_detector.detect_with_kb(
                    question=question_data["question"],
                    agent_answer=full_text,
                )
                boundary_result = boundary.to_dict()
                self._emit("boundary_done", {
                    "status": boundary.status,
                    "hit_rate": round(boundary.max_score * 100, 1),
                    "matched": boundary.matched_keywords[:10],
                    "recommendation": boundary.recommendation,
                })

            # P0-15: 取消检查点 #4 — 边界检测后,评分前
            self._check_cancelled()

            # ── 10维度评分 (多Judge投票 + 多轮追踪) ──
            self._emit("scoring", {})
            adversarial_type = question_data.get("adversarial_type")
            scoring_rubric = question_data.get("scoring_rubric")
            score = self.evaluator.evaluate(
                question=question_data["question"],
                agent_answer=full_text,
                golden_answer=question_data.get("golden_answer", ""),
                goal=question_data.get("goal", ""),
                turns=conversation_turns,
                boundary_result=boundary_result,
                adversarial_type=adversarial_type,
                scoring_rubric=scoring_rubric,
            )

            self._emit("score_done", {
                "overall": score.get("overall", 0),
                "correctness": score.get("correctness", 0),
                "relevancy": score.get("relevancy", 0),
                "completeness": score.get("completeness", 0),
                "guidance": score.get("guidance", 0),
                "followup_quality": score.get("followup_quality", 0),
                "boundary_compliance": score.get("boundary_compliance", 0),
                "boundary_status": score.get("boundary_status", ""),
                "turn_consistency": score.get("turn_consistency", 0),
                "knowledge_scaffolding": score.get("knowledge_scaffolding", 0),
                # 置信度
                "n_judges": score.get("n_judges", 1),
                "judge_variance": score.get("judge_variance", 0),
                "flags": score.get("flags", []),
                "needs_human_review": score.get("needs_human_review", False),
                "confidences": score.get("confidences", {}),
            })

            return {
                "question_data": question_data,
                "conversation_turns": conversation_turns,
                "full_conversation": full_text,
                "score": score,
                "boundary": boundary_result,
            }

        except TimeoutError as e:
            # P0-15: 场景超时
            agent.close()
            self._emit("error", {
                "message": f"场景超时: {e}",
                "traceback": traceback.format_exc(),
                "stage": "scenario_timeout",
            })
            return {
                "question_data": question_data,
                "conversation_turns": conversation_turns if 'conversation_turns' in dir() else [],
                "full_conversation": "",
                "score": None,
                "boundary": None,
                "error": f"场景超时: {e}",
            }

        except Exception as e:
            agent.close()
            self._emit("error", {
                "message": str(e),
                "traceback": traceback.format_exc(),
                "stage": "scenario_error",
            })
            return {
                "question_data": question_data,
                "conversation_turns": [],
                "full_conversation": "",
                "score": None,
                "boundary": None,
                "error": str(e),
            }

    def run_all(self):
        """运行全部测试场景 — P0-15: 带取消检查点和全局超时保护"""
        from src.watchdog import WatchdogCancelled

        num = self.config.get("num_questions", 1)
        results = []
        all_boundary = []

        use_golden = self.config.get("use_golden_qa", True)
        questions = []
        if use_golden:
            questions = self._load_golden_questions(num)

        if not questions:
            questions = [self.q_gen.generate_one() for _ in range(num)]

        self._emit("test_start", {
            "agent": self.agent_id,
            "total": len(questions),
            "questions": [{"qa_id": q.get("qa_id", ""), "phase": q.get("phase", ""),
                           "type": q.get("type", ""), "question": q.get("question", "")[:100]}
                          for q in questions],
        })

        for i, q_data in enumerate(questions):
            # P0-15: 取消检查点 — 每个场景开始前
            try:
                self._check_cancelled()
            except WatchdogCancelled:
                print(f"  ⚠️ 评测在第 {i+1}/{len(questions)} 个场景前被取消, "
                      f"已完成 {len(results)} 个场景")
                break

            self._emit("scenario_start", {
                "index": i + 1, "total": len(questions),
                "qa_id": q_data.get("qa_id", ""),
            })

            # P0-15: 使用场景超时上下文(如果 watchdog 可用)
            if self.watchdog:
                try:
                    with self.watchdog.scenario_context(scenario_index=i + 1):
                        result = self.run_single_question(q_data)
                except WatchdogCancelled as e:
                    print(f"  ⚠️ 场景 #{i+1} 被取消: {e.reason}")
                    result = {
                        "question_data": q_data,
                        "conversation_turns": [],
                        "full_conversation": "",
                        "score": None,
                        "boundary": None,
                        "error": f"取消: {e.reason}",
                    }
                    results.append(result)
                    break
            else:
                result = self.run_single_question(q_data)

            results.append(result)

            if result.get("boundary"):
                all_boundary.append(result["boundary"])

            s = result.get("score") or {}
            self._emit("scenario_done", {
                "index": i + 1,
                "overall": s.get("overall", 0) if isinstance(s, dict) else 0,
                "boundary_status": s.get("boundary_status", "N/A"),
            })

            # P0-15: 场景完成后发送心跳
            if self.watchdog:
                self.watchdog.heartbeat()

            if i < num - 1:
                # P0-15: 取消检查点 — 场景间隔
                try:
                    self._check_cancelled()
                except WatchdogCancelled:
                    print(f"  ⚠️ 评测在场景间隔被取消, 已完成 {len(results)} 个场景")
                    break
                time.sleep(2)

        # 边界汇总
        boundary_summary = None
        if self.boundary_detector and all_boundary:
            from src.boundary_detector import BoundaryResult
            wrapped = [BoundaryResult(**b) for b in all_boundary]
            boundary_summary = self.boundary_detector.get_summary(wrapped)

        # P0-15: 取消检查点 — 生成报告前
        try:
            self._check_cancelled()
        except WatchdogCancelled:
            pass  # 即使取消也尝试生成部分报告

        # 生成报告（含文字解释 + 重要性权重）
        extra = {
            "importance_weights": dict(getattr(self.evaluator, "importance_weights", {})),
            "final_total": sum(
                s.get("overall", 0) for r in results if (s := r.get("score"))
            ) / max(1, sum(1 for r in results if r.get("score"))),
        }
        report_path = self.reporter.generate_report(results, boundary_summary, extra=extra)
        report_data = self.reporter.get_last_report()

        self._emit("done", {
            "report_path": report_path,
            "summary": report_data.get("summary", {}),
            # P0-15: 标明是否被截断
            "truncated": len(results) < num,
            "completed_scenarios": len(results),
            "total_scenarios": num,
        })

        print(f"\n📊 评测报告已生成：{report_path}")
        if len(results) < num:
            print(f"⚠️ 评测被截断: 完成 {len(results)}/{num} 个场景")
        return results
