# Psychology

LLM 驱动的像素风虚拟伴侣 —— 住在数字星空里的 AI 角色，通过文字 + 实时像素表情与用户互动。

## 快速开始

```bash
# 1. 设置 API Key
export DEEPSEEK_API_KEY=your_deepseek_api_key

# 2. 启动
docker compose up -d

# 3. 访问
open http://localhost:9010
```

## 项目结构

```
psychology/
├── app/                          # FastAPI 核心
│   ├── main.py                   # 入口 + lifespan 初始化 + 5个定时任务
│   ├── db.py                     # PostgreSQL (pgvector) 连接池 + 建表迁移
│   ├── models.py                 # Pydantic ChatRequest
│   └── routes/
│       ├── __init__.py           # 聚合路由
│       ├── chat.py               # /api/chat + SSE 流式 + 核心管线
│       ├── diary.py              # /api/diary/* AI日记
│       ├── emotions.py           # /api/emotions 表情缓存管理
│       ├── memory.py             # /api/memory + affinity + mood + idle + missing-you
│       └── news.py               # /api/news 热榜聚合 + 话题推荐
├── services/                     # 业务逻辑 (15个模块)
│   ├── prompt.py                 # SYSTEM_PROMPT + 昼夜节律 + temperature
│   ├── memory_loader.py          # 记忆文件加载 (persona/profile/summary)
│   ├── memory_search.py          # pgvector HNSW 语义向量搜索
│   ├── condense.py               # 对话摘要压缩 (每50轮)
│   ├── diary.py                  # AI 日记生成
│   ├── news.py                   # 多源热榜抓取 (B站/GitHub/Tophub/百度)
│   ├── affinity.py               # 10D 亲密度 + 表达幅度学习 + 关系里程碑
│   ├── affect.py                 # Panksepp六系统情绪评估 + Gross调节 + 效价追踪
│   ├── salience.py               # SNARC显著性 (Surprise/Novelty/Arousal/Reward/Conflict)
│   ├── state_machine.py          # 5行为模式 + 4唤醒态
│   ├── identity_guard.py         # 人设漂移检测 + 修正注入
│   ├── crystallization.py        # 模式结晶 + Ebbinghaus遗忘曲线
│   ├── narrative.py              # 叙事蒸馏 (Instant→Situation→Episode→Narrative)
│   ├── prediction.py             # 预测误差学习 (Active Inference)
│   ├── attachment.py             # 依恋风格识别 (焦虑/回避/安全)
│   └── consciousness_loop.py     # 背景意识循环 (空闲独白 + 情绪波动 + 日记种子)
├── static/                       # 前端 (零构建 vanilla JS)
│   ├── index.html                # SPA 骨架
│   ├── style.css                 # 所有样式
│   └── js/
│       ├── engine.js             # 全局状态、表情计算、音频引擎、调试面板
│       ├── visuals.js            # 星空渲染、流星、记忆星点、像素头像绘制
│       ├── ui.js                 # 对话框、SSE流、面板、主循环
│       └── globals.d.ts          # TypeScript 类型声明
├── memory/                       # 记忆数据 (volume 挂载)
│   ├── user_persona.md           # AI 人设
│   ├── user_profile.md           # 用户档案
│   ├── conversation_summary.md   # 对话摘要 (自动生成)
│   ├── conversation_archive.jsonl # 对话归档
│   ├── crystals.jsonl            # 结晶记忆
│   ├── situations.jsonl          # 叙事情景
│   ├── episodes.jsonl            # 叙事章节
│   ├── milestones.jsonl          # 关系里程碑
│   └── attachment_style.json     # 依恋风格分析
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── tsconfig.json
└── .env.example
```

## 架构总览

```
用户输入 → ui.js → POST /api/chat/stream (SSE)
  → _build_context(msg):
      SYSTEM_PROMPT + 昼夜节律
      + 记忆文件 (persona + profile + summary)
      + 结晶记忆 (crystals.jsonl, Ebbinghaus衰减过滤)
      + 叙事上下文 (situations + episodes)
      + pgvector 语义搜索 (HNSW 余弦相似度)
      + 10D亲密度 + Panksepp情绪 + Gross调节策略 + 效价追踪
      + SNARC显著性信号 + 依恋风格建议
      + 人设漂移修正
      + 今天的热门话题
      + 最近4轮对话历史
  → 状态机判断模式 (CHAT/DEEP/COMFORT/EXPLORE/PLAY)
  → 唤醒态判断 (WAKE/FOCUS/REST/CRISIS)
  → 深度问题? → _think() 预分析
  → DeepSeek Chat API (temperature=节律+模式+唤醒)
  → 解析 JSON {emotions, reply}
  → _jitter_frame() + scale_emotion_params()
  → SSE: thinking → emotions → text → done
  → 后台: 归档、亲密度、情绪、显著性、预测、摘要、结晶、情景检测、
          情节蒸馏、人设检查、依恋分析、记忆文件更新
```

## 核心系统

### 表情系统 (15参数)

| 参数 | 范围 | 含义 |
|------|------|------|
| eye_curve | -1~1 | 垂眼(悲伤) → 拱眼(大笑) |
| eye_open | 0~1 | 闭眼 → 瞪大 |
| eye_pupil | -1~1 | 向左看 → 向右看 |
| eye_wink | -1~1 | 左眼眨 → 右眼眨 |
| mouth_curve | -1~1 | 撇嘴 → 灿烂微笑 |
| mouth_open | 0~1 | 紧闭 → 大张 |
| mouth_width | 0.3~1 | 抿嘴 → 咧嘴 |
| mouth_asym | -1~1 | 讥讽冷笑 → 歪嘴坏笑 |
| sparkle | 0~1 | 眼神暗淡 → 闪闪发亮 |
| brow_angle | -1~1 | V字怒 → 八字悲 |
| brow_height | 0~1 | 低压 → 高抬 |
| brow_asym | 0~1 | 对称 → 不对称 |
| blush | 0~1 | 无 → 通红 |
| head_tilt | -1~1 | 左歪头 → 右歪头 |
| tear | 0~1 | 无 → 泪珠 |

64×64像素网格程序化渲染，支持微表情(眨眼/脸红/泪光)、多帧表情序列、内感受呼吸动画。

### 记忆系统 (四层)

| 层 | 机制 | 触发 |
|----|------|------|
| **即时上下文** | 最近4轮对话直接注入 | 每轮 |
| **语义检索** | LLM标签→MD5→256维向量→pgvector HNSW | 每轮 |
| **叙事蒸馏** | Instant→Situation→Episode→Narrative | 每10/50轮 |
| **模式结晶** | 重复话题→LLM蒸馏→持久记忆 + Ebbinghaus衰减 | 每10轮 |

### 情感系统

- **Panksepp六系统**: SEEKING/PLAY/CARE/FEAR/RAGE/PANIC 维度评估
- **Gross人际情绪调节**: 认知重评/共情回应/陪伴/幽默重构/深入探索
- **Active Inference效价追踪**: 追踪情绪变化方向，评估策略有效性
- **SNARC显著性**: Surprise/Novelty/Arousal/Reward/Conflict 五维追踪

### 关系系统 (10D亲密度)

| 经典维度 | SDT维度 | 其他 |
|----------|---------|------|
| warmth, trust, intimacy, curiosity, patience, tension | user_autonomy, user_competence, user_relatedness | expression_amplitude |

关系里程碑: 阈值跨越事件记录到 milestones.jsonl（温暖默契、信任分享、深刻联结、无话不谈、心之桥梁）

### 认知状态

**行为模式** (Soul Engine MentalProcesses): CHAT → DEEP → COMFORT → EXPLORE → PLAY

**唤醒状态** (SAGE): WAKE → FOCUS → REST → CRISIS

每个状态独立调节 temperature、max_tokens、表情幅度

### 背景意识循环

| 任务 | 频率 | 说明 |
|------|------|------|
| 空闲思绪 | 每5分钟 | 用户离线时生成20-40字内心独白 |
| 情绪波动 | 每30分钟 | 表达幅度随机游走(±0.03，趋近1.0) |
| 日记种子 | 每小时 | 累积空闲思绪供日记使用 |

### 人设维护

- **身份免疫**: 每30轮LLM检查人设漂移，分数>0.5时注入修正提醒
- **记忆文件演进**: 每20轮更新用户档案、每30轮更新AI人设 (LLM反思式更新)

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 发送消息，返回 {emotions, reply} |
| POST | `/api/chat/stream` | SSE 流式: thinking → emotions → text → done |
| GET | `/api/chat/history?for_date=&limit=50` | 对话历史 |
| GET | `/api/affinity` | 10D亲密度 + 里程碑列表 |
| GET | `/api/emotions` | 表情缓存列表 (按使用次数降序) |
| DELETE | `/api/emotions/{label}` | 删除表情缓存项 |
| GET | `/api/diary?limit=30` | 日记列表 |
| GET | `/api/diary/{date}` | 指定日期日记 |
| POST | `/api/diary/generate` | 手动触发生成日记 |
| GET | `/api/diary/on-this-day` | 往年今日 |
| GET | `/api/news?limit=30` | 新闻列表 |
| GET | `/api/news/topics?limit=4` | 话题推荐 (用于对话启动) |
| POST | `/api/news/fetch` | 手动触发新闻抓取 |
| GET | `/api/mood/calendar?days=60` | 心情日历 (情绪emoji+聊天数) |
| GET | `/api/memory/persona` | AI人设 |
| GET | `/api/memory/profile` | 用户档案 |
| GET | `/api/idle-thought` | 最新空闲独白 |
| GET | `/api/missing-you` | 思念模式 (离线>12h返回累积独白) |
| GET | `/api/narrative/situations` | 叙事情景列表 |
| GET | `/api/narrative/episodes` | 叙事章节列表 |

## 环境变量

| 变量 | 必需 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | 是 | - |
| `DB_PASSWORD` | 否 | 123456 |
| `DB_HOST` | 否 | postgres |
| `DB_PORT` | 否 | 5432 |
| `DB_NAME` | 否 | psychology |
| `DB_USER` | 否 | postgres |

## 数据持久化

- **记忆文件宿主路径**: `/home/xuwl/app/psychology/memory`
- **容器内挂载点**: `/app/memory`
- **PostgreSQL 数据**: named volume `psychology_pgdata`
- 更新容器时使用宿主路径挂载，避免记忆数据丢失

## 部署

```bash
# 开发/生产部署
docker compose up -d --build

# 查看日志
docker compose logs -f app

# 停止
docker compose down
```

## 技术栈

- **后端**: Python 3.10 + FastAPI + uvicorn
- **LLM**: DeepSeek Chat API (OpenAI 兼容协议)
- **数据库**: PostgreSQL 15 + pgvector (HNSW 向量索引)
- **前端**: 零构建 Vanilla JS + JSDoc @ts-check + Canvas 2D
- **调度**: APScheduler (5个定时任务)

## 设计原则

1. **人格驱动**: AI风趣幽默知性，主动引导对话，非被动问答
2. **全程序化生成**: 无预制素材，面部像素/星空/音效全部算法生成
3. **单LLM架构**: 一个 DeepSeek API 处理聊天/表情/标签/日记/摘要/记忆/叙事/人格分析
4. **零构建前端**: 纯 vanilla JS，无框架，无打包工具
5. **Docker化**: 双容器 (app + pgvector)，单端口 (9010)，开箱即用

## 理论依据

本项目融合了以下前沿心理学和意识工程理论:

- **Panksepp 情感神经科学** — 七原级情绪系统
- **Gross 情绪调节过程模型** (2025 人际扩展)
- **自我决定理论 SDT** (Ryan & Deci)
- **依恋理论** (2025 AI依恋量表, Xie et al.)
- **Active Inference / 自由能原理** (Friston)
- **SAGE 意识循环 + SNARC 显著性**
- **Echo 模式结晶**
- **Soul Engine MentalProcesses**
- **psyche-rs 叙事蒸馏**
- **PHANTASM 内感受节律**
