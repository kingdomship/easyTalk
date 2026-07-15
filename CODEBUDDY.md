# CODEBUDDY.md

> 为切换 Agent 时的无缝交接而生成。任何接手此项目的 Claude 实例应首先阅读本文。

## 项目概述

**easyTalk** 是一个 LLM 驱动的像素头像聊天伴侣。用户通过文本与住在数字星空中的 AI 女性角色对话，AI 用 15 维连续参数实时驱动像素头像的面部表情，配合星空粒子视效、四层记忆系统和关系追踪。

- **技术栈**: Python/FastAPI + PostgreSQL(pgvector) + Canvas JS
- **LLM**: DeepSeek Chat API（OpenAI 兼容协议）
- **部署**: Docker Compose（双容器：app + postgres）
- **代码规模**: ~5,500 行（Python ~2,500 + JS ~2,800 + 配置 ~200）

## 快速开始

```bash
cp .env.example .env          # 填入 DEEPSEEK_API_KEY
docker-compose up -d          # 启动 → localhost:9010
```

首次部署需确保宿主机 `/home/xuwl/app/easyChat/memory/` 目录存在且包含 `user_persona.md` 和 `user_profile.md`（容器启动时会自动从种子数据复制）。

## 目录结构与职责

```
easytalk/
├── app/                          # Web 层（不要在这里加业务逻辑）
│   ├── main.py                   # FastAPI app, lifespan, seed memory, 完整性检查, 5个定时任务
│   ├── db.py                     # PostgreSQL 连接池, init_db (建表+migration)
│   ├── models.py                 # Pydantic 请求模型 (ChatRequest)
│   └── routes/                   # API 路由（thin layer: 解析请求→调用service→返回）
│       ├── __init__.py           # 聚合所有子路由
│       ├── chat.py               # /api/chat, /api/chat/stream, 工具函数
│       ├── diary.py              # /api/diary/*
│       ├── emotions.py           # /api/emotions/*
│       ├── memory.py             # /api/memory/*, /api/affinity, /api/mood/*, idle, missing-you
│       └── news.py              # /api/news/*
│
├── services/                     # 业务逻辑（15个模块，可独立测试）
│   ├── prompt.py                 # SYSTEM_PROMPT + 昼夜节律上下文 + temperature调制
│   ├── memory_loader.py          # 从 /app/memory/ 加载 persona/profile/summary
│   ├── memory_search.py          # pgvector 语义搜索（LLM标签→MD5哈希→256维HNSW索引）
│   ├── condense.py               # 对话摘要压缩（CONDENSE_PROMPT + standalone CLI）
│   ├── diary.py                  # 日记 LLM 生成（每天凌晨4点定时）
│   ├── news.py                   # 4源并发异步新闻抓取（B站/GitHub/百度/Tophub）
│   ├── affinity.py               # 10D亲密度追踪 + 表达幅度自适应学习 + 关系里程碑
│   ├── affect.py                 # Panksepp六系统情绪评估 + Gross调节策略 + 效价追踪
│   ├── salience.py               # SNARC显著性 (Surprise/Novelty/Arousal/Reward/Conflict)
│   ├── state_machine.py          # 5行为模式(CHAT/DEEP/COMFORT/EXPLORE/PLAY) + 4唤醒态
│   ├── identity_guard.py         # 人设漂移检测 (每30轮, LLM检查→修正注入)
│   ├── crystallization.py        # 模式结晶 (重复话题→持久记忆 + Ebbinghaus衰减)
│   ├── narrative.py              # 叙事蒸馏 (Situation每10轮→Episode每5个Situation)
│   ├── prediction.py             # 预测误差学习 (Active Inference, 后台线程)
│   ├── attachment.py             # 依恋风格识别 (焦虑/回避/安全, 每30轮LLM分析)
│   └── consciousness_loop.py     # 背景意识循环 (空闲独白每5min + 情绪波动每30min + 日记种子每小时)
│
├── static/                       # 前端（零构建工具，直接加载）
│   ├── index.html                # HTML 骨架（49行）
│   ├── style.css                 # 所有样式（249行）
│   └── js/
│       ├── globals.d.ts          # TypeScript 类型声明（232行，VS Code 原生支持）
│       ├── engine.js             # 全局状态, 15参数表情系统, 音频, 氛围, 调试面板 (430行)
│       ├── visuals.js            # 星空渲染, 流星, 记忆星点, 头像绘制, 表情动画 (704行)
│       └── ui.js                 # 对话框, SSE流式, 面板, 主循环, 事件处理 (648行)
│
├── memory/                       # 持久化记忆数据（volume 挂载到 /app/memory）
│   ├── user_persona.md           # AI 人设（用户编写，启动时加载，每30轮LLM反思更新）
│   ├── user_profile.md           # 用户档案（用户编写，每20轮LLM反思更新）
│   ├── conversation_archive.jsonl # 对话归档（每轮追加）
│   ├── conversation_summary.md   # 自动摘要（每50轮由 _maybe_condense 生成）
│   ├── crystals.jsonl            # 结晶记忆（重复话题蒸馏，持久化）
│   ├── situations.jsonl          # 叙事情景（每10轮检测话题边界）
│   ├── episodes.jsonl            # 叙事章节（每5个情景蒸馏为情节）
│   ├── milestones.jsonl          # 关系里程碑（阈值跨越事件）
│   ├── attachment_style.json     # 依恋风格分析结果
│   ├── drift_log.jsonl           # 人设漂移检查日志
│   ├── prediction.json           # 当前预测快照
│   ├── valence_prev.json         # 效价追踪前一状态
│   └── salience_prev.json        # 显著性前一消息
│
├── Dockerfile                    # python:3.10-slim, COPY app/services/static, uvicorn
├── docker-compose.yml            # pgvector/pgvector:pg15 + app, 端口 9010
├── requirements.txt              # fastapi, uvicorn, psycopg2-binary, openai, httpx, apscheduler
├── tsconfig.json                 # TypeScript 类型检查配置（checkJs, noEmit, ES2020）
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
  │     ├── services/crystallization.py → 活跃结晶记忆 (Ebbinghaus衰减过滤)
  │     ├── services/narrative.py → 最近3个情景 + 最近2个情节
  │     ├── services/memory_search.py → pgvector语义检索 top-5
  │     ├── services/affinity.py → 10D亲密度上下文
  │     ├── services/affect.py → Panksepp情绪 + Gross调节策略 + 效价追踪
  │     ├── services/salience.py → SNARC显著性信号
  │     ├── services/attachment.py → 依恋风格建议
  │     ├── services/state_machine.py → 行为模式 + 唤醒态
  │     ├── services/identity_guard.py → 人设漂移修正提醒
  │     └── services/news.py → 今天的热门话题
  ├── _think() → 深度问题的LLM预分析 (不向用户展示)
  ├── _call_llm() → DeepSeek API（temperature=节律+模式+唤醒调制, 带错误分类fallback）
  ├── _jitter_frame() → ±2-3% 随机微动
  ├── scale_emotion_params() → 表达幅度缩放
  └── 返回 {emotions, reply} → 前端渲染
      ├── 存储到 chat_history + emotion_cache
      ├── 归档到 conversation_archive.jsonl
      ├── 更新亲密度 + 情绪 + 显著性 + 表达幅度
      └── 后台线程: pgvector索引 + 摘要 + 结晶 + 情景检测 +
                情节蒸馏 + 人设检查 + 依恋分析 + 预测生成 + 记忆文件更新
```

### 表情系统参数（15维连续值）
| 参数 | 范围 | 含义 |
|------|------|------|
| eye_curve | -1 ~ 1 | 眼角弧度（悲伤→开心） |
| eye_open | 0 ~ 1 | 眼睛开合（闭眼→瞪大） |
| eye_pupil | -1 ~ 1 | 瞳孔偏移（左看→右看） |
| eye_wink | -1 ~ 1 | 眨眼（左眼→右眼） |
| mouth_curve | -1 ~ 1 | 嘴角弧度（悲伤→微笑） |
| mouth_open | 0 ~ 1 | 嘴张合（紧闭→大张） |
| mouth_width | 0.3 ~ 1 | 嘴宽度（抿嘴→咧嘴） |
| mouth_asym | -1 ~ 1 | 嘴不对称（冷笑→歪嘴坏笑） |
| sparkle | 0 ~ 1 | 眼神光泽（暗淡→闪亮） |
| brow_angle | -1 ~ 1 | 眉角度（V字怒眉→八字眉） |
| brow_height | 0 ~ 1 | 眉高度（低压→高抬） |
| brow_asym | 0 ~ 1 | 眉不对称度 |
| blush | 0 ~ 1 | 脸红（无→通红） |
| head_tilt | -1 ~ 1 | 歪头（左→右） |
| tear | 0 ~ 1 | 泪光（无→泪珠） |

支持多帧表情序列（如困惑→惊喜、难过→振作），每帧含独立的 duration_ms。

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

## 记忆系统架构（4层）

```
Layer 1: 即时上下文（4轮原文）      → 直接注入 messages[]
Layer 2: 语义检索（pgvector HNSW）   → LLM提取标签→MD5哈希256维向量→余弦搜索top-5
Layer 3: 叙事蒸馏（Situation→Episode） → 每10轮检测情景, 每5个情景蒸馏为情节
Layer 4: 模式结晶（Ebbinghaus衰减）   → 重复话题→LLM蒸馏→持久记忆, 衰减过滤活跃/休眠
```

- **标签提取**: `services/memory_search.py:_llm_extract_tags()` 调用 DeepSeek 提取 5-10 个中文语义标签
- **向量化**: 每个标签 MD5 哈希 → 映射到 256 维向量的 3 个位置 → L2 归一化
- **存储**: `memory_vectors` 表，`halfvec(256)` 类型，HNSW 索引（`halfvec_cosine_ops`）
- **检索**: 当前消息提取标签→哈希→余弦相似度>0.3→取 top-5

## 亲密度系统（10D）

| 维度 | 默认值 | 说明 |
|------|--------|------|
| warmth | 0.5 | 温暖度 |
| trust | 0.4 | 信任度 |
| intimacy | 0.2 | 亲密度 |
| curiosity | 0.6 | 好奇心 |
| patience | 0.7 | 耐心度 |
| tension | 0.1 | 紧张度 |
| expression_amplitude | 1.0 | 表达幅度（0.5含蓄~1.5夸张） |
| user_autonomy | 0.5 | 用户自主性（SDT） |
| user_competence | 0.5 | 用户胜任感（SDT） |
| user_relatedness | 0.3 | 用户关联感（SDT） |

- **更新**: 基于关键词启发的 EMA 平滑（alpha=0.05）
- **自然衰减**: tension(-0.005), patience(-0.002), SDT维度各(-0.001~-0.002)
- **表达学习**: `adjust_expression_amplitude()` 根据用户回复长度/情绪词调整幅度，缓慢趋近 1.0
- **里程碑**: 5个关系阈值（warmth=0.6温暖默契, intimacy=0.3信任分享, intimacy=0.5深刻联结, trust=0.7无话不谈, relatedness=0.5心之桥梁），每个仅触发一次

## 定时任务（5个）

| 任务 | 时间 | 说明 |
|------|------|------|
| 日记生成 | 每天 04:00 | 为昨天生成 AI 日记（200-400字，含mood_emoji） |
| 新闻抓取 | 每天 07:00 | 4源并发异步抓取热榜（B站/GitHub/百度/Tophub） |
| 空闲思绪 | 每5分钟 | 用户离线>3分钟时，LLM生成20-40字内心独白 |
| 情绪波动 | 每30分钟 | 表达幅度随机游走±0.03，趋近1.0 |
| 日记种子 | 每小时 | 累积空闲思绪供日记使用 |

## 关键路径常量

| 常量 | 值 | 位置 |
|------|-----|------|
| 记忆宿主路径 | `/home/xuwl/app/easyChat/memory` | docker-compose.yml |
| 容器挂载点 | `/app/memory` | Dockerfile |
| 种子数据 | `/app/memory_seed/` | Dockerfile COPY |
| 归档文件 | `/app/memory/conversation_archive.jsonl` | routes/chat.py:_ARCHIVE_PATH |
| 摘要文件 | `/app/memory/conversation_summary.md` | routes/chat.py:_maybe_condense |
| 摘要触发阈值 | 每 50 轮 | routes/chat.py:_CONDENSE_EVERY |
| 用户档案更新 | 每 20 轮 | routes/chat.py:_PROFILE_UPDATE_EVERY |
| AI人设更新 | 每 30 轮 | routes/chat.py:_PERSONA_UPDATE_EVERY |
| 对话上下文窗口 | 最近 4 轮 | routes/chat.py:_build_context (LIMIT 4) |
| 结晶检查间隔 | 每 10 轮 | services/crystallization.py:_CHECK_EVERY |
| 情景检测间隔 | 每 10 轮 | services/narrative.py:_SITUATION_CHECK_EVERY |
| 情节蒸馏阈值 | 5 个情景 | services/narrative.py:_EPISODE_CHECK_THRESHOLD |
| 人设检查间隔 | 每 30 轮 | services/identity_guard.py:_CHECK_EVERY |
| 依恋分析间隔 | 每 30 轮 | services/attachment.py:_CHECK_EVERY |
| pgvector 维度 | 256, halfvec, HNSW | db.py + memory_search.py |
| SSE 流式间隔 | 每 2 字符，30ms 间隔 | routes/chat.py:chat_stream |
| LLM model | deepseek-chat | 所有 LLM 调用点 |

## 修改指南

### 调整 AI 性格
编辑 `services/prompt.py` 中的 `SYSTEM_PROMPT` 或 `build_time_context()`

### 调整 AI 人设
编辑 `/home/xuwl/app/easyChat/memory/user_persona.md`，重启容器生效（或等待每30轮的自动反思更新）

### 添加新 API 端点
1. 在 `app/routes/` 下新建文件（参考已有文件的模式）
2. 在 `app/routes/__init__.py` 中注册
3. 业务逻辑放 `services/`

### 添加新前端功能
1. 按功能归属选择 engine.js（逻辑/状态）、visuals.js（渲染）、ui.js（交互）
2. 在 `globals.d.ts` 中声明新类型/函数

### 修改数据库表
编辑 `app/db.py:init_db()`，在函数末尾追加 migration 逻辑（参考已有的 `emotion_cache` 列追加模式）

### 调试
- 后端日志: `docker compose logs -f app`
- 前端调试面板: 三击页面左下角 8×8px 区域
- LLM 错误: 自动分类（timeout→信号不好, rate limit→说得太快, auth→钥匙坏了, connection→连接断开）并输出到日志+调试面板

## 常见问题

**Q: 新部署后 AI 没有个性？**
A: 确认 `/home/xuwl/app/easyChat/memory/user_persona.md` 和 `user_profile.md` 存在。启动时会自动从种子数据复制。

**Q: pgvector 扩展加载失败？**
A: 确认 docker-compose.yml 使用 `pgvector/pgvector:pg15` 镜像，不是普通 `postgres:15`。

**Q: 容器内存/磁盘占用大？**
A: `chat_history` 和 `idle_thoughts` 表会无限增长。可考虑定期清理旧记录或设置 retention policy。

**Q: 如何导出对话记录？**
A: 对话归档在 `/home/xuwl/app/easyChat/memory/conversation_archive.jsonl`，每行一条 JSON。

**Q: SSE 流式没有表情帧？**
A: 检查 DeepSeek API 是否正确返回了 emotions 数组。response_format=json_object 与对话历史结合时有已知bug，项目已绕过，使用大括号匹配直接提取JSON。
