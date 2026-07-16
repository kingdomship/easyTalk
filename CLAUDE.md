# easyTalk 项目关键约定

## 目录结构

```
easytalk/
├── app/                    # 应用核心（FastAPI 入口、DB、路由、模型）
│   ├── main.py             # 入口 + lifespan + seed memory + 5个定时任务
│   ├── db.py               # PostgreSQL 连接池 + init_db + migration
│   ├── models.py           # Pydantic 模型 (ChatRequest)
│   ├── config.py           # 路径常量 (MEMORY_DIR 下各文件路径)
│   ├── utils.py            # LLM 客户端 (get_llm/get_llm_model/reset_llm) + 后台线程池
│   ├── llm_config.py       # LLM 配置中心 (12家供应商预设 + load/save)
│   └── routes/             # API 路由（thin layer）
│       ├── __init__.py     # 聚合所有子路由
│       ├── chat.py         # /api/chat + SSE流式 + 核心管线函数
│       ├── config.py       # /api/config/apikey (自定义 API Key 管理)
│       ├── diary.py        # /api/diary/*
│       ├── emotions.py     # /api/emotions/*
│       ├── memory.py       # /api/memory/* + affinity + mood + idle + missing-you
│       └── news.py         # /api/news/*
├── services/               # 业务逻辑 (按领域分6个子目录)
│   ├── cognition/          # 认知系统
│   │   ├── dual_system.py  # 双系统思维 (快速直觉 + 慢速推理)
│   │   ├── prediction.py   # 预测误差学习 (Active Inference)
│   │   ├── predictive_agent.py # 预测代理
│   │   └── state_machine.py # 5行为模式 + 4唤醒态 (SAGE)
│   ├── emotion/            # 情绪系统
│   │   ├── affect.py       # Panksepp六系统情绪评估 + Gross调节 + 效价追踪
│   │   ├── affinity.py     # 10D亲密度追踪 + 表达幅度学习 + 关系里程碑
│   │   ├── attachment.py   # 依恋风格识别 (焦虑/回避/安全, 每30轮)
│   │   └── salience.py     # SNARC显著性 (Surprise/Novelty/Arousal/Reward/Conflict)
│   ├── identity/           # 身份系统
│   │   ├── drift_detector.py # 人设漂移检测 (每30轮)
│   │   ├── guard.py        # 身份守护
│   │   ├── personality.py  # 人格配置
│   │   └── prompt.py       # SYSTEM_PROMPT + 昼夜节律上下文 + temperature
│   ├── info/               # 信息获取
│   │   └── news.py         # 多源热榜抓取 (B站/GitHub/Tophub/百度, 4源异步)
│   ├── memory/             # 记忆系统
│   │   ├── clustering.py   # 记忆聚类
│   │   ├── condense.py     # 对话摘要压缩 (每50轮 + standalone CLI)
│   │   ├── crystallization.py # 模式结晶 + Ebbinghaus遗忘曲线
│   │   ├── knowledge_graph.py # 知识图谱
│   │   ├── loader.py       # 记忆文件加载 (persona/profile/summary)
│   │   ├── narrative.py    # 叙事蒸馏 (Situation→Episode)
│   │   ├── reranker.py     # 记忆重排序
│   │   └── search.py       # pgvector语义搜索 (LLM标签→MD5哈希→256维HNSW)
│   └── reflection/         # 反思系统
│       ├── consciousness_loop.py # 背景意识循环 (空闲独白 + 情绪波动 + 日记种子)
│       └── diary.py        # AI日记生成 (每天04:00)
├── static/                 # 前端 (零构建)
│   ├── index.html          # HTML 骨架
│   ├── style.css           # 所有样式
│   └── js/
│       ├── engine.js       # 全局变量、工具函数、表情系统、音频引擎、调试面板
│       ├── visuals.js      # 星空渲染、流星、记忆星点、像素头像绘制
│       ├── constellation.js # 交互式星图 (Obsidian风格, 力导向图 + 缩放/拖拽)
│       ├── ui.js           # 对话框、SSE流、面板、主循环、事件处理
│       └── globals.d.ts    # TypeScript 类型声明
├── memory/                 # 记忆数据（volume 挂载到 /app/memory）
│   ├── user_persona.md     # AI人设
│   ├── user_profile.md     # 用户档案
│   ├── conversation_archive.jsonl  # 对话归档
│   ├── conversation_summary.md     # 对话摘要 (自动生成)
│   ├── crystals.jsonl      # 结晶记忆
│   ├── situations.jsonl    # 叙事情景
│   ├── episodes.jsonl      # 叙事章节
│   ├── milestones.jsonl    # 关系里程碑
│   ├── attachment_style.json # 依恋风格
│   ├── api_key.txt         # 自定义 API Key (旧格式，已迁移至 llm_config.json)
│   └── llm_config.json     # LLM 多供应商配置 (api_key/base_url/model)
├── Dockerfile              # python:3.10-slim, uvicorn
├── docker-compose.yml      # pgvector/pgvector:pg15 + app, 端口 9010
├── requirements.txt        # fastapi, uvicorn, psycopg2-binary, openai, httpx, apscheduler
├── tsconfig.json           # TypeScript 类型检查 (checkJs, noEmit)
├── .env.example            # DEEPSEEK_API_KEY + DB_PASSWORD
└── .gitignore
```

## 导入规范

- `app/` 是核心层，不依赖 `services/`
- `services/` 依赖 `app.db`，不依赖 `app.routes`
- 跨模块导入使用完整路径：`from app.db import ...`、`from services.emotion.xxx import ...`

## 数据持久化

- **记忆文件宿主路径**: `/home/xuwl/app/easyChat/memory`
- 容器内挂载点: `/app/memory`
- 该目录存放: `user_persona.md`、`user_profile.md`、`conversation_archive.jsonl`、`conversation_summary.md` 等
- 更新容器时使用此宿主路径，避免记忆数据丢失
- PostgreSQL 数据通过 named volume `pgdata` 持久化

## 记忆系统架构 (四层)

1. **即时上下文**: 最近4轮对话直接注入 system prompt
2. **语义检索**: `services/memory/search.py` — LLM提取标签 → MD5哈希256维向量 → pgvector HNSW余弦搜索
3. **叙事蒸馏**: `services/memory/narrative.py` — Instant → Situation (每10轮) → Episode (每5个Situation) → 注入context
4. **模式结晶**: `services/memory/crystallization.py` — 重复话题→LLM蒸馏→持久记忆 + Ebbinghaus遗忘曲线衰减

## 亲密度系统 (10D)

| 维度 | 默认值 | 说明 |
|------|--------|------|
| warmth | 0.5 | 温暖度 |
| trust | 0.4 | 信任度 |
| intimacy | 0.2 | 亲密度 |
| curiosity | 0.6 | 好奇心 |
| patience | 0.7 | 耐心度 |
| tension | 0.1 | 紧张度 |
| expression_amplitude | 1.0 | 表达幅度 (0.5含蓄~1.5夸张) |
| user_autonomy | 0.5 | 用户自主性 (SDT) |
| user_competence | 0.5 | 用户胜任感 (SDT) |
| user_relatedness | 0.3 | 用户关联感 (SDT) |

- **更新**: 基于关键词启发的 EMA 平滑 (alpha=0.05)
- **表达学习**: `adjust_expression_amplitude()` 根据用户回复长度/情绪词调整幅度，缓慢趋近 1.0
- **里程碑**: 5个关系阈值 (温暖默契/信任分享/深刻联结/无话不谈/心之桥梁)

## 定时任务 (5个)

| 任务 | 时间 | 说明 |
|------|------|------|
| 日记生成 | 每天 04:00 | 为昨天生成 AI 日记 |
| 新闻抓取 | 每天 07:00 | 4源并发异步抓取热榜 |
| 空闲思绪 | 每5分钟 | 离线时生成内心独白 |
| 情绪波动 | 每30分钟 | 表达幅度随机游走 |
| 日记种子 | 每小时 | 累积空闲思绪供日记使用 |

## 部署

- 使用 `docker-compose.yml` 构建和启动
- PostgreSQL 镜像: `pgvector/pgvector:pg15`（支持向量搜索）
- 服务端口: `9010:8000`
- 需要环境变量 `DEEPSEEK_API_KEY`、`DB_PASSWORD`（可选，默认 123456）

## 关键路径常量

| 常量 | 值 | 位置 |
|------|-----|------|
| 记忆宿主路径 | `/home/xuwl/app/easyChat/memory` | docker-compose.yml |
| 容器挂载点 | `/app/memory` | Dockerfile |
| 种子数据 | `/app/memory_seed/` | Dockerfile COPY |
| 归档文件 | `conversation_archive.jsonl` | routes/chat.py |
| 摘要触发阈值 | 每 50 轮 | routes/chat.py |
| 对话上下文窗口 | 最近 4 轮 | routes/chat.py:_build_context |
| pgvector 维度 | 256, halfvec, HNSW | db.py + services/memory/search.py |
| LLM 配置 | `memory/llm_config.json` | llm_config.py |
| SSE 流式间隔 | 每 2 字符，30ms | routes/chat.py:chat_stream |

## 修改指南

### 调整 AI 性格
编辑 `services/identity/prompt.py` 中的 `SYSTEM_PROMPT` 或 `build_time_context()`

### 调整 AI 人设
编辑 `/home/xuwl/app/easyChat/memory/user_persona.md`，重启容器生效

### 添加新 API 端点
1. 在 `app/routes/` 下新建文件（参考已有文件的模式）
2. 在 `app/routes/__init__.py` 中注册
3. 业务逻辑放 `services/`

### 添加新前端功能
1. 按功能归属选择 engine.js（逻辑/状态）、visuals.js（渲染）、constellation.js（星图）、ui.js（交互）
2. 在 `globals.d.ts` 中声明新类型/函数

### 修改数据库表
编辑 `app/db.py:init_db()`，在函数末尾追加 migration 逻辑

### 调试
- 后端日志: `docker compose logs -f app`
- 前端调试面板: 三击页面左下角 8×8px 区域
- LLM 错误: 自动分类并输出到日志+调试面板

## 并发安全模型

### 文件锁
- `archive_lock` (`threading.Lock`, `app/config.py`) — 保护 `conversation_archive.jsonl` 的并发读写
  - 15 处保护点: `chat.py` (4)、`condense.py` (1)、`narrative.py` (2)、`crystallization.py` (1)、`attachment.py` (2)、`guard.py` (2)、`cleanup.py` (1)
  - 使用 `with archive_lock:` 上下文管理器
- `_crystal_lock` (`threading.RLock`, `crystallization.py`) — 保护 `crystals.jsonl` 读写
  - **注意**: 使用 `RLock`（可重入锁），因为 `maybe_crystallize()` 和 `reinforce_crystal()` 获取锁后会调用内部函数（`_save_crystals()` 等），内部函数也会获取同一把锁
- `_situation_lock` / `_episode_lock` (`threading.Lock`, `narrative.py`) — 非阻塞守卫，防止叙事检测并发运行
- `_guard_lock` (`threading.Lock`, `guard.py`) — 非阻塞守卫，防止身份守护并发运行

### 非阻塞守卫模式
后台任务使用 `lock.acquire(blocking=False)` 模式，若已有实例在运行则静默跳过：
```python
if not _crystal_lock.acquire(blocking=False):
    return
try:
    # ... work ...
finally:
    _crystal_lock.release()
```

### 计数器更新时机
所有 `_last_check_count` / `_last_situation_check` / `_last_episode_check` 必须在 LLM 调用和文件写入**成功后**才更新，防止失败后数据永久跳过。

## Async/Thread 模式

- **FastAPI `async def` 端点不能直接调用同步阻塞函数**（会冻结事件循环）
- `_think()`、`_call_llm()` 等 LLM API 调用必须用 `await asyncio.to_thread()` 包裹
- `chat()` 和 `chat_stream()` 端点均已适配此模式
- 文件 I/O 和数据库查询同步执行（轻量操作，不会阻塞）

## 前端安全规范

- **`innerHTML` 赋值前必须对用户/LLM 内容调用 `escapeHtml()`**
  - `escapeHtml()` 在 `engine.js` 中定义，转义 `&` `<` `>` `"` `'`
- 日记搜索高亮：先 `escapeHtml()` 再正则替换插入 `<mark>` 标签
- 错误消息 `e.message` 拼接 HTML 时也必须转义
- `console.error` 重写中 `JSON.stringify` 必须包裹 `try/catch`（循环引用会抛异常）
- SSE 流解析：`decoder.decode(value, {stream: true})` 后按 `\n` 分割，不完整的 JSON 行存回 buffer 等待下个 chunk

## 部署 (阿里云 ACR)

```bash
# 构建并推送镜像
docker build -t easytalk-app:latest .
docker tag easytalk-app:latest crpi-1gdx2774xijb53l6.cn-chengdu.personal.cr.aliyuncs.com/xuwl03/easytalk:latest
docker push crpi-1gdx2774xijb53l6.cn-chengdu.personal.cr.aliyuncs.com/xuwl03/easytalk:latest
```
