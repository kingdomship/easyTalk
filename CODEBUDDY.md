# CODEBUDDY.md

> 为切换 Agent 时的无缝交接而生成。任何接手此项目的 Claude 实例应首先阅读本文。

## 项目概述

**emoji-chat** 是一个 LLM 驱动的像素头像聊天伴侣。用户通过文本与住在数字星空中的 AI 女性角色对话，AI 用 10 维连续参数实时驱动像素头像的面部表情，配合星空粒子视效、记忆系统和关系追踪。

- **技术栈**: Python/FastAPI + PostgreSQL(pgvector) + Canvas JS
- **LLM**: DeepSeek Chat API（OpenAI 兼容协议）
- **部署**: Docker Compose（双容器：app + postgres）
- **代码规模**: ~4,000 行（Python 1,640 + JS 2,184 + 配置 79）

## 快速开始

```bash
cp .env.example .env          # 填入 DEEPSEEK_API_KEY
docker-compose up -d          # 启动 → localhost:9010
```

首次部署需确保宿主机 `/home/xuwl/app/easyChat/memory/` 目录存在且包含 `user_persona.md` 和 `user_profile.md`。

## 目录结构与职责

```
emoji-chat/
├── app/                          # Web 层（不要在这里加业务逻辑）
│   ├── main.py                   # FastAPI app, lifespan, seed memory, 完整性检查
│   ├── db.py                     # PostgreSQL 连接池, init_db (建表+migration)
│   ├── models.py                 # Pydantic 请求模型 (ChatRequest)
│   └── routes/                   # API 路由（thin layer: 解析请求→调用service→返回）
│       ├── __init__.py           # 聚合所有子路由
│       ├── chat.py               # /api/chat, /api/chat/stream, 工具函数
│       ├── diary.py              # /api/diary/*
│       ├── emotions.py           # /api/emotions/*
│       ├── memory.py             # /api/memory/*, /api/affinity, /api/mood/*
│       └── news.py              # /api/news/*
│
├── services/                     # 业务逻辑（可独立测试）
│   ├── prompt.py                 # SYSTEM_PROMPT + 昼夜节律上下文
│   ├── memory_loader.py          # 从 /app/memory/ 加载 persona/profile/summary
│   ├── memory_search.py          # pgvector 语义搜索（LLM标签→哈希向量→HNSW索引）
│   ├── condense.py               # 对话摘要压缩（CONDENSE_PROMPT + standalone CLI）
│   ├── diary.py                  # 日记 LLM 生成（每天凌晨4点定时）
│   ├── news.py                   # 4源并发异步新闻抓取（B站/GitHub/百度/Tophub）
│   └── affinity.py               # 6D亲密度追踪 + 表达幅度自适应学习
│
├── static/                       # 前端（零构建工具，直接加载）
│   ├── index.html                # HTML 骨架（48行）
│   ├── style.css                 # 所有样式（205行）
│   └── js/
│       ├── globals.d.ts          # TypeScript 类型声明（232行，VS Code 原生支持）
│       ├── engine.js             # 全局状态, 表情系统, 音频, 氛围, 调试面板
│       ├── visuals.js            # 星空渲染, 流星, 记忆星点, 头像绘制, 表情动画
│       └── ui.js                 # 对话框, SSE流式, 面板, 主循环, 事件处理
│
├── memory/                       # 持久化记忆数据（volume 挂载到 /app/memory）
│   ├── user_persona.md           # AI 人设（用户编写，启动时加载）
│   ├── user_profile.md           # 用户档案（用户编写）
│   ├── conversation_archive.jsonl # 对话归档（每轮追加）
│   └── conversation_summary.md   # 自动摘要（每50轮由 _maybe_condense 生成）
│
├── Dockerfile                    # python:3.10-slim, COPY app/services/static, uvicorn
├── docker-compose.yml            # pgvector/pgvector:pg15 + app, 端口 9010
├── requirements.txt              # fastapi, uvicorn, psycopg2-binary, openai, httpx, apscheduler
├── tsconfig.json                 # TypeScript 类型检查配置（checkJs, noEmit）
├── .env.example                  # DEEPSEEK_API_KEY + DB_PASSWORD 模板
├── .gitignore                    # __pycache__/, .claude/, .env
└── CLAUDE.md                     # 项目约定速查
```

## 关键架构决策

### 导入规范
- `app/` → 核心层，不依赖 `services/`
- `services/` → 依赖 `app.db`，不依赖 `app.routes`
- 跨模块始终使用完整路径：`from app.db import ...`, `from services.xxx import ...`

### 数据流
```
用户消息 → routes/chat.py
  ├── _build_context() 组装 system prompt:
  │     ├── services/prompt.py → SYSTEM_PROMPT + 昼夜节律
  │     ├── services/memory_loader.py → persona + profile + summary
  │     ├── services/affinity.py → 亲密度上下文
  │     ├── services/news.py → 热榜话题
  │     └── services/memory_search.py → 语义检索相关历史
  ├── _call_llm() → DeepSeek API（带错误分类 fallback）
  ├── _jitter_frame() → ±2-3% 随机微动
  ├── scale_emotion_params() → 表达幅度缩放
  └── 返回 {emotions, reply} → 前端渲染
      ├── 存储到 chat_history + emotion_cache
      ├── 归档到 conversation_archive.jsonl
      ├── 更新亲密度 + 表达幅度
      └── 后台: index_turn(pgvector) + _maybe_condense(每50轮)
```

### 表情系统参数（10维连续值）
| 参数 | 范围 | 含义 |
|------|------|------|
| eye_curve | -1 ~ 1 | 眼角弧度（悲伤→开心） |
| eye_open | 0 ~ 1 | 眼睛开合（闭眼→瞪大） |
| eye_pupil | -1 ~ 1 | 瞳孔偏移（左看→右看） |
| mouth_curve | -1 ~ 1 | 嘴角弧度（悲伤→微笑） |
| mouth_open | 0 ~ 1 | 嘴张合（紧闭→大张） |
| mouth_width | 0.3 ~ 1 | 嘴宽度（抿嘴→咧嘴） |
| sparkle | 0 ~ 1 | 眼神光泽（暗淡→闪亮） |
| brow_angle | -1 ~ 1 | 眉角度（V字怒眉→八字眉） |
| brow_height | 0 ~ 1 | 眉高度（低压→高抬） |
| brow_asym | 0 ~ 1 | 眉不对称度 |

### 前端加载顺序（单向依赖，不可更改）
```
1. engine.js   → 定义所有全局变量/函数（curParams, tgtParams, sequence, lerp 等）
2. visuals.js  → 使用 engine 的全局变量，定义绘制函数（drawStarfield, drawFaceOnCanvas 等）
3. ui.js       → 使用 engine + visuals，定义交互+主循环
```

### TypeScript 类型检查
- `static/js/globals.d.ts` 声明所有全局类型
- 每个 `.js` 文件顶部有 `// @ts-check`
- VS Code 开箱即用：自动补全、类型检查、跳转定义
- 零构建工具、零运行时影响
- CI 检查：`npx tsc --noEmit`（需要 `npm install typescript`）

## 记忆系统架构（3层）

```
Layer 1: 近期上下文（10轮原文） → 直接注入 messages[]
Layer 2: 语义检索（pgvector）    → LLM提取标签→哈希256维向量→HNSW余弦搜索
Layer 3: 长期摘要（每50轮）     → auto-condense → conversation_summary.md
```

- **标签提取**: `services/memory_search.py:_llm_extract_tags()` 调用 DeepSeek 提取 5-10 个中文语义标签
- **向量化**: 每个标签 MD5 哈希 → 映射到 256 维向量的 3 个位置 → L2 归一化
- **存储**: `memory_vectors` 表，`halfvec(256)` 类型，HNSW 索引（`halfvec_cosine_ops`）
- **检索**: 当前消息提取标签→哈希→余弦相似度>0.3→取 top-5

## 亲密度系统（7D）

| 维度 | 默认值 | 说明 |
|------|--------|------|
| warmth | 0.5 | 温暖度 |
| trust | 0.4 | 信任度 |
| intimacy | 0.2 | 亲密度 |
| curiosity | 0.6 | 好奇心 |
| patience | 0.7 | 耐心度 |
| tension | 0.1 | 紧张度 |
| expression_amplitude | 1.0 | 表达幅度（0.5含蓄~1.5夸张） |

- **更新**: 基于关键词启发的 EMA 平滑（alpha=0.05）
- **表达学习**: `adjust_expression_amplitude()` 根据用户回复长度/情绪词调整幅度，缓慢趋近 1.0

## 定时任务

| 任务 | 时间 | 说明 |
|------|------|------|
| 日记生成 | 每天 04:00 | 为昨天生成 AI 日记 |
| 新闻抓取 | 每天 07:00 | 4源并发异步抓取热榜 |

## 关键路径常量

| 常量 | 值 | 位置 |
|------|-----|------|
| 记忆宿主路径 | `/home/xuwl/app/easyChat/memory` | docker-compose.yml |
| 容器挂载点 | `/app/memory` | Dockerfile volume |
| 种子数据 | `/app/memory_seed/` | Dockerfile COPY |
| 归档文件 | `/app/memory/conversation_archive.jsonl` | routes/chat.py:_ARCHIVE_PATH |
| 摘要文件 | `/app/memory/conversation_summary.md` | routes/chat.py:_maybe_condense |
| 摘要触发阈值 | 每 50 轮 | routes/chat.py:_CONDENSE_EVERY |
| 对话上下文窗口 | 最近 20 条（10轮） | routes/chat.py:_build_context |
| pgvector 维度 | 256, halfvec, HNSW | db.py + memory_search.py |
| SSE 流式间隔 | 每 2 字符，30ms 间隔 | routes/chat.py:chat_stream |

## 修改指南

### 调整 AI 性格
编辑 `services/prompt.py` 中的 `SYSTEM_PROMPT` 或 `build_time_context()`

### 调整 AI 人设
编辑 `/home/xuwl/app/easyChat/memory/user_persona.md`，重启容器生效

### 添加新 API 端点
1. 在 `app/routes/` 下新建文件（参考已有文件的模式）
2. 在 `app/routes/__init__.py` 中注册
3. 业务逻辑放 `services/`

### 添加新前端功能
1. 按功能归属选择 engine.js（逻辑/状态）、visuals.js（渲染）、ui.js（交互）
2. 在 `globals.d.ts` 中声明新类型/函数

### 修改数据库表
编辑 `app/db.py:init_db()`，在函数末尾追加 migration 逻辑

### 调试
- 后端日志: `docker logs emoji-chat-app-1`
- 前端调试面板: 三击页面左下角 8×8px 区域
- LLM 错误: 自动分类并输出到日志+调试面板

## 常见问题

**Q: 新部署后 AI 没有个性？**
A: 确认 `/home/xuwl/app/easyChat/memory/user_persona.md` 和 `user_profile.md` 存在。启动时会自动从种子数据复制。

**Q: pgvector 扩展加载失败？**
A: 确认 docker-compose.yml 使用 `pgvector/pgvector:pg15` 镜像，不是普通 `postgres:15`。

**Q: 容器内存/磁盘占用大？**
A: `chat_history` 表会无限增长。可考虑定期清理旧记录或设置 retention policy。

**Q: 如何导出对话记录？**
A: 对话归档在 `/home/xuwl/app/easyChat/memory/conversation_archive.jsonl`，每行一条 JSON。
