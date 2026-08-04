"""Inject calibration CSS into index.html and fix title."""
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

css_block = '''
/* Calibration — Volcano Design */
.cal-header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:16px;flex-wrap:wrap}
.cal-header-left h2{font-size:20px;font-weight:700;margin:0 0 4px;letter-spacing:-.3px}
.cal-header-left p{font-size:12.5px;color:var(--muted);margin:0;line-height:1.5;max-width:600px}
.cal-progress-ring{width:72px;height:72px;border-radius:50%;display:flex;align-items:center;justify-content:center}
.cal-progress-inner{width:60px;height:60px;border-radius:50%;background:var(--surface);display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:700;color:var(--sky)}
.cal-stats-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.cal-stat-card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;text-align:center}
.cal-stat-card:hover{border-color:var(--sky);box-shadow:0 2px 8px rgba(0,0,0,.04)}
.cal-stat-num{font-size:28px;font-weight:800;color:var(--text);letter-spacing:-.5px}
.cal-stat-text{font-size:11px;color:var(--muted);margin-top:2px}
.cal-stat-val{font-size:22px;font-weight:800;color:var(--sky)}
.cal-stat-label{font-size:11px;color:var(--muted)}
.cal-stat-threshold{font-size:9px;color:var(--dim);margin-top:1px}
.cal-warning{display:flex;align-items:center;gap:8px;padding:10px 14px;background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;font-size:12px;color:#92400e;margin-bottom:12px}
.cal-main{display:grid;grid-template-columns:360px 1fr;gap:16px}
.cal-left{background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.cal-left-toolbar{padding:10px 12px;border-bottom:1px solid var(--line);background:var(--surface-2)}
.cal-filter-group{display:flex;gap:4px;flex-wrap:wrap}
.cal-filter{padding:4px 10px;border:1px solid var(--line);border-radius:6px;background:var(--surface);font-size:11px;cursor:pointer;color:var(--muted);transition:all .15s}
.cal-filter:hover{border-color:var(--sky);color:var(--sky)}
.cal-filter.active{background:var(--sky);color:#fff;border-color:var(--sky)}
.cal-qa-list{max-height:60vh;overflow-y:auto}
.cal-item{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--line-soft);cursor:pointer;transition:background .12s;font-size:12px}
.cal-item:hover{background:var(--surface-2)}
.cal-item-active{background:var(--sel)!important;border-left:3px solid var(--sky)}
.cal-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.cal-dot.pending{background:var(--dim)}
.cal-dot.done{background:var(--green)}
.cal-badge{padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600;color:#fff;flex-shrink:0}
.cal-badge.bg-red{background:#dc2626}
.cal-badge.bg-amber{background:#d97706}
.cal-badge.bg-purple{background:#7c3aed}
.cal-badge.bg-gray{background:#64748b}
.cal-item-q{color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cal-right{background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden}
.cal-right-toolbar{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--line);background:var(--surface-2)}
.cal-score-panel{padding:16px;max-height:60vh;overflow-y:auto}
.cal-score-header{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.cal-qa-id{font-size:11px;color:var(--dim)}
.cal-question{font-size:14px;font-weight:600;line-height:1.5;margin-bottom:10px}
.cal-rubric{font-size:12px;line-height:1.6;background:var(--surface-2);border:1px solid var(--line);border-radius:8px;padding:12px;margin-bottom:12px;white-space:pre-wrap}
.cal-rubric-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--sky);margin-bottom:6px}
.cal-dim{padding:10px 0;border-bottom:1px solid var(--line-soft)}
.cal-dim-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px}
.cal-dim-head b{font-size:13px}
.cal-dim-desc{display:block;font-size:11px;color:var(--muted);font-weight:400;margin-top:1px}
.cal-dim-val{font-weight:700;font-size:18px;color:var(--sky);min-width:24px;text-align:right}
.cal-slider{width:100%;accent-color:var(--sky);height:4px}
.cal-dim-labels{display:flex;justify-content:space-between;font-size:10px;color:var(--dim);cursor:pointer;margin-top:2px}
.cal-dim-labels span:hover{color:var(--sky)}
.cal-actions{display:flex;align-items:center;margin-top:14px}
.cal-empty{text-align:center;padding:30px;color:var(--muted);font-size:13px}
.cal-loading{display:flex;align-items:center;justify-content:center;gap:8px;padding:30px;color:var(--muted);font-size:13px}
.cal-spinner{width:16px;height:16px;border:2px solid var(--line);border-top-color:var(--sky);border-radius:50%;animation:cal-spin .6s linear infinite}
@keyframes cal-spin{to{transform:rotate(360deg)}}
.cal-dims-scroll{max-height:45vh;overflow-y:auto;padding-right:4px}
.cal-card{position:relative;background:var(--surface);border-radius:var(--radius);padding:16px 17px;border:1px solid var(--line);box-shadow:var(--shadow);overflow:hidden}
'''

# Insert before </style>
end = content.find('</style>')
if end > 0:
    content = content[:end] + css_block + '\n' + content[end:]

# Fix title
content = content.replace('<title>AI Agent 评测平台 v3.4</title>', '<title>AI Agent 评测平台</title>')

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done: CSS injected, title fixed')
