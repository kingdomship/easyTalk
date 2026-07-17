# easyTalk 项目关键约定

## 目录结构

```
easytalk/
├── app/                    # 应用核心（FastAPI 入口、DB、路由、模型）
│   ├── main.py             # 入口 + lifespan + seed memory + 8个定时任务
│   ├── db.py               # PostgreSQL 连接池 + init_db + migration
│   ├── models.py           # Pydantic 模型 (ChatRequest)
│   ├── config.py           # 路径常量 (MEMORY_DIR 下各文件路径)
│   ├── utils.py            # LLM 客户端 (get_llm/get_llm_model/reset_llm) + 后台线程池
│   ├── llm_config.py       # LLM 配置中心 (12家供应商预设 + load/save)
│   ├── catchup.py          # 启动补漏 (停机期间遗漏的日记/情绪随机游走)
│   ├── cleanup.py          # 数据生命周期清理 (每天03:07, 语义保留式修剪)
│   ├── emotion_params.py   # 27维情感参数权威定义 (default/min/max/jitter)
│   └── routes/             # API 路由（thin layer）
│       ├── __init__.py     # 聚合所有子路由
│       ├── chat.py         # /api/chat + SSE流式 + 核心管线 + 两段式精灵生成
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
│   │   ├── pde.py          # 预测误差驱动 (新增)
│   │   └── state_machine.py # 5行为模式 + 4唤醒态 (SAGE)
│   ├── emotion/            # 情绪系统
│   │   ├── affect.py       # Panksepp六系统情绪评估 + Gross调节 + 效价追踪
│   │   ├── affinity.py     # 10D亲密度追踪 + 表达幅度学习 + 关系里程碑
│   │   ├── attachment.py   # 依恋风格识别 (焦虑/回避/安全, 每30轮)
│   │   └── salience.py     # SNARC显著性 (Surprise/Novelty/Arousal/Reward/Conflict)
│   ├── identity/           # 身份系统
│   │   ├── drift_detector.py # 人设漂移检测 (每30轮)
│   │   ├── guard.py        # 身份守护
│   │   ├── personality.py  # OCEAN + MBTI + 原型人格引擎
│   │   ├── prompt.py       # 模块化提示词 + AI预分析组装 (见提示词系统章节)
│   │   ├── sprite_prompt.py # 两段式精灵生成专用prompt (16×16高分辨率网格)
│   │   ├── sprite_library.py # 精灵库查询/持久化 (新增)
│   │   └── sprites/        # 预生成精灵JSON (11类: animals/weather/food/...) (新增)
│   ├── drive/               # 驱动系统 (新增)
│   │   ├── engine.py       # 动机引擎 (drive values + decay)
│   │   └── prompts.py      # 驱动相关 prompt
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
│       ├── engine.js       # 全局变量、工具函数、表情系统、音频引擎、调试面板、localStorage状态持久化
│       ├── visuals.js      # 星空渲染、流星、记忆星点、像素头像(64x64)、精灵系统(offscreen canvas预渲染)
│       ├── constellation.js # 交互式星图 (Obsidian风格, 力导向图 + 缩放/拖拽 + 触摸手势)
│       ├── ui.js           # 对话框、SSE流、面板、话题气泡、日记模态框、设置面板、主循环
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
│   └── llm_config.json     # LLM 多供应商配置 (api_key/base_url/model)
├── scripts/                # 工具脚本
│   ├── batch_generate_sprites.py  # 批量预生成精灵
│   └── adjust_sprite_scales.py    # 精灵缩放调整
├── Dockerfile              # python:3.10-slim, uvicorn
├── docker-compose.yml      # pgvector/pgvector:pg15 + app, 端口 8000
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

## 定时任务 (8个)

| 任务 | 时间 | 说明 |
|------|------|------|
| 日记生成 | 每天 04:00 | 为昨天生成 AI 日记 |
| 新闻抓取 | 每天 07:00 | 4源并发异步抓取热榜 |
| 空闲思绪 | 每5分钟 | 离线时生成内心独白 |
| 情绪波动 | 每30分钟 | 表达幅度随机游走 |
| 日记种子 | 每小时 | 累积空闲思绪供日记使用 |
| 数据清理 | 每天 03:07 | 语义保留式修剪旧对话数据 (app/cleanup.py) |
| 离线分析 | 每7分钟 | 预测代理离线分析 (predictive_agent.py) |
| System2巩固 | 每23分钟 | 慢速推理结果巩固 (consciousness_loop.py) |

## 提示词系统 (模块化 + AI 预分析)

### 架构

核心提示词拆分为 10 个独立模块，通过 `assemble_prompt()` 按需组装：

```
用户消息
  ↓
_analyze_intent()          AI 快速分类 (~200ms, ~60 tokens)
  ↓                          输出标签: ["emotion","weather","story","object","topic","none"]
  ↓                          失败时自动降级为关键词匹配
assemble_prompt(msg, tags)
  ↓
┌─────────────────────────────────────────────┐
│ 基础模块（始终加载，~970 tokens）              │
│  _MODULE_ROLE        角色 + 情绪调节 + 关系伦理│
│  _MODULE_FACS        27参数手册 + 8基本情绪   │
│  _MODULE_ANIMATION   多帧序列 + 头部动画      │
│  _MODULE_OUTPUT      JSON输出格式             │
├─────────────────────────────────────────────┤
│ 可选模块（AI 按需加载，~1,100 tokens 总计）    │
│  _MODULE_COMPOSITE     8个复合表情示例         │
│  _MODULE_COLOR_FIELDS  氛围光晕 + 5种天气配方   │
│  _MODULE_BACKGROUND    6种话题背景色            │
│  _MODULE_SPRITES       精灵关键词生成           │
│  _MODULE_SCENES        Freytag叙事 + 写作技巧   │
└─────────────────────────────────────────────┘
```

### 调用链

```
_build_context(msg)
  → _analyze_intent(msg)              # chat.py: 轻量LLM分类
  → build_dynamic_system_prompt(msg=msg, intent_tags=tags)  # personality.py
  → assemble_prompt(msg, tags=tags)   # prompt.py: 模块组装
  → 拼接完整 system prompt → 主 LLM 调用
```

### 模块触发条件

| 模块 | AI 标签 | 关键词（降级用） |
|------|---------|-----------------|
| composite | `emotion` | "难过"、"伤心"、"愤怒"... |
| color_fields | `emotion` / `weather` / `topic` | "下雨"、"夕阳"、"火锅"... |
| background | `emotion` / `weather` / `topic` | 同上 + "森林"、"浪漫"... |
| sprites | `object` | "帽子"、"猫"、"咖啡"... |
| scenes | `story` | "讲故事"、"童话"、"寓言"... |

### Token 节省

简单闲聊（"你好"）：~970 tokens vs 完整版 ~2,168 tokens（省 56%）。完整 FACS 手册始终保留，表情质量不受影响。

### 修改提示词

- 修改基础内容：编辑 `prompt.py` 中对应 `_MODULE_*` 字符串
- 修改触发逻辑：编辑 `prompt.py:assemble_prompt()` 或 `_analyze_intent_sync()` 中的 `_INTENT_PROMPT`
- 新增模块：在 `prompt.py` 中定义 `_MODULE_*` 字符串 → 加入 `_BASE_MODULES` 或 `assemble_prompt()` 中的条件分支

## 多段叙事 (Scenes)

用户请求讲故事时，AI 输出多场景分段回复，每段独立表情/色块/背景：

- **触发**: `_is_story_request()` 检测故事关键词 → `max_tokens` 8192 + temperature +0.05
- **结构**: Freytag 金字塔 (开场→发展→高潮→结局)，Show Don't Tell，多感官描写
- **前端**: `scene_done` 事件暂停流，显示"▶ 下一段"按钮，点击后播出缓冲帧
- **流式协议**: `scene_start` (场景切换) → `text` (逐字) → `scene_done` (暂停等待点击)
- **关键文件**: `prompt.py:_MODULE_SCENES`, `chat.py:_is_story_request()`, `ui.js:showStoryContinueBtn()`

## 两段式精灵生成

### 流程

```
主 LLM → sprite_keywords (2-3个中文关键词)
  ↓
_generate_sprites() [asyncio.to_thread]
  ├─ 1) lookup_sprite(keywords) → 检查预建精灵库 (sprites/*.json)
  └─ 2) 库未命中 → sprite_prompt.py LLM 生成 16×16 像素网格
  ↓
persist_sprite() → 存入精灵库供后续复用
  ↓
pixel_sprites SSE 事件 → 前端 offscreen canvas 预渲染 + drawImage
```

### 关键文件

- `services/identity/sprite_prompt.py` — 精灵生成专用 prompt
- `services/identity/sprite_library.py` — `lookup_sprite()` / `persist_sprite()`
- `services/identity/sprites/` — 11 类预生成精灵 (animals/weather/food/objects/...)
- `static/js/visuals.js` — offscreen canvas 预渲染 + `drawImage`

## 驱动系统 (Drive)

新增动机引擎，追踪 AI 的内在驱动状态：

- `services/drive/engine.py` — 驱动值计算、衰减、更新
- `services/drive/prompts.py` — 驱动相关 prompt
- **关键函数**: `get_drive_values()`, `update_drives_on_chat()`, `get_drive_context()`, `get_drive_temp_mod()`
- 影响 temperature、行为模式、token 预算

## 部署

- 使用 `docker-compose.yml` 构建和启动
- PostgreSQL 镜像: `pgvector/pgvector:pg15`（支持向量搜索）
- 服务端口: `8000:8000`
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
| 前端缓存版本 | `?v=N` (index.html) | 每次部署更新以强制刷新 |

## 修改指南

### 调整 AI 性格/表情/氛围
- **基础角色/表情**: 编辑 `services/identity/prompt.py` 中对应 `_MODULE_*` 字符串
- **模块触发**: 编辑 `prompt.py:assemble_prompt()` 或 `_analyze_intent_sync()` 中的 `_INTENT_PROMPT`
- **新增能力模块**: 在 `prompt.py` 中定义 `_MODULE_*` → 加入 `assemble_prompt()` 条件分支
- **时段语境**: 编辑 `prompt.py:build_time_context()`
- **人格参数**: 编辑 `personality.py` 中的 OCEAN/MBTI/原型配置

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
- 前端调试面板: 三击页面左下角 16×16px 区域
- LLM 错误: 自动分类并输出到日志+调试面板

## 并发安全模型

### 文件锁
- `archive_lock` (`threading.Lock`, `app/config.py`) — 保护 `conversation_archive.jsonl` 的并发读写
  - 16 处保护点: `chat.py` (4)、`condense.py` (1)、`narrative.py` (2)、`crystallization.py` (4)、`attachment.py` (2)、`guard.py` (2)、`cleanup.py` (1)
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

## 前端状态持久化

- `saveVisualState()` (`engine.js`) — 每2秒保存表情参数、背景颜色、颜色场、对话框到 `localStorage.easytalk_visual`
- `loadVisualState()` — 读取并恢复，5分钟过期自动清除
- 刷新后恢复对话框 DOM（`ui.js` init 段）

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
