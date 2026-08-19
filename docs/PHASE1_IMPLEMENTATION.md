# Phase 1 实现清单 — Platform Explorer (PX)

> **最后更新**: 2026-08-05  
> **状态**: ✅ 核心框架完成, 🔄 待完善响应体捕获  
> **接手AI**: 按此清单了解现状并继续

---

## ✅ 已完成

### 探索器核心 (`src/platform_probe/`)

| 文件 | 状态 | 说明 |
|------|------|------|
| `models.py` | ✅ | 全部 dataclass (L0~L4 数据模型) |
| `confidence.py` | ✅ | 6信号API分类 + Step类型分类 + 置信度汇总 |
| `l0_auth.py` | ✅ | **4路径自适应认证**: React Fiber注入 → 标准表单 → 按钮点击 → 预认证 |
| `l1_capture.py` | ✅ | TrafficInterceptor + BFS导航 + SPA卡片探索 |
| `l2_structure.py` | ✅ | **API驱动结构发现**: 从graph-source/careers等API解析Phase/Lesson/Step |
| `l3_classify.py` | ✅ | APIClassifier(6信号) + StepTypeClassifier |
| `l4_schema.py` | ✅ | SchemaGenerator + Redactor + SchemaValidator |
| `explorer.py` | ✅ | 五层流水线主协调器 |
| `__main__.py` | ✅ | CLI入口 |

### 后端

| 文件 | 状态 |
|------|------|
| `backend/models/exploration_session.py` | ✅ ORM模型 |
| `backend/services/explorer_service.py` | ✅ 后台线程 + DB持久化 |
| `backend/api/explorer.py` | ✅ REST API (run/status/cancel/sessions/schema/health) |
| `backend/api/settings.py` | ✅ LLM Key管理 |
| `backend/api/__init__.py` | ✅ 路由注册 |

### 前端

| 文件 | 状态 |
|------|------|
| `frontend/index.html` | ✅ Explorer页面 + 侧边栏 + Schema指示器 |
| `frontend/js/app.js` | ✅ 完整JS (exploreStart/Cancel/ViewSchema/DownloadSchema/UseSchema) |
| `frontend/locales/zh.json, en.json` | ✅ 双语i18n |

---

## 🔄 当前状态

### 已验证成功

- ✅ **React Fiber认证**: 突破 Next.js 自定义认证
- ✅ **API发现**: 5个API端点 (graph-source, careers, digital-teacher, auth/me, events)
- ✅ **Phase发现**: 22个Phase (来自 careers API 的 competency 数据)
- ✅ **端到端流程**: 前端UI → 后端API → 探索器 → Schema生成 → 结果展示
- ✅ **云端部署**: http://124.174.108.70/test/ 可正常使用

### 已知问题 (2026-08-05 最新)

- ✅ **View/Download Schema**: 已修复 — View在页面内嵌显示, Download用fetch+blob下载
- 🔄 **API响应体捕获**: JWT存储在React内存中, 外部requests无法访问。已改用 `page.evaluate(fetch())` 在浏览器内调用API获取响应体
- 🔄 **Phase名称**: 依赖API响应体捕获成功后L2才能解析
- ⚠️ **SPA导航**: BFS对无`<a href>`的SPA较慢(90s+)，已限制depth=2/pages=10

---

## 🔲 待完成

### P0 — 响应体捕获

当前 `page.on("response")` 无法捕获fetch/XHR响应体。使用 `page.route()` + `route.fetch()` 方案:
```python
# l1_capture.py TrafficInterceptor.install()
page.route("**/*", lambda route: ...)
# route.fetch() → 获取完整响应体 → route.fulfill()
```

### P1 — L2结构推断增强

- [ ] Phase名称提取: `_extract_field()` 需要更好的嵌套字段匹配
- [ ] Lesson/Step层次: 当前只发现Phase，需要从graph-source API提取子层次
- [ ] 多API数据融合: graph-source(courses) + careers(competencies) 合并

### P2 — 前端完善

- [ ] View/Download Schema按钮已支持从历史列表传session_id
- [ ] Schema指示器在Dashboard上显示探索状态
- [ ] "Use This Schema"按钮将schema路径写入test_config

### P3 — 通式化

- [ ] 更多API响应格式的自适应匹配
- [ ] LLM辅助结构推断 (Phase 2)
- [ ] 跨平台Schema缓存共享 (Unbrowse思路)

---

## 🔧 调试命令

```bash
# 云端直接运行探索器
ssh root@124.174.108.70
cd /opt/agent_eval
./venv/bin/python3 -c "
from src.platform_probe.explorer import PlatformExplorer
from pathlib import Path
e = PlatformExplorer(headless=True, output_dir=Path('/tmp/test'), verbose=True)
e.explore('http://124.174.108.70/personalized-secure', '111', '123456')
"

# 查看最新探索结果
curl -s http://localhost:8000/api/explorer/sessions?page_size=1 | python3 -m json.tool

# 查看生成的schema
cat /opt/agent_eval/output/platform_probe/explore_*/platform_schema.yaml | head -50

# 重启服务
systemctl restart agent-eval
```
