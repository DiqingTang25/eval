/* ════════════════════════════════════════════
   Chart.js 封装 — 趋势图 / 雷达图 / 柱状图
   ════════════════════════════════════════════ */

const CHART_COLORS = {
    blue: '#38bdf8',
    blueFill: 'rgba(56, 189, 248, 0.1)',
    green: '#22c55e',
    yellow: '#f59e0b',
    red: '#ef4444',
    purple: '#a855f7',
    grid: '#334155',
    text: '#94a3b8',
    textMuted: '#64748b',
};

// 10维度完整key列表（对齐后端evaluator.DIMENSION_NAMES）
const DIM_KEYS_10 = [
    'correctness', 'relevancy', 'completeness', 'guidance',
    'followup_quality', 'boundary_compliance', 'turn_consistency',
    'knowledge_scaffolding', 'overhelping', 'fairness_bias',
];

function _getDimLabels() {
    // Use i18n labels if available, otherwise fall back to Chinese
    if (typeof window !== 'undefined' && window.getDimLabels) {
        return window.getDimLabels();
    }
    return ['正确性', '相关性', '完整性', '引导力', '追问质量', '边界合规', '跨轮一致', '知识递进', '过度帮助', '公平性'];
}

export function drawTrendChart(canvasId, trendData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');

    // 销毁旧图表
    if (canvas._chart) canvas._chart.destroy();

    const labels = trendData.map(t => t.ts?.slice(9, 17) || '').reverse();
    const scores = trendData.map(t => t.score).reverse();

    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: (typeof window !== 'undefined' && window.t) ? window.t('chart_overall_label', '综合得分') : '综合得分',
                data: scores,
                borderColor: CHART_COLORS.blue,
                backgroundColor: CHART_COLORS.blueFill,
                fill: true,
                tension: 0.3,
                pointRadius: 4,
                pointBackgroundColor: CHART_COLORS.blue,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: CHART_COLORS.text, font: { size: 11 } } },
            },
            scales: {
                x: {
                    ticks: { color: CHART_COLORS.textMuted, font: { size: 10 } },
                    grid: { color: CHART_COLORS.grid },
                },
                y: {
                    min: 0, max: 5,
                    ticks: { color: CHART_COLORS.textMuted, stepSize: 1 },
                    grid: { color: CHART_COLORS.grid },
                },
            },
        },
    });

    canvas._chart = chart;
    return chart;
}

export function drawRadarChart(canvasId, dimensionScores) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');

    if (canvas._chart) canvas._chart.destroy();

    const keys = DIM_KEYS_10;
    const values = keys.map(k => dimensionScores[k] || 0);

    const chart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: _getDimLabels(),
            datasets: [{
                label: (typeof window !== 'undefined' && window.t) ? window.t('chart_dim_label', '维度得分') : '维度得分',
                data: values,
                borderColor: CHART_COLORS.blue,
                backgroundColor: CHART_COLORS.blueFill,
                borderWidth: 2,
                pointRadius: 3,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    min: 0, max: 5,
                    grid: { color: CHART_COLORS.grid },
                    pointLabels: { color: CHART_COLORS.text, font: { size: 10 } },
                    ticks: { display: false, stepSize: 1 },
                },
            },
            plugins: {
                legend: { labels: { color: CHART_COLORS.text, font: { size: 11 } } },
            },
        },
    });

    canvas._chart = chart;
    return chart;
}

export function drawComparisonChart(canvasId, reports) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');

    if (canvas._chart) canvas._chart.destroy();

    const colors = ['#38bdf8', '#f59e0b', '#22c55e', '#a855f7', '#ef4444'];
    const keys = DIM_KEYS_10;
    const datasets = reports.map((r, i) => ({
        label: r.timestamp?.slice(9, 19) || `Report ${i + 1}`,
        data: keys.map(k => r.scores?.[k] || 0),
        borderColor: colors[i % colors.length],
        backgroundColor: 'transparent',
        tension: 0.2,
        pointRadius: 3,
    }));

    const chart = new Chart(ctx, {
        type: 'line',
        data: { labels: _getDimLabels(), datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: CHART_COLORS.text, font: { size: 10 } } },
            },
            scales: {
                x: { ticks: { color: CHART_COLORS.textMuted, font: { size: 10 } }, grid: { color: CHART_COLORS.grid } },
                y: { min: 0, max: 5, ticks: { color: CHART_COLORS.textMuted, stepSize: 1 }, grid: { color: CHART_COLORS.grid } },
            },
        },
    });

    canvas._chart = chart;
    return chart;
}

export function destroyChart(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (canvas && canvas._chart) {
        canvas._chart.destroy();
        canvas._chart = null;
    }
}
