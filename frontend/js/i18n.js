/* ═══════════════════════════════════════════════════════════
   i18n.js — 中英双语核心模块 (全局脚本)

   设计目标:
   1. 作为普通 <script> 加载, 挂载全局函数 window.t / window.setLang 等
   2. ES 模块页面通过 i18n-bridge.js 间接调用, 共享同一份字典和语言状态
   3. 通过 onLangChange(fn) 实现响应式语言切换 — 切换语言后所有注册的
      页面模块自动重渲染
   4. 新增页面只需: 在 I18N_DICT 中添加键值 → 代码中用 t('key') →
      onLangChange 注册重渲染 → 完成

   字典组织规则:
   - key 用 snake_case, 按功能分组: nav_ / card_ / btn_ / th_ / ph_ /
     cal_ / kb_ / we_ / qa_ / rp_ / chart_ / dim_ / status_ / eval_ /
     health_ / common_
   - 值可以是字符串或函数 (用于含变量的动态文本)
   - 中文是主语言 (zh), 英文是翻译 (en)
   ═══════════════════════════════════════════════════════════ */

(function (global) {
  'use strict';

  // ═══════════════════════════════════════════
  // 完整字典
  // ═══════════════════════════════════════════
  var I18N_DICT = {
    zh: {
      // ── 全局 / 标题 ──
      title: 'AI Agent 评测平台 v3.5',
      app_name: 'AI Agent 评测平台 v3.5',
      brand: 'AI Agent 评测',

      // ── 导航 ──
      nav_home: '📊 首页',
      nav_platform_health: '🔌 平台监控',
      nav_test: '🧪 测试运行',
      nav_reports: '📋 报告',
      nav_calibration: '🎯 校准',
      nav_kb: '📚 知识库',
      nav_qa: '✅ QA管理',

      // ── 语言切换 ──
      lang_label: 'EN',
      lang_switch_to: 'English',
      lang_tooltip: '切换语言 / Switch language',

      // ── 系统状态 ──
      sys_online: '在线',
      sys_offline: 'API离线',
      sys_ws_connected: '🟢 WS已连接',
      sys_ws_disconnected: '🔌 WS断开',
      sys_loading: '加载中...',
      sys_error: '加载失败',
      sys_no_data: '暂无数据',
      sys_coming_soon: '即将上线',

      // ── 首页 / Dashboard ──
      home_title: '评测总览',
      home_desc: '实时监控关键指标，一键发起 Agent 评测',
      home_ready: '就绪，选择一个 Agent 点击"开始测评"',

      card_total_tests: '📊 历史测试',
      card_avg_score: '⭐ 平均综合分',
      card_qa_approved: '✅ 已审核QA',
      card_qa_pending: '🕐 待审',
      card_sys_status: '系统状态',

      // ── 实时评测面板 ──
      live_title: '🔍 实时评测过程',
      live_hint: '点击上方"开始测评"查看完整过程',
      live_ws_status: 'WS断开',
      live_elapsed: '⏱️',
      live_step: '📍',
      live_errors: '❌',
      live_progress: '📊',
      live_step_ready: '就绪',
      live_step_starting: '启动中',
      live_step_agent_connecting: '连接 Agent中',
      live_step_agent_ready: 'Agent 就绪',
      live_step_sending: '发送问题',
      live_step_receiving: '收到回复',
      live_step_followup: '生成追问中',
      live_step_send_followup: '发送追问',
      live_step_boundary: '边界检测中',
      live_step_scoring: '评分中',
      live_step_done: '✅ 评测完成',
      live_step_cancelled: '⏹ 已取消',
      live_step_error: '❌ 出错',
      live_step_conversation_done: '对话完成',
      live_step_scenario_done: '场景完成',
      live_step_scenario_start: '场景开始',

      // ── 图表 ──
      chart_trend: '📈 得分趋势',
      chart_radar: '🎯 维度分布',
      chart_overall_label: '综合得分',
      chart_dim_label: '维度得分',
      recent_reports: '📋 最近报告',

      // ── 测试运行器 ──
      test_title: '测试运行',
      test_desc: '配置并运行评测任务，观察实时事件日志',
      test_config: '⚙️ 测试配置',
      test_config_label: '⚙️ 配置',
      test_agent_label: 'Agent:',
      test_profile_label: 'Profile:',
      test_scenarios_label: '场景数:',
      test_start_btn: '▶ 开始测试',
      test_stop_btn: '⏹ 停止',
      test_waiting: '等待测试启动...',
      test_starting: '⏳ 正在启动...',
      test_event_log: '📋 实时事件日志',
      test_history: '📋 历史会话',
      test_no_history: '暂无历史会话',

      // ── 报告 ──
      reports_title: '评测报告',
      reports_desc: '查看历次评测的结果与状态',
      reports_no_data: '暂无报告',
      reports_no_data_hint: '暂无报告。运行一次评测后在此查看。',
      reports_select_hint: '← 选择一个报告查看详情',
      reports_compare_mode: '⚖️ 对比模式',
      reports_exit_compare: '✕ 退出对比',
      reports_compare_hint: '勾选 2-5 个报告进行对比',
      reports_max_compare: '最多对比5个报告',
      reports_loading_detail: '加载报告详情...',
      reports_detail_empty: '报告数据为空',
      reports_detail_unavailable: '报告数据不可用',
      reports_detail_not_found: '未找到报告数据。请先运行一次评测。',

      // ── 报告详情 ──
      rp_header_title: 'AI Agent Evaluation Report · v3.5',
      rp_overall_title: '🤖 全维度测评报告',
      rp_overall_score: '综合评分 / 5.0',
      rp_section_calc: '🧮 总分计算过程 (透明化)',
      rp_section_calc_desc: '公式: 最终总分 = Σ(维度分 × 重要性权重); 每个维度分 = L1规则×30% + L3 LLM×70%。缺失维度权重自动重归一化。',
      rp_section_evidence: '🔐 证据链 · 报告完整性证明',
      rp_section_evidence_desc: 'SHA-256(完整报告内容) — 下载JSON→重算SHA-256→比对此值→匹配=未篡改',
      rp_section_confidence: '📊 置信度 & 可靠性分析',
      rp_section_confidence_desc: 'CV (变异系数) = σ/μ — CV<10%=高可信(🟢), 10-25%=中可信(🟡), 25-50%=低可信(🟠), >50%=不可靠(🔴)。95% CI = μ ± 1.96×σ/√n。',
      rp_section_judge: '⚖️ 多Judge共识',
      rp_section_dims: '📈 10维度评分总览',
      rp_section_scenarios: '📝 场景详情',
      rp_section_boundary: '🛡️ 边界检测统计',
      rp_section_radar: '🎯 维度分布',
      rp_section_comparison: '📊 维度对比',
      rp_section_score_compare: '📋 得分对比',
      rp_section_max_delta: '📐 最大差异',
      rp_footer: '报告由 AI Agent 评测平台 v3.5 自动生成 · 三层级联评分 · 证据链SHA-256封存 · 置信度CV量化',
      rp_btn_print: '🖨 打印/PDF',
      rp_btn_close: '关闭',
      rp_btn_export_json: '📥 导出 JSON',
      rp_btn_export_csv: '📊 导出 CSV',
      rp_btn_delete: '🗑 删除',
      rp_btn_full_html: '📄 完整HTML报告(含证据链)',
      rp_btn_copy_hash: '📋 复制',
      rp_confirm_delete: '确定删除此报告？',
      rp_deleted: '已删除',
      rp_exported: '已导出',
      rp_db_report: 'DB报告 · 点击查看详情',
      rp_file_report: '文件报告',
      rp_persona_matrix: '多画像矩阵报告',
      rp_storage_label: '存储后端:',
      rp_verify_label: '验证:',
      rp_report_id_label: '报告ID:',
      rp_config_fp_label: '⚙️ 配置指纹:',
      rp_hash_sealed: '✅ 已封存',
      rp_audit_title: '📋 审计清单',
      rp_hash_chain_title: '🔗 场景哈希链 (防篡改):',

      // ── 网页评测 ──
      we_title: '网页评测',
      we_desc: '对目标网页做全维度可用性检测',
      we_start_btn: '🔍 开始评测',
      we_refresh_btn: '🔄 刷新',
      we_url_label: 'URL:',
      we_hint: '点击"开始评测"检测网页',
      we_evaluating: '⏳ 正在评测网页...',
      we_no_data: '暂无网页评测结果',
      we_history_title: '📋 历史评测',
      we_no_history: '暂无历史评测',
      we_result_title: '📊 最新评测结果',
      we_collapse: '✕ 收起',
      we_overall: '综合得分',
      we_dim_performance: '性能',
      we_dim_accessibility: '可访问性',
      we_dim_best_practices: '最佳实践',
      we_dim_ai_function: 'AI对话',
      we_dim_ui_ux: 'UI/UX',
      we_dim_content: '内容',
      we_run_failed: '评测失败',
      we_detail_indicator: '指标',
      we_detail_value: '值',
      we_detail_eval: '评估',
      we_lcp: 'LCP',
      we_ttfb: 'TTFB',
      we_cls: 'CLS',
      we_https: 'HTTPS',
      we_a11y_violations: '可访问性违规',
      we_ai_latency: 'AI延迟',
      we_raw_result: '📋 查看原始结果',
      we_config_title: '🔍 评测配置',
      we_progress_text: '⏳ 评测进行中...',

      // ── 知识库 ──
      kb_title: '知识库',
      kb_desc: '搜索与查看火山引擎课程知识库',
      kb_configured: '✅ 火山引擎已配置',
      kb_unconfigured: '❌ 未配置',
      kb_connected: '已连接火山引擎',
      kb_not_configured: '❌ 火山引擎未配置',
      kb_service_id: '服务ID',
      kb_no_service_id: '(未设置)',
      kb_search_ph: '搜索课程知识库…',
      kb_search_btn: '🔍 搜索',
      kb_sync_btn: '🔄 同步火山引擎知识库',
      kb_searching: '🔍 正在搜索 4 个 Phase 知识库…',
      kb_no_query: '请输入搜索关键词',
      kb_search_fail: '搜索失败',
      kb_no_results: '未找到 "{0}" 的相关课程资料',
      kb_results_fmt: function (n, e) { return n + ' 条结果 · ' + (e && e.length ? '⚠️' + e.join(', ') : '✅ 全部 Phase 连通'); },
      kb_relevance: '相关度',
      kb_provider: '火山引擎',
      kb_search_title: '🔍 搜索知识库',
      kb_search_input_ph: '输入查询...',
      kb_searching_text: '⏳ 搜索中...',
      kb_no_results_text: '未找到结果',
      kb_bases_title: '📚 知识库管理',
      kb_no_bases: '暂无已同步的知识库',
      kb_sync_hint: '点击"同步"按钮同步',
      kb_doc_count: '文档',
      kb_sync_status: '状态',
      kb_last_sync: '上次同步',
      kb_syncing: '⏳ 正在同步火山引擎知识库...',
      kb_sync_success: '已同步 {0} 个知识库',
      kb_sync_failed: '同步失败',
      kb_doc_title: '📄 文档列表',
      kb_doc_select_hint: '选择知识库查看文档',
      kb_doc_no_data: '暂无文档',
      kb_info_title: '📚 4Phase 火山引擎知识库',
      kb_info_phases: 'Phase1 国产AI技术基础 · Phase2 新型硬件设计 · Phase3&4 环境感知与触觉反馈 · Phase5 具身智能控制',

      // ── 平台监控 ──
      health_title: '📡 平台监控',
      health_desc: '实时监控被测平台健康状态 & 评测事件',
      health_loading: '加载中...',
      health_unavailable: '平台交互数据加载失败',
      health_no_data: '无法获取平台健康度数据 — 请检查被测平台是否在线',
      health_refresh_btn: '🔄 刷新检测',
      health_refreshing: '⏳ 检测中 (2-3分钟)...',
      health_refresh_text: '⏳ 正在运行全量平台健康检测 (2-3分钟)...',
      health_refresh_fail: '检测失败',
      health_summary: '综合健康度',
      health_working: '正常',
      health_degraded: '降级',
      health_broken: '故障',
      health_total: '共',
      health_items: '项功能',
      health_p0_warning: '🚨 P0 阻断:',
      health_p0_detail: '以下核心功能不可用',
      health_p0_blocked: 'P0 功能受阻',
      health_feature_table_title: '功能 / API / 状态 / 延迟 / 详情',
      health_log_title: '📋 评测事件日志',
      health_log_loaded: '页面已加载。在「测试运行」启动评测后此处实时显示。',
      health_log_cleared: '日志已清空',
      health_ws_card: 'WebSocket',
      health_ws_connected: '🟢 已连接',
      health_ws_disconnected: '🔌 断开',
      health_eval_status: '评测状态',
      health_eval_idle: '空闲',
      health_eval_running: '▶ 运行中',
      health_scenarios_done: '已完成场景',
      health_elapsed: '耗时',
      health_eval_started: '🚀 测评启动',
      health_eval_all_done: '🎉 全部完成!',
      health_data_age_seconds: '{0}秒前',
      health_data_age_minutes: '{0}分钟前',
      health_data_age_hours: '{0}小时前',
      health_data_age_label: '数据: ',
      health_data_realtime: '实时探活',
      health_feature_status: '状态',
      health_feature_api: 'API',
      health_feature_latency: '延迟',
      health_feature_detail: '详情',
      health_feature_name: '功能',

      // ── 校准 ──
      cal_title: '🎯 人类校准工作台',
      cal_subtitle: 'Human vs LLM Judge 一致性校验 · 10维度评分 · Cohen\'s κ · Spearman ρ',
      cal_load_btn: '📋 加载待校准项',
      cal_results_btn: '📊 查看校准统计',
      cal_generate_btn: '🔄 生成校准集',
      cal_queue_title: '校准队列',
      cal_queue_empty: '点击"加载待校准项"开始',
      cal_queue_no_items: '无待校准项 · 点击"生成校准集"创建',
      cal_scoring_title: '评分面板',
      cal_scoring_empty: '← 从左侧选择一个QA对开始评分',
      cal_stats_title: '校准统计',
      cal_stats_empty: '提交评分后查看统计',
      cal_submit_btn: '✅ 提交评分',
      cal_skip_btn: '⏭ 跳过',
      cal_item_scored: '✓',
      cal_item_pending: '待评',
      cal_score_label: '未评',
      cal_score_label_fmt: function (s) { return s + '/5'; },
      cal_complete_hint: '请至少完成8个维度的评分',
      cal_submit_success: '评分已提交 ✅',
      cal_submit_failed: '提交失败',
      cal_generate_success: '校准集已生成 ✅',
      cal_generate_failed: '生成失败',
      cal_api_unavailable: '校准API可能未部署，请确保后端运行中',
      cal_cohens_kappa: "Cohen's κ",
      cal_spearman_rho: 'Spearman ρ',
      cal_mae: 'MAE',
      cal_scored_count: '已标注',
      cal_dim_bias: '偏差',
      cal_question_label: '问题:',
      cal_answer_label: 'Agent回答:',
      cal_golden_label: '黄金答案:',

      // ── QA 管理 ──
      qa_title: 'QA 管理',
      qa_desc: '审核与管理黄金问答集',
      qa_filter_pending: '待审核',
      qa_filter_all: '全部',
      qa_filter_approved: '已通过',
      qa_filter_rejected: '已拒绝',
      qa_filter_all_phase: '全部阶段',
      qa_filter_all_type: '全部题型',
      qa_search_ph: '🔍 搜索问题/答案...',
      qa_generate_btn: '🔄 从Excel生成QA',
      qa_batch_approve_btn: '✅ 批量通过',
      qa_no_data: '暂无QA数据',
      qa_select_hint: '← 选择一条QA查看详情',
      qa_approved: '已通过',
      qa_rejected: '已拒绝',
      qa_detail_title_prefix: '📝 ',
      qa_question_label: '问题',
      qa_answer_label: '黄金答案',
      qa_knowledge_points: '知识点',
      qa_source_label: '来源',
      qa_approve_btn: '✅ 通过',
      qa_reject_btn: '❌ 拒绝',
      qa_save_btn: '✏️ 保存修改',
      qa_delete_btn: '🗑 删除',
      qa_already_reviewed_prefix: '已审核 · ',
      qa_reject_reason_prompt: '拒绝原因（可选）:',
      qa_confirm_delete: '确定删除此QA？',
      qa_deleted: '已删除',
      qa_saved: '修改已保存',
      qa_generating: '⏳ 正在从Excel生成QA...',
      qa_generate_success: '已生成 {0} 条QA，请审核',
      qa_batch_confirm: '确定批量通过当前筛选的所有待审核QA？',
      qa_batch_none: '没有待审核的QA',
      qa_batch_success: '已批量通过 {0} 条',
      qa_type_concept: '概念解释',
      qa_type_procedure: '操作步骤',
      qa_type_comparison: '对比分析',
      qa_type_scenario: '应用场景',
      qa_record_count: '条',
      qa_page_of: function (tot, p, tp) { return '共 ' + tot + ' 条，第 ' + p + '/' + tp + ' 页 '; },

      // ── 10维度标签 ──
      dim_correctness: '事实正确性',
      dim_relevancy: '答案相关性',
      dim_completeness: '内容完整性',
      dim_guidance: '教学引导力',
      dim_followup_quality: '追问响应质量',
      dim_boundary_compliance: '边界合规性',
      dim_turn_consistency: '跨轮一致性',
      dim_knowledge_scaffolding: '知识递进性',
      dim_overhelping: '过度帮助',
      dim_fairness_bias: '公平性偏见',

      dim_short_correctness: '正确性',
      dim_short_relevancy: '相关性',
      dim_short_completeness: '完整性',
      dim_short_guidance: '引导力',
      dim_short_followup_quality: '追问质量',
      dim_short_boundary_compliance: '边界合规',
      dim_short_turn_consistency: '跨轮一致',
      dim_short_knowledge_scaffolding: '知识递进',
      dim_short_overhelping: '过度帮助',
      dim_short_fairness_bias: '公平性',

      dim_icons: {
        correctness: '📐', relevancy: '🎯', completeness: '📋', guidance: '🧭',
        followup_quality: '🔄', boundary_compliance: '🛡️', turn_consistency: '🔗',
        knowledge_scaffolding: '📈', overhelping: '⚠️', fairness_bias: '⚖️'
      },

      dim_desc_correctness: '回答的事实准确度，有无幻觉',
      dim_desc_relevancy: '是否切题',
      dim_desc_completeness: '关键知识点覆盖',
      dim_desc_guidance: 'Socratic教学法引导',
      dim_desc_followup_quality: '多轮追问后深入程度',
      dim_desc_boundary_compliance: '是否在课程边界内',
      dim_desc_turn_consistency: '多轮信息一致性',
      dim_desc_knowledge_scaffolding: '知识层层递进',
      dim_desc_overhelping: '是否直接给代码(反向)',
      dim_desc_fairness_bias: '不同画像质量一致性',

      // ── 报告详情 维度计算表头 ──
      rp_th_dim: '维度',
      rp_th_score: '得分',
      rp_th_weight: '权重',
      rp_th_contribution: '贡献',
      rp_th_scale: '1-5',
      rp_th_total: 'Σ 最终总分',

      // ── 置信度表头 ──
      rp_conf_th_dim: '维度',
      rp_conf_th_mean: '均值',
      rp_conf_th_cv: 'CV',
      rp_conf_th_ci: '95%CI',
      rp_conf_th_reliability: '可靠性',

      // ── 对比表头 ──
      rp_compare_th_time: '时间',
      rp_compare_th_overall: '综合',

      // ── 分数等级 ──
      score_excellent: '卓越',
      score_good: '优秀',
      score_fair: '良好',
      score_poor: '需改进',
      score_fail: '不合格',

      // ── 状态标签 ──
      status_pending: '待审核',
      status_approved: '已通过',
      status_rejected: '已拒绝',
      status_success: '成功',
      status_failed: '失败',
      status_synced: '已同步',
      status_error: '错误',
      status_running: '运行中',
      status_idle: '空闲',

      // ── 按钮 / 通用动作 ──
      btn_start_eval: '▶ 开始测评',
      btn_refresh: '🔄 刷新',
      btn_clear: '清空',
      btn_close: '关闭',
      btn_save: '保存',
      btn_cancel: '取消',
      btn_delete: '删除',
      btn_export: '导出',
      btn_approve: '通过',
      btn_reject: '拒绝',
      btn_prev: '上一页',
      btn_next: '下一页',
      btn_view: '查看',
      btn_loading: '加载中...',

      // ── 表格通用头 ──
      th_time: '时间',
      th_agent: 'Agent',
      th_overall: '综合分',
      th_scenarios: '场景数',
      th_status: '状态',
      th_question: '问题',
      th_phase: '阶段',
      th_type: '题型',
      th_action: '操作',

      // ── 场景 / 对话 / 评测过程 ──
      scenario_label: '场景',
      scenario_divider: function (i, tt) { return '📝 场景 ' + i + '/' + tt; },
      scenario_n: function (i, tt) { return '场景 ' + i + '/' + tt; },
      turn_label: '第{0}轮',
      turn_reply: function (turn, st, dur) { return '第' + turn + '轮回复 · ' + st + ' · ' + dur + 's'; },
      turn_count: function (n) { return n + ' 轮'; },
      scenarios_count: function (n) { return n + '场景'; },
      pts: function (n) { return n + '分'; },
      docs_count: function (n) { return n + ' 文档'; },
      kb_service: function (id) { return '服务ID: ' + id; },

      // ── 评测事件 ──
      eval_test_start: function (agent, total) { return '评测启动: Agent=' + agent + ' | ' + total + ' 个场景'; },
      eval_agent_connecting: function (agent) { return '正在连接 Agent: ' + agent; },
      eval_agent_ready: function (agent) { return 'Agent 已就绪: ' + agent; },
      eval_prologue: function (text) { return '开场白: ' + text; },
      eval_send: function (turn, q) { return '第' + turn + '轮发送: ' + q; },
      eval_response: function (turn, status, dur, text) { return '第' + turn + '轮回复 · ' + status + ' · ' + dur + 's\n' + text; },
      eval_followup: function (q) { return '追问: ' + q; },
      eval_boundary_done: function (status, hitRate, rec) { return '边界检测完成: ' + status + ' | 命中率: ' + hitRate + ' | 建议: ' + rec; },
      eval_score_done_line: function (d) { return '综合:' + d.overall + '/5 | 正确性:' + d.correctness + ' 相关性:' + d.relevancy + ' 完整性:' + d.completeness + ' 引导力:' + d.guidance + ' 追问:' + d.followup_quality + ' 边界:' + d.boundary_compliance; },
      eval_score_done: '评分完成',
      eval_done: '✅ 评测完成',
      eval_cancelled: function (reason) { return '评测已取消: ' + (reason || '用户取消'); },
      eval_scenario_done: function (idx, overall, boundary) { return '场景 ' + idx + ' 完成 · 综合分: ' + overall + ' · 边界: ' + boundary; },
      eval_conversation_done: function (turns) { return '对话完成 (' + turns + ' 轮)'; },
      eval_generating_followup: '正在生成追问...',
      eval_followup_end: '追问结束',
      eval_conversation_end: function (reason) { return '对话结束: ' + reason; },
      eval_boundary_start: '正在检测边界合规...',
      eval_scoring: '正在评分 (多Judge投票)...',
      eval_needs_human_review: '🔍 需要人工复核',
      eval_error_unknown: '未知错误',
      eval_error_traceback_title: '📋 完整错误堆栈',
      eval_truncated: function (completed, total) { return ' (截断: ' + completed + '/' + total + ')'; },
      eval_progress_fmt: function (scIdx, scTotal, turnIdx, turnTotal) { return '场景 ' + scIdx + '/' + scTotal + ' · 第 ' + turnIdx + '/' + turnTotal + ' 轮'; },

      // ── 意图标签 ──
      intent_concept: '📖 概念理解',
      intent_deep_q: '🔍 深入追问',
      intent_deep_q2: '🔁 连续追问',
      intent_stuck: '🛠️ 卡壳诊断',
      intent_challenge: '🚀 挑战引导',
      intent_want_code: '⚠️ 索要代码',
      intent_boundary: '🚧 越界测试',

      // ── Agent 选项 ──
      agent_option_hi_phase1: 'Phase 1 — 国产AI技术基础',
      agent_option_hi_phase2: 'Phase 2 — 新型硬件设计',
      agent_option_hi_phase3_4: 'Phase 3&4 — 环境感知与触觉反馈',
      agent_option_hi_phase5: 'Phase 5 — 具身智能控制',
      agent_option_platform: '实训教学平台',

      // ── 场景卡片标签 ──
      scenario_card_user: '👤 用户',
      scenario_card_agent: '🤖 Agent',
      scenario_card_judge: '🧑‍⚖️ Judge',
      scenario_card_l1_rule: '📏 L1规则',
      scenario_card_l3_judge: '🧠 L3 Judge',
      scenario_card_overall: '📊 综合',
      scenario_card_needs_review: '需人工复核',
      scenario_card_full_conversation: '💬 完整对话',

      // ── 通用 ──
      log_cleared: '日志已清空',
      no_data: '暂无数据',
      load_failed: function (msg) { return '加载失败: ' + msg; },
      request_failed: function (msg) { return '请求失败: ' + msg; },
      start_failed: function (msg) { return '启动失败: ' + msg; },
      operation_failed: '操作失败',
      network_error: '网络错误',

      // ── 报告 场景详情 特殊项 ──
      rp_verifiable: '可验证',
      rp_reference: '参考',
      rp_data_completeness: '📊',

      // ── 向后兼容别名 (旧版 key → 新版 key 映射) ──
      app_h1: '🤖 AI Agent 评测平台 v3.5',
      online: '在线',
      ph_home_title: '评测总览', ph_home_desc: '实时监控关键指标，一键发起 Agent 评测',
      ph_qa_title: 'QA 管理', ph_qa_desc: '审核与管理黄金问答集',
      ph_test_title: '测试运行', ph_test_desc: '配置并运行评测任务，观察实时事件日志',
      ph_reports_title: '评测报告', ph_reports_desc: '查看历次评测的结果与状态',
      ph_webeval_title: '网页评测', ph_webeval_desc: '对目标网页做全维度可用性检测',
      ph_kb_title: '知识库', ph_kb_desc: '搜索与查看火山引擎课程知识库',
      nav_webeval: '🌐 网页评测',
      card_total: '📊 历史测试', card_avg: '⭐ 平均综合分', card_approved: '✅ 已审核QA', card_pending: '🕐 待审',
      opt_platform: '实训教学平台', opt_web_test: '网站测试 (Playwright)',
      home_live_hint: '点击上方"开始测评"查看完整过程',
      loading: '加载中...',
      qa_all: '全部', qa_pending: '待审核', qa_approved: '已通过', qa_rejected: '已拒绝',
      ph_search: '搜索...',
      scenarios_label: '场景', btn_start_test: '▶ 开始测试',
      event_log: '📋 事件日志', tr_wait: '等待测试启动...',
      btn_web_eval: '🔍 开始评测', web_hint: '点击"开始评测"检测网页',
      btn_sync_kb: '🔄 同步火山引擎知识库',
      no_reports_hint: '暂无报告。选择 Mock Agent 点击"开始测评"即可生成第一份报告。',
      eval_running: '评测进行中...', eval_started: '评测启动...',
      score_done: '评分完成',
      starting_eval: '⏳ 正在启动评测...', starting: '启动中...', starting2: '⏳ 正在启动...', start_fail: '启动失败: ',
      no_qa: '暂无QA数据', prev: '上一页', next: '下一页',
      no_reports: '暂无报告。完成一次评测后在此查看。',
      no_web: '暂无网页评测结果',
      kb_configured: '✅ 火山引擎已配置', kb_unconfigured: '❌ 未配置', kb_connected: '已连接火山引擎',
      no_kb: '暂无已同步的知识库。点击"同步"按钮。',
      evaluating_web: '⏳ 正在评测网页...', syncing: '⏳ 正在同步...',
      kb_btn_search: '🔍 搜索',
      kb_searching: '🔍 正在搜索 4 个 Phase 知识库…', kb_no_query: '请输入搜索关键词',
      kb_search_fail: '搜索失败',
      kb_no_results: '未找到 "{0}" 的相关课程资料',
      kb_results_fmt: function (n, e) { return n + ' 条结果 · ' + (e && e.length ? '⚠️' + e.join(', ') : '✅ 全部 Phase 连通'); },
      kb_relevance: '相关度', kb_provider: '火山引擎',
      dim_labels: ['正确性', '相关性', '完整性', '引导力', '追问质量', '边界合规', '跨轮一致', '知识递进', '过度帮助', '公平性'],
      status_pending: '待审核', status_approved: '已通过', status_rejected: '已拒绝', status_success: '成功', status_failed: '失败', status_synced: '已同步', status_error: '错误',
      agent_scenarios: function (a, n) { return 'Agent: ' + a + ' | ' + n + ' 场景'; },
      scenario_n: function (i, tt) { return '场景 ' + i + '/' + tt; },
      scenario_div: function (i, tt) { return '📝 场景 ' + i + '/' + tt; },
      turn_reply: function (turn, st, dur) { return '第' + turn + '轮回复 · ' + st + ' · ' + dur + 's'; },
      score_line: function (d) { return '综合:' + d.overall + '/5 | 正确性:' + d.correctness + ' 相关性:' + d.relevancy + ' 完整性:' + d.completeness + ' 引导力:' + d.guidance + ' 追问:' + d.followup_quality + ' 边界:' + d.boundary_compliance; },
      scenarios_count: function (n) { return n + '场景'; },
      page_of: function (tot, p, tp) { return '共 ' + tot + ' 条，第 ' + p + '/' + tp + ' 页 '; },
      pts: function (n) { return n + '分'; },
      docs_count: function (n) { return n + ' 文档'; },
      kb_service: function (id) { return '服务ID: ' + id; },
    },

    // ═══════════════════════════════════════════
    // English
    // ═══════════════════════════════════════════
    en: {
      title: 'AI Agent Evaluation Platform v3.5',
      app_name: 'AI Agent Evaluation Platform v3.5',
      brand: 'AI Agent Eval',

      nav_home: '📊 Home',
      nav_platform_health: '🔌 Platform Health',
      nav_test: '🧪 Test Runner',
      nav_reports: '📋 Reports',
      nav_calibration: '🎯 Calibration',
      nav_kb: '📚 Knowledge Base',
      nav_qa: '✅ QA Review',

      lang_label: '中',
      lang_switch_to: '中文',
      lang_tooltip: 'Switch language / 切换语言',

      sys_online: 'Online',
      sys_offline: 'API Offline',
      sys_ws_connected: '🟢 WS Connected',
      sys_ws_disconnected: '🔌 WS Disconnected',
      sys_loading: 'Loading...',
      sys_error: 'Load failed',
      sys_no_data: 'No data',
      sys_coming_soon: 'Coming soon',

      home_title: 'Overview',
      home_desc: 'Monitor key metrics and launch an evaluation in one click',
      home_ready: 'Ready — pick an Agent and click "Start Eval"',

      card_total_tests: '📊 Total Tests',
      card_avg_score: '⭐ Avg Overall',
      card_qa_approved: '✅ QA Approved',
      card_qa_pending: '🕐 Pending',
      card_sys_status: 'System Status',

      live_title: '🔍 Live Evaluation',
      live_hint: 'Click "Start Eval" above to watch the full process',
      live_ws_status: 'WS Disconnected',
      live_elapsed: '⏱️',
      live_step: '📍',
      live_errors: '❌',
      live_progress: '📊',
      live_step_ready: 'Ready',
      live_step_starting: 'Starting',
      live_step_agent_connecting: 'Connecting Agent',
      live_step_agent_ready: 'Agent Ready',
      live_step_sending: 'Sending question',
      live_step_receiving: 'Receiving reply',
      live_step_followup: 'Generating follow-up',
      live_step_send_followup: 'Sending follow-up',
      live_step_boundary: 'Boundary check',
      live_step_scoring: 'Scoring',
      live_step_done: '✅ Evaluation done',
      live_step_cancelled: '⏹ Cancelled',
      live_step_error: '❌ Error',
      live_step_conversation_done: 'Conversation done',
      live_step_scenario_done: 'Scenario done',
      live_step_scenario_start: 'Scenario start',

      chart_trend: '📈 Score Trend',
      chart_radar: '🎯 Dimension Radar',
      chart_overall_label: 'Overall Score',
      chart_dim_label: 'Dimension Score',
      recent_reports: '📋 Recent Reports',

      test_title: 'Test Runner',
      test_desc: 'Configure and run evaluations with a live event log',
      test_config: '⚙️ Test Config',
      test_config_label: '⚙️ Config',
      test_agent_label: 'Agent:',
      test_profile_label: 'Profile:',
      test_scenarios_label: 'Scenarios:',
      test_start_btn: '▶ Start Test',
      test_stop_btn: '⏹ Stop',
      test_waiting: 'Waiting for test to start...',
      test_starting: '⏳ Starting...',
      test_event_log: '📋 Live Event Log',
      test_history: '📋 Session History',
      test_no_history: 'No session history',

      reports_title: 'Reports',
      reports_desc: 'Browse the results and status of past evaluations',
      reports_no_data: 'No reports',
      reports_no_data_hint: 'No reports yet. They will appear here after an evaluation.',
      reports_select_hint: '← Select a report to view details',
      reports_compare_mode: '⚖️ Compare Mode',
      reports_exit_compare: '✕ Exit Compare',
      reports_compare_hint: 'Select 2-5 reports to compare',
      reports_max_compare: 'Max 5 reports for comparison',
      reports_loading_detail: 'Loading report details...',
      reports_detail_empty: 'Report data is empty',
      reports_detail_unavailable: 'Report data unavailable',
      reports_detail_not_found: 'Report data not found. Please run an evaluation first.',

      rp_header_title: 'AI Agent Evaluation Report · v3.5',
      rp_overall_title: '🤖 Full-Dimension Evaluation Report',
      rp_overall_score: 'Overall Score / 5.0',
      rp_section_calc: '🧮 Score Calculation (Transparent)',
      rp_section_calc_desc: 'Formula: Final Score = Σ(Dimension Score × Importance Weight); Each dimension = L1 Rules×30% + L3 LLM×70%. Missing dimensions auto-renormalized.',
      rp_section_evidence: '🔐 Evidence Chain · Report Integrity Proof',
      rp_section_evidence_desc: 'SHA-256(Full Report) — Download JSON → Recompute SHA-256 → Compare → Match = Untampered',
      rp_section_confidence: '📊 Confidence & Reliability Analysis',
      rp_section_confidence_desc: 'CV = σ/μ — CV<10%=High(🟢), 10-25%=Medium(🟡), 25-50%=Low(🟠), >50%=Unreliable(🔴). 95% CI = μ ± 1.96×σ/√n.',
      rp_section_judge: '⚖️ Multi-Judge Consensus',
      rp_section_dims: '📈 10-Dimension Score Overview',
      rp_section_scenarios: '📝 Scenario Details',
      rp_section_boundary: '🛡️ Boundary Detection Stats',
      rp_section_radar: '🎯 Dimension Radar',
      rp_section_comparison: '📊 Dimension Comparison',
      rp_section_score_compare: '📋 Score Comparison',
      rp_section_max_delta: '📐 Maximum Variance',
      rp_footer: 'Report auto-generated by AI Agent Evaluation Platform v3.5 · 3-Tier Cascade Scoring · SHA-256 Evidence Chain · CV Quantified Confidence',
      rp_btn_print: '🖨 Print/PDF',
      rp_btn_close: 'Close',
      rp_btn_export_json: '📥 Export JSON',
      rp_btn_export_csv: '📊 Export CSV',
      rp_btn_delete: '🗑 Delete',
      rp_btn_full_html: '📄 Full HTML Report (with Evidence)',
      rp_btn_copy_hash: '📋 Copy',
      rp_confirm_delete: 'Delete this report?',
      rp_deleted: 'Deleted',
      rp_exported: 'Exported',
      rp_db_report: 'DB Report · Click for details',
      rp_file_report: 'File Report',
      rp_persona_matrix: 'Persona Matrix Report',
      rp_storage_label: 'Storage backend:',
      rp_verify_label: 'Verify:',
      rp_report_id_label: 'Report ID:',
      rp_config_fp_label: '⚙️ Config fingerprint:',
      rp_hash_sealed: '✅ Sealed',
      rp_audit_title: '📋 Audit Manifest',
      rp_hash_chain_title: '🔗 Scenario Hash Chain (Tamper-proof):',

      we_title: 'Web Eval',
      we_desc: 'Run a full-dimension usability check on a target site',
      we_start_btn: '🔍 Start Eval',
      we_refresh_btn: '🔄 Refresh',
      we_url_label: 'URL:',
      we_hint: 'Click "Start Eval" to inspect the site',
      we_evaluating: '⏳ Evaluating website...',
      we_no_data: 'No web-eval results yet',
      we_history_title: '📋 Eval History',
      we_no_history: 'No eval history',
      we_result_title: '📊 Latest Result',
      we_collapse: '✕ Collapse',
      we_overall: 'Overall Score',
      we_dim_performance: 'Performance',
      we_dim_accessibility: 'Accessibility',
      we_dim_best_practices: 'Best Practices',
      we_dim_ai_function: 'AI Chat',
      we_dim_ui_ux: 'UI/UX',
      we_dim_content: 'Content',
      we_run_failed: 'Evaluation failed',
      we_detail_indicator: 'Metric',
      we_detail_value: 'Value',
      we_detail_eval: 'Rating',
      we_lcp: 'LCP',
      we_ttfb: 'TTFB',
      we_cls: 'CLS',
      we_https: 'HTTPS',
      we_a11y_violations: 'A11y Violations',
      we_ai_latency: 'AI Latency',
      we_raw_result: '📋 View Raw Result',
      we_config_title: '🔍 Eval Config',
      we_progress_text: '⏳ Evaluation in progress...',

      kb_title: 'Knowledge Base',
      kb_desc: 'Search and inspect the Volcengine course KB',
      kb_configured: '✅ Volcengine configured',
      kb_unconfigured: '❌ Not configured',
      kb_connected: 'Volcengine connected',
      kb_not_configured: '❌ Volcengine not configured',
      kb_service_id: 'Service ID',
      kb_no_service_id: '(not set)',
      kb_search_ph: 'Search course KB…',
      kb_search_btn: '🔍 Search',
      kb_sync_btn: '🔄 Sync Volcengine KB',
      kb_searching: '🔍 Searching across 4 Phase KBs…',
      kb_no_query: 'Please enter a search query',
      kb_search_fail: 'Search failed',
      kb_no_results: 'No results found for "{0}"',
      kb_results_fmt: function (n, e) { return n + ' results · ' + (e && e.length ? '⚠️' + e.join(', ') : '✅ All phases connected'); },
      kb_relevance: 'Relevance',
      kb_provider: 'Volcengine',
      kb_search_title: '🔍 Search Knowledge Base',
      kb_search_input_ph: 'Enter query...',
      kb_searching_text: '⏳ Searching...',
      kb_no_results_text: 'No results found',
      kb_bases_title: '📚 Knowledge Base Management',
      kb_no_bases: 'No synced knowledge base yet',
      kb_sync_hint: 'Click "Sync" to sync',
      kb_doc_count: 'Docs',
      kb_sync_status: 'Status',
      kb_last_sync: 'Last sync',
      kb_syncing: '⏳ Syncing Volcengine KB...',
      kb_sync_success: 'Synced {0} knowledge bases',
      kb_sync_failed: 'Sync failed',
      kb_doc_title: '📄 Documents',
      kb_doc_select_hint: 'Select a knowledge base to view documents',
      kb_doc_no_data: 'No documents',
      kb_info_title: '📚 4-Phase Volcengine KB',
      kb_info_phases: 'Phase1 AI Technology Basics · Phase2 Novel Hardware Design · Phase3&4 Environmental & Tactile Perception · Phase5 Embodied Intelligence Control',

      health_title: '📡 Platform Health',
      health_desc: 'Real-time platform health monitoring & eval events',
      health_loading: 'Loading...',
      health_unavailable: 'Platform interaction data failed to load',
      health_no_data: 'Cannot fetch platform health data — check if the target platform is online',
      health_refresh_btn: '🔄 Refresh Check',
      health_refreshing: '⏳ Checking (2-3 min)...',
      health_refresh_text: '⏳ Running full platform health check (2-3 min)...',
      health_refresh_fail: 'Check failed',
      health_summary: 'Overall Health',
      health_working: 'Working',
      health_degraded: 'Degraded',
      health_broken: 'Broken',
      health_total: 'Total',
      health_items: 'features',
      health_p0_warning: '🚨 P0 Blocking:',
      health_p0_detail: 'The following core features are unavailable',
      health_p0_blocked: 'P0 features blocked',
      health_feature_table_title: 'Feature / API / Status / Latency / Detail',
      health_log_title: '📋 Eval Event Log',
      health_log_loaded: 'Page loaded. Start an evaluation in Test Runner to see live events.',
      health_log_cleared: 'Log cleared',
      health_ws_card: 'WebSocket',
      health_ws_connected: '🟢 Connected',
      health_ws_disconnected: '🔌 Disconnected',
      health_eval_status: 'Eval Status',
      health_eval_idle: 'Idle',
      health_eval_running: '▶ Running',
      health_scenarios_done: 'Scenarios Done',
      health_elapsed: 'Elapsed',
      health_eval_started: '🚀 Eval Started',
      health_eval_all_done: '🎉 All Done!',
      health_data_age_seconds: '{0}s ago',
      health_data_age_minutes: '{0}min ago',
      health_data_age_hours: '{0}h ago',
      health_data_age_label: 'Data: ',
      health_data_realtime: 'Live probe',
      health_feature_status: 'Status',
      health_feature_api: 'API',
      health_feature_latency: 'Latency',
      health_feature_detail: 'Detail',
      health_feature_name: 'Feature',

      cal_title: '🎯 Human Calibration Workspace',
      cal_subtitle: 'Human vs LLM Judge Consistency · 10-Dim Scoring · Cohen\'s κ · Spearman ρ',
      cal_load_btn: '📋 Load Calibration Items',
      cal_results_btn: '📊 View Stats',
      cal_generate_btn: '🔄 Generate Set',
      cal_queue_title: 'Calibration Queue',
      cal_queue_empty: 'Click "Load Items" to start',
      cal_queue_no_items: 'No items · Click "Generate Set" to create',
      cal_scoring_title: 'Scoring Panel',
      cal_scoring_empty: '← Select a QA pair from the left to start scoring',
      cal_stats_title: 'Calibration Stats',
      cal_stats_empty: 'Submit scores to view statistics',
      cal_submit_btn: '✅ Submit Score',
      cal_skip_btn: '⏭ Skip',
      cal_item_scored: '✓',
      cal_item_pending: 'Pending',
      cal_score_label: 'Unscored',
      cal_score_label_fmt: function (s) { return s + '/5'; },
      cal_complete_hint: 'Please score at least 8 dimensions',
      cal_submit_success: 'Score submitted ✅',
      cal_submit_failed: 'Submit failed',
      cal_generate_success: 'Calibration set generated ✅',
      cal_generate_failed: 'Generation failed',
      cal_api_unavailable: 'Calibration API may not be deployed. Ensure backend is running.',
      cal_cohens_kappa: "Cohen's κ",
      cal_spearman_rho: 'Spearman ρ',
      cal_mae: 'MAE',
      cal_scored_count: 'Scored',
      cal_dim_bias: 'Bias',
      cal_question_label: 'Question:',
      cal_answer_label: 'Agent Answer:',
      cal_golden_label: 'Golden Answer:',

      qa_title: 'QA Review',
      qa_desc: 'Review and manage the golden QA set',
      qa_filter_pending: 'Pending',
      qa_filter_all: 'All',
      qa_filter_approved: 'Approved',
      qa_filter_rejected: 'Rejected',
      qa_filter_all_phase: 'All Phases',
      qa_filter_all_type: 'All Types',
      qa_search_ph: '🔍 Search question/answer...',
      qa_generate_btn: '🔄 Generate from Excel',
      qa_batch_approve_btn: '✅ Batch Approve',
      qa_no_data: 'No QA data',
      qa_select_hint: '← Select a QA item to view details',
      qa_approved: 'Approved',
      qa_rejected: 'Rejected',
      qa_detail_title_prefix: '📝 ',
      qa_question_label: 'Question',
      qa_answer_label: 'Golden Answer',
      qa_knowledge_points: 'Knowledge Points',
      qa_source_label: 'Source',
      qa_approve_btn: '✅ Approve',
      qa_reject_btn: '❌ Reject',
      qa_save_btn: '✏️ Save',
      qa_delete_btn: '🗑 Delete',
      qa_already_reviewed_prefix: 'Reviewed · ',
      qa_reject_reason_prompt: 'Rejection reason (optional):',
      qa_confirm_delete: 'Delete this QA?',
      qa_deleted: 'Deleted',
      qa_saved: 'Changes saved',
      qa_generating: '⏳ Generating QA from Excel...',
      qa_generate_success: 'Generated {0} QA items. Please review.',
      qa_batch_confirm: 'Batch approve all pending QA in current filter?',
      qa_batch_none: 'No pending QA items',
      qa_batch_success: 'Batch approved {0} items',
      qa_type_concept: 'Concept',
      qa_type_procedure: 'Procedure',
      qa_type_comparison: 'Comparison',
      qa_type_scenario: 'Scenario',
      qa_record_count: 'records',
      qa_page_of: function (tot, p, tp) { return tot + ' total · page ' + p + '/' + tp + ' '; },

      dim_correctness: 'Factual Correctness',
      dim_relevancy: 'Answer Relevance',
      dim_completeness: 'Content Completeness',
      dim_guidance: 'Teaching Guidance',
      dim_followup_quality: 'Follow-up Quality',
      dim_boundary_compliance: 'Boundary Compliance',
      dim_turn_consistency: 'Cross-Turn Consistency',
      dim_knowledge_scaffolding: 'Knowledge Scaffolding',
      dim_overhelping: 'Over-Helping',
      dim_fairness_bias: 'Fairness / Bias',

      dim_short_correctness: 'Correctness',
      dim_short_relevancy: 'Relevance',
      dim_short_completeness: 'Completeness',
      dim_short_guidance: 'Guidance',
      dim_short_followup_quality: 'Follow-up',
      dim_short_boundary_compliance: 'Boundary',
      dim_short_turn_consistency: 'Turn Consistency',
      dim_short_knowledge_scaffolding: 'Scaffolding',
      dim_short_overhelping: 'Over-helping',
      dim_short_fairness_bias: 'Fairness',

      dim_icons: {
        correctness: '📐', relevancy: '🎯', completeness: '📋', guidance: '🧭',
        followup_quality: '🔄', boundary_compliance: '🛡️', turn_consistency: '🔗',
        knowledge_scaffolding: '📈', overhelping: '⚠️', fairness_bias: '⚖️'
      },

      dim_desc_correctness: 'Factual accuracy, hallucination check',
      dim_desc_relevancy: 'Answer relevance to question',
      dim_desc_completeness: 'Key knowledge point coverage',
      dim_desc_guidance: 'Socratic teaching method',
      dim_desc_followup_quality: 'Depth after multi-turn follow-up',
      dim_desc_boundary_compliance: 'Within course boundaries',
      dim_desc_turn_consistency: 'Cross-turn info consistency',
      dim_desc_knowledge_scaffolding: 'Progressive knowledge building',
      dim_desc_overhelping: 'Avoids giving direct code (inverse)',
      dim_desc_fairness_bias: 'Quality consistency across personas',

      rp_th_dim: 'Dimension',
      rp_th_score: 'Score',
      rp_th_weight: 'Weight',
      rp_th_contribution: 'Contribution',
      rp_th_scale: '1-5',
      rp_th_total: 'Σ Final Score',

      rp_conf_th_dim: 'Dimension',
      rp_conf_th_mean: 'Mean',
      rp_conf_th_cv: 'CV',
      rp_conf_th_ci: '95% CI',
      rp_conf_th_reliability: 'Reliability',

      rp_compare_th_time: 'Time',
      rp_compare_th_overall: 'Overall',

      score_excellent: 'Excellent',
      score_good: 'Good',
      score_fair: 'Fair',
      score_poor: 'Needs Improvement',
      score_fail: 'Fail',

      status_pending: 'Pending',
      status_approved: 'Approved',
      status_rejected: 'Rejected',
      status_success: 'Success',
      status_failed: 'Failed',
      status_synced: 'Synced',
      status_error: 'Error',
      status_running: 'Running',
      status_idle: 'Idle',

      btn_start_eval: '▶ Start Eval',
      btn_refresh: '🔄 Refresh',
      btn_clear: 'Clear',
      btn_close: 'Close',
      btn_save: 'Save',
      btn_cancel: 'Cancel',
      btn_delete: 'Delete',
      btn_export: 'Export',
      btn_approve: 'Approve',
      btn_reject: 'Reject',
      btn_prev: 'Prev',
      btn_next: 'Next',
      btn_view: 'View',
      btn_loading: 'Loading...',

      th_time: 'Time',
      th_agent: 'Agent',
      th_overall: 'Overall',
      th_scenarios: 'Scenarios',
      th_status: 'Status',
      th_question: 'Question',
      th_phase: 'Phase',
      th_type: 'Type',
      th_action: 'Action',

      scenario_label: 'Scenario',
      scenario_divider: function (i, tt) { return '📝 Scenario ' + i + '/' + tt; },
      scenario_n: function (i, tt) { return 'Scenario ' + i + '/' + tt; },
      turn_label: 'Turn {0}',
      turn_reply: function (turn, st, dur) { return 'Turn ' + turn + ' reply · ' + st + ' · ' + dur + 's'; },
      turn_count: function (n) { return n + ' turns'; },
      scenarios_count: function (n) { return n + ' scenarios'; },
      pts: function (n) { return n + ' pts'; },
      docs_count: function (n) { return n + ' docs'; },
      kb_service: function (id) { return 'Service ID: ' + id; },

      eval_test_start: function (agent, total) { return 'Eval started: Agent=' + agent + ' | ' + total + ' scenarios'; },
      eval_agent_connecting: function (agent) { return 'Connecting to Agent: ' + agent; },
      eval_agent_ready: function (agent) { return 'Agent ready: ' + agent; },
      eval_prologue: function (text) { return 'Prologue: ' + text; },
      eval_send: function (turn, q) { return 'Turn ' + turn + ' send: ' + q; },
      eval_response: function (turn, status, dur, text) { return 'Turn ' + turn + ' reply · ' + status + ' · ' + dur + 's\n' + text; },
      eval_followup: function (q) { return 'Follow-up: ' + q; },
      eval_boundary_done: function (status, hitRate, rec) { return 'Boundary check done: ' + status + ' | Hit rate: ' + hitRate + ' | Recommendation: ' + rec; },
      eval_score_done_line: function (d) { return 'Overall:' + d.overall + '/5 | Correctness:' + d.correctness + ' Relevance:' + d.relevancy + ' Completeness:' + d.completeness + ' Guidance:' + d.guidance + ' Follow-up:' + d.followup_quality + ' Boundary:' + d.boundary_compliance; },
      eval_score_done: 'Scoring done',
      eval_done: '✅ Evaluation done',
      eval_cancelled: function (reason) { return 'Evaluation cancelled: ' + (reason || 'User cancelled'); },
      eval_scenario_done: function (idx, overall, boundary) { return 'Scenario ' + idx + ' done · Overall: ' + overall + ' · Boundary: ' + boundary; },
      eval_conversation_done: function (turns) { return 'Conversation done (' + turns + ' turns)'; },
      eval_generating_followup: 'Generating follow-up...',
      eval_followup_end: 'Follow-up ended',
      eval_conversation_end: function (reason) { return 'Conversation ended: ' + reason; },
      eval_boundary_start: 'Running boundary compliance check...',
      eval_scoring: 'Scoring (Multi-Judge voting)...',
      eval_needs_human_review: '🔍 Needs human review',
      eval_error_unknown: 'Unknown error',
      eval_error_traceback_title: '📋 Full Error Traceback',
      eval_truncated: function (completed, total) { return ' (truncated: ' + completed + '/' + total + ')'; },
      eval_progress_fmt: function (scIdx, scTotal, turnIdx, turnTotal) { return 'Scenario ' + scIdx + '/' + scTotal + ' · Turn ' + turnIdx + '/' + turnTotal; },

      intent_concept: '📖 Concept',
      intent_deep_q: '🔍 Deep Question',
      intent_deep_q2: '🔁 Follow-up Chain',
      intent_stuck: '🛠️ Stuck Diagnosis',
      intent_challenge: '🚀 Challenge',
      intent_want_code: '⚠️ Code Request',
      intent_boundary: '🚧 Boundary Test',

      agent_option_hi_phase1: 'Phase 1 — AI Technology Basics',
      agent_option_hi_phase2: 'Phase 2 — Novel Hardware Design',
      agent_option_hi_phase3_4: 'Phase 3&4 — Perception & Tactile',
      agent_option_hi_phase5: 'Phase 5 — Embodied Intelligence',
      agent_option_platform: 'Teaching Platform',

      scenario_card_user: '👤 User',
      scenario_card_agent: '🤖 Agent',
      scenario_card_judge: '🧑‍⚖️ Judge',
      scenario_card_l1_rule: '📏 L1 Rules',
      scenario_card_l3_judge: '🧠 L3 Judge',
      scenario_card_overall: '📊 Overall',
      scenario_card_needs_review: 'Needs Review',
      scenario_card_full_conversation: '💬 Full Conversation',

      log_cleared: 'Log cleared',
      no_data: 'No data',
      load_failed: function (msg) { return 'Load failed: ' + msg; },
      request_failed: function (msg) { return 'Request failed: ' + msg; },
      start_failed: function (msg) { return 'Start failed: ' + msg; },
      operation_failed: 'Operation failed',
      network_error: 'Network error',

      rp_verifiable: 'Verifiable',
      rp_reference: 'Reference',
      rp_data_completeness: '📊',

      // ── Backward compat aliases (old keys) ──
      app_h1: '🤖 AI Agent Evaluation Platform v3.5',
      online: 'Online',
      ph_home_title: 'Overview', ph_home_desc: 'Monitor key metrics and launch an evaluation in one click',
      ph_qa_title: 'QA Review', ph_qa_desc: 'Review and manage the golden QA set',
      ph_test_title: 'Test Runner', ph_test_desc: 'Configure and run evaluations with a live event log',
      ph_reports_title: 'Reports', ph_reports_desc: 'Browse the results and status of past evaluations',
      ph_webeval_title: 'Web Eval', ph_webeval_desc: 'Run a full-dimension usability check on a target site',
      ph_kb_title: 'Knowledge Base', ph_kb_desc: 'Search and inspect the Volcengine course KB',
      nav_webeval: '🌐 Web Eval',
      card_total: '📊 Total Tests', card_avg: '⭐ Avg Overall', card_approved: '✅ QA Approved', card_pending: '🕐 Pending',
      opt_platform: 'Teaching Platform', opt_web_test: 'Website Test (Playwright)',
      home_live_hint: 'Click "Start Eval" above to watch the full process',
      loading: 'Loading...',
      qa_all: 'All', qa_pending: 'Pending', qa_approved: 'Approved', qa_rejected: 'Rejected',
      ph_search: 'Search...',
      scenarios_label: 'scenarios', btn_start_test: '▶ Start Test',
      event_log: '📋 Event Log', tr_wait: 'Waiting for test to start...',
      btn_web_eval: '🔍 Start Eval', web_hint: 'Click "Start Eval" to inspect the site',
      btn_sync_kb: '🔄 Sync Volcengine KB',
      no_reports_hint: 'No reports yet. Pick a Mock Agent and click "Start Eval" to generate the first one.',
      eval_running: 'Evaluating...', eval_started: 'Evaluation started...',
      score_done: 'Scoring done',
      starting_eval: '⏳ Starting evaluation...', starting: 'Starting...', starting2: '⏳ Starting...', start_fail: 'Start failed: ',
      no_qa: 'No QA data', prev: 'Prev', next: 'Next',
      no_reports: 'No reports yet. They will appear here after an evaluation.',
      no_web: 'No web-eval results yet',
      kb_configured: '✅ Volcengine configured', kb_unconfigured: '❌ Not configured', kb_connected: 'Volcengine connected',
      no_kb: 'No synced knowledge base yet. Click "Sync".',
      evaluating_web: '⏳ Evaluating website...', syncing: '⏳ Syncing...',
      kb_btn_search: '🔍 Search',
      kb_searching: '🔍 Searching across 4 Phase KBs…', kb_no_query: 'Please enter a search query',
      kb_search_fail: 'Search failed',
      kb_no_results: 'No results found for "{0}"',
      kb_results_fmt: function (n, e) { return n + ' results · ' + (e && e.length ? '⚠️' + e.join(', ') : '✅ All phases connected'); },
      kb_relevance: 'Relevance', kb_provider: 'Volcengine',
      dim_labels: ['Correctness', 'Relevancy', 'Completeness', 'Guidance', 'Follow-up', 'Boundary', 'Turn Consist.', 'Scaffolding', 'Overhelping', 'Fairness'],
      status_pending: 'Pending', status_approved: 'Approved', status_rejected: 'Rejected', status_success: 'Success', status_failed: 'Failed', status_synced: 'Synced', status_error: 'Error',
      agent_scenarios: function (a, n) { return 'Agent: ' + a + ' | ' + n + ' scenarios'; },
      scenario_n: function (i, tt) { return 'Scenario ' + i + '/' + tt; },
      scenario_div: function (i, tt) { return '📝 Scenario ' + i + '/' + tt; },
      turn_reply: function (turn, st, dur) { return 'Turn ' + turn + ' reply · ' + st + ' · ' + dur + 's'; },
      score_line: function (d) { return 'Overall:' + d.overall + '/5 | Correct:' + d.correctness + ' Relevant:' + d.relevancy + ' Complete:' + d.completeness + ' Guidance:' + d.guidance + ' Follow-up:' + d.followup_quality + ' Boundary:' + d.boundary_compliance; },
      scenarios_count: function (n) { return n + ' scenarios'; },
      page_of: function (tot, p, tp) { return tot + ' total · page ' + p + '/' + tp + ' '; },
      pts: function (n) { return n + ' pts'; },
      docs_count: function (n) { return n + ' docs'; },
      kb_service: function (id) { return 'Service ID: ' + id; },
    }
  };

  // ═══════════════════════════════════════════
  // 运行时状态
  // ═══════════════════════════════════════════
  var LANG = 'zh';
  try { LANG = localStorage.getItem('lang') || 'zh'; } catch (e) { /* ignore */ }
  var _listeners = [];

  // ═══════════════════════════════════════════
  // 公共 API
  // ═══════════════════════════════════════════

  /**
   * 将 snake_case key 转换为可读文本 (smart fallback)
   * 例如: "nav_home" → "Nav Home", "rp_section_calc" → "Rp Section Calc"
   * 当字典中完全没有这个 key 时使用, 确保用户至少看到可读的文字
   */
  function _keyToText(key) {
    return key
      .replace(/_+/g, ' ')
      .replace(/\b\w/g, function(c) { return c.toUpperCase(); })
      .trim();
  }

  /**
   * t(key, ...args) — 获取当前语言的文本
   * 如果 key 对应的值是函数, 则调用它并传入 args
   * 如果英文翻译缺失, 回退到中文
   * 如果中文也不存在, 将 key 转为可读文本 (smart fallback)
   */
  function t(key) {
    var dict = I18N_DICT[LANG] || I18N_DICT.zh;
    var v = dict[key];
    if (v === undefined) {
      // 回退到中文
      v = (I18N_DICT.zh[key] !== undefined) ? I18N_DICT.zh[key] : undefined;
    }
    if (v === undefined) {
      // 最终 fallback: 将 key 转为可读文本
      // 同时自动注册这个 key (标记为需要翻译)
      _registerMissingKey(key);
      return _keyToText(key);
    }
    if (typeof v === 'function') {
      return v.apply(null, Array.prototype.slice.call(arguments, 1));
    }
    return v;
  }

  /**
   * 自动注册缺失的 key — 收集起来, 通过 API 发送给后端
   * 去重 + 延迟批量上报, 避免频繁请求
   */
  var _missingKeys = {};
  var _missingReportTimer = null;

  function _registerMissingKey(key) {
    if (_missingKeys[key]) return;
    _missingKeys[key] = true;

    // 延迟2秒批量上报, 避免启动时洪水
    if (_missingReportTimer) clearTimeout(_missingReportTimer);
    _missingReportTimer = setTimeout(_reportMissingKeys, 2000);
  }

  async function _reportMissingKeys() {
    var keys = Object.keys(_missingKeys);
    if (!keys.length) return;
    _missingKeys = {};

    var API = '';
    try {
      if (window.location.pathname.indexOf('/test/') === 0) API = '/test';
    } catch(e) {}

    try {
      await fetch(API + '/api/i18n/auto-register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({keys: keys})
      });
      console.log('[i18n] Auto-registered ' + keys.length + ' new keys:', keys);
    } catch(e) {
      console.warn('[i18n] Failed to auto-register keys:', keys, e.message);
    }
  }

  function getLang() {
    return LANG;
  }

  function setLang(l) {
    if (l === LANG) return;
    LANG = l;
    try { localStorage.setItem('lang', l); } catch (e) { /* ignore */ }

    // 更新 document
    var dict = I18N_DICT[LANG] || I18N_DICT.zh;
    document.title = dict.title || I18N_DICT.zh.title;
    document.documentElement.lang = (LANG === 'zh') ? 'zh-CN' : 'en';

    // 更新静态 data-i18n 元素
    applyStaticI18n();

    // 更新语言切换按钮
    updateLangToggle();

    // 通知所有监听者 (页面模块重渲染)
    _listeners.forEach(function (fn) {
      try { fn(LANG); } catch (e) { console.warn('[i18n] Listener error:', e); }
    });
  }

  /**
   * 注册语言切换回调
   * 返回取消注册的函数
   */
  function onLangChange(fn) {
    _listeners.push(fn);
    return function () {
      var i = _listeners.indexOf(fn);
      if (i >= 0) _listeners.splice(i, 1);
    };
  }

  /**
   * 更新所有 [data-i18n] 和 [data-i18n-ph] 元素
   */
  function applyStaticI18n() {
    var dict = I18N_DICT[LANG] || I18N_DICT.zh;
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var v = dict[el.getAttribute('data-i18n')];
      if (typeof v === 'string') el.textContent = v;
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(function (el) {
      var v = dict[el.getAttribute('data-i18n-ph')];
      if (typeof v === 'string') el.setAttribute('placeholder', v);
    });
  }

  function updateLangToggle() {
    var lt = document.getElementById('langToggle');
    if (lt) lt.textContent = (LANG === 'zh') ? 'EN' : '中';
  }

  /**
   * tStatus(status) — 获取状态标签的翻译
   */
  function tStatus(s) {
    return t('status_' + s);
  }

  /**
   * 获取维度标签 (短版, 用于图表/卡片)
   */
  function getDimLabels() {
    var DIM_KEYS = ['correctness', 'relevancy', 'completeness', 'guidance',
      'followup_quality', 'boundary_compliance', 'turn_consistency',
      'knowledge_scaffolding', 'overhelping', 'fairness_bias'];
    return DIM_KEYS.map(function (k) { return t('dim_short_' + k); });
  }

  /**
   * 获取维度标签 (完整版, 用于报告)
   */
  function getDimFullLabels() {
    var DIM_KEYS = ['correctness', 'relevancy', 'completeness', 'guidance',
      'followup_quality', 'boundary_compliance', 'turn_consistency',
      'knowledge_scaffolding', 'overhelping', 'fairness_bias'];
    return DIM_KEYS.map(function (k) { return t('dim_' + k); });
  }

  /**
   * 渲染已翻译的 HTML 片段 — 用于动态生成的内容
   * 示例: renderTemplate('eval_test_start', agent, total)
   */
  function renderTemplate(key) {
    var args = Array.prototype.slice.call(arguments, 1);
    return t.apply(null, [key].concat(args));
  }

  /**
   * getDimIcon(key) — 获取维度图标
   * dim_icons 在字典中是嵌套对象 (zh/en 共享), 直接查 I18N_DICT.zh.dim_icons
   */
  function getDimIcon(key) {
    var icons = I18N_DICT.zh.dim_icons;
    return (icons && icons[key]) ? icons[key] : '';
  }

  // ═══════════════════════════════════════════
  // 动态字典加载 (从后端 API 获取最新字典)
  // ═══════════════════════════════════════════
  var _remoteLoaded = false;
  var _dictUpdateListeners = [];

  function isRemoteLoaded() { return _remoteLoaded; }

  function onDictUpdate(fn) {
    _dictUpdateListeners.push(fn);
    return function() {
      var i = _dictUpdateListeners.indexOf(fn);
      if (i >= 0) _dictUpdateListeners.splice(i, 1);
    };
  }

  async function loadRemoteDict() {
    // 检测 API 前缀: 适配 /test/ 前缀和直接访问两种部署方式
    var API = '';
    try {
      var p = window.location.pathname;
      if (p.indexOf('/test/') === 0) API = '/test';
    } catch(e) {}

    try {
      // 1. 检查 localStorage 缓存
      var cached = null;
      var cachedVer = null;
      try {
        cached = JSON.parse(localStorage.getItem('i18n_dict_cache') || 'null');
        cachedVer = localStorage.getItem('i18n_dict_ver');
      } catch(e) {}

      // 2. 快速版本检查
      var vResp = await fetch(API + '/api/i18n/version');
      if (!vResp.ok) throw new Error('Version check failed: ' + vResp.status);
      var vData = await vResp.json();

      // 3. 版本匹配 → 用缓存
      if (cached && cached.zh && cached.en && cachedVer === vData.version) {
        Object.assign(I18N_DICT.zh, cached.zh);
        Object.assign(I18N_DICT.en, cached.en);
        _remoteLoaded = true;
      } else {
        // 4. 版本不匹配 → 获取完整字典
        var zhR = await fetch(API + '/api/i18n/dict?lang=zh');
        var enR = await fetch(API + '/api/i18n/dict?lang=en');
        if (!zhR.ok || !enR.ok) throw new Error('Dict fetch failed');

        var zhD = await zhR.json();
        var enD = await enR.json();

        // 5. 合并到 I18N_DICT (API 数据覆盖内嵌默认值)
        if (zhD.dict) Object.assign(I18N_DICT.zh, zhD.dict);
        if (enD.dict) Object.assign(I18N_DICT.en, enD.dict);

        // 6. 写入 localStorage 缓存
        try {
          localStorage.setItem('i18n_dict_cache', JSON.stringify({zh: zhD.dict, en: enD.dict}));
          localStorage.setItem('i18n_dict_ver', zhD.version || vData.version || '0');
        } catch(e) { /* quota exceeded — silently ignore */ }

        _remoteLoaded = true;
      }
    } catch(e) {
      console.warn('[i18n] Remote dict load failed, using embedded fallback:', e.message);
    }

    // 7. 通知所有监听者 (字典可能已更新)
    if (_remoteLoaded) {
      applyStaticI18n();
      updateLangToggle();
      _listeners.forEach(function(fn) {
        try { fn(LANG); } catch(e) { console.warn('[i18n] Listener error:', e); }
      });
      _dictUpdateListeners.forEach(function(fn) {
        try { fn(); } catch(e) { console.warn('[i18n] Dict-update listener error:', e); }
      });
    }
  }

  // ═══════════════════════════════════════════
  // 暴露全局
  // ═══════════════════════════════════════════
  global.t = t;
  global.getLang = getLang;
  global.setLang = setLang;
  global.onLangChange = onLangChange;
  global.tStatus = tStatus;
  global.getDimLabels = getDimLabels;
  global.getDimFullLabels = getDimFullLabels;
  global.applyStaticI18n = applyStaticI18n;
  global.I18N_DICT = I18N_DICT; // 暴露字典供高级用例
  global.renderTemplate = renderTemplate;
  global.getDimIcon = getDimIcon;
  global.loadRemoteDict = loadRemoteDict;
  global.isRemoteLoaded = isRemoteLoaded;
  global.onDictUpdate = onDictUpdate;

  // 同时挂载在 I18n 命名空间下, 方便批量引用
  global.I18n = {
    t: t,
    getLang: getLang,
    setLang: setLang,
    onLangChange: onLangChange,
    tStatus: tStatus,
    getDimLabels: getDimLabels,
    getDimFullLabels: getDimFullLabels,
    getDimIcon: getDimIcon,
    applyStaticI18n: applyStaticI18n,
    dict: I18N_DICT,
    renderTemplate: renderTemplate,
    loadRemoteDict: loadRemoteDict,
    isRemoteLoaded: isRemoteLoaded,
    onDictUpdate: onDictUpdate
  };

  // ── 页面加载时自动执行远程字典加载 ──
  if (typeof window !== 'undefined') {
    // 延迟到 DOM ready 后执行, 避免阻塞首次渲染
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function() { loadRemoteDict(); });
    } else {
      loadRemoteDict();
    }
  }

})(typeof window !== 'undefined' ? window : this);
