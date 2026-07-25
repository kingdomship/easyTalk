# easyTalk

LLM 驱动的像素风虚拟伴侣 —— 住在数字星空里的 AI 角色，通过文字 + 实时像素表情与用户互动。

## 快速开始

```bash
# 1. 设置 API Key
export DEEPSEEK_API_KEY=your_deepseek_api_key

# 2. 启动
docker compose up -d

# 3. 访问
open http://localhost:8000
```

## 项目结构

```
easytalk/
├── app/                          # FastAPI 核心
│   ├── main.py                   # 入口 + lifespan 初始化 + 9个定时任务 + ASGI middleware
│   ├── db.py                     # PostgreSQL (pgvector) 连接池 + 建表迁移
│   ├── models.py                 # Pydantic ChatRequest
│   ├── config.py                 # 路径常量 (MEMORY_DIR / LOG_DIR) + atomic_write
│   ├── utils.py                  # LLM 客户端 + 后台线程池
│   ├── llm_config.py             # LLM 配置中心 (12家供应商)
│   ├── log_setup.py              # JSON 结构化日志 + 日切轮转
│   ├── audit.py                  # 审计追踪 (fire-and-forget 非阻塞写入)
│   ├── tracer.py                 # 请求追踪 (request_id 传播 + span 计时)
│   ├── token_tracker.py          # Token 用量追踪 (内存队列 + 批量刷入 DB)
│   ├── cleanup.py                # 数据生命周期清理 (7表语义保留式修剪)
│   ├── emotion_params.py         # 27维情感参数定义
│   └── routes/                   # API 路由 (thin layer)
│       ├── chat.py               # /api/chat + SSE 流式 + 核心管线
│       ├── config.py             # /api/config/* (LLM配置 + API Key)
│       ├── debug.py              # /api/debug/* (审计查询 + 性能统计 + 日志级别)
│       ├── diary.py              # /api/diary/*
│       ├── emotions.py           # /api/emotions/*
│       ├── memory.py             # /api/memory/* + affinity + mood
│       ├── news.py               # /api/news/*
│       └── visual.py             # /api/visual/* (摄像头帧 + 视觉LLM)
├── services/                     # 业务逻辑 (6个子目录, ~30个模块)
│   ├── cognition/                # 认知系统 (双系统思维/预测误差/状态机)
│   ├── emotion/                  # 情绪系统 (affect/affinity/attachment/contagion/self_affect/salience)
│   ├── identity/                 # 身份系统 (personality/prompt/sprite/drift_detector/guard)
│   ├── drive/                    # 驱动系统 (动机引擎)
│   ├── info/                     # 信息获取 (多源热榜)
│   ├── psych/                    # 心理系统 (用户画像/对话目标/生活领域/好奇心)
│   ├── memory/                   # 记忆系统 (摘要/结晶/叙事/知识图谱/语义搜索)
│   └── reflection/               # 反思系统 (意识循环/AI日记)
├── static/                       # 前端 (零构建 vanilla JS)
│   ├── index.html                # SPA 骨架
│   ├── style.css                 # 所有样式
│   └── js/
│       ├── engine.js             # 全局状态、表情计算、调试面板(4标签)、日志转发
│       ├── visuals.js            # 星空渲染、流星、像素头像、精灵系统
│       ├── constellation.js      # 交互式星图 (力导向图 + 触摸手势)
│       ├── ui.js                 # 对话框、SSE流、面板、主循环
│       └── globals.d.ts          # TypeScript 类型声明
├── memory/                       # 记忆数据 (volume 挂载)
│   ├── user_persona.md           # AI 人设
│   ├── user_profile.md           # 用户档案
│   ├── conversation_archive.jsonl # 对话归档
│   ├── conversation_summary.md   # 对话摘要 (自动生成)
│   ├── crystals.jsonl            # 结晶记忆
│   ├── situations.jsonl          # 叙事情景
│   ├── episodes.jsonl            # 叙事章节
│   ├── logs/                     # 结构化日志 (JSON, 日切 + 30天留存)
│   └── llm_config.json           # LLM 供应商配置
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 架构总览

```
用户输入 → ui.js → POST /api/chat (SSE)
  → @app.middleware("http") → set_request_id() → X-Request-ID 注入
  → _build_context(msg):
      [基础层] 模块化提示词 + 时间节律 + 人格 (OCEAN/MBTI/原型)
      [关系层] 10D亲密度 + 连续性/关怀/锚点/时间线
      [情绪层] Panksepp六系统 + Gross调节 + 效价 + 显著性 + 情绪感染 + AI自我情绪
      [认知层] 对话目标 + 生活领域 + 好奇心 + 驱动 + 依恋
      [信息层] 新闻 + 结晶记忆 + 叙事 + 语义搜索 + 知识图谱
      [反思层] 双系统思考 + 行为模式 + 漂移检测 + 预测误差
      [整合层] 统一用户画像 (~20数据源) + 最近4轮对话
  → DeepSeek Chat API (temperature=节律+模式+唤醒调节)
  → 解析 JSON {emotions, reply, sprite_keywords, color_fields, ...}
  → 两段式精灵生成 (关键词 → 精灵库查询 → LLM生成16×16像素)
  → SSE: thinking → emotions → text → sprites → done
  → 后台管线: 归档、情绪更新、亲密度、显著性、摘要、结晶、叙事、
              人设检查、依恋分析、情绪感染、对话目标、生活领域、好奇心、
              预测误差、驱动更新、audit_log、token 追踪
```

## 核心系统

### 表情系统 (27参数)

64×64 像素网格程序化渲染，覆盖眼睛(6维)、嘴部(7维)、眉毛(3维)、脸颊(2维)、头部(1维)、特效(4维)。支持微表情(眨眼/脸红/泪光)、多帧表情序列、内感受呼吸动画。

### 记忆系统 (四层)

| 层 | 机制 | 触发 |
|----|------|------|
| **即时上下文** | 最近4轮对话直接注入 | 每轮 |
| **语义检索** | LLM标签→MD5→256维向量→pgvector HNSW | 每轮 |
| **叙事蒸馏** | Instant→Situation(每10轮)→Episode(每5个Situation) | 每10/50轮 |
| **模式结晶** | 重复话题→LLM蒸馏→持久记忆 + Ebbinghaus衰减 | 每10轮 |

### 情绪系统

- **Panksepp 六系统**: SEEKING/PLAY/CARE/FEAR/RAGE/PANIC 维度评估
- **Gross 人际情绪调节**: 5种策略 (认知重评/共情回应/陪伴/幽默重构/深入探索)
- **情绪感染**: lag-1 因果追踪 AI→用户情绪影响，安抚有效性评估
- **AI 自我情绪**: 6D Panksepp 跨会话持久化，昼夜节律 + 对话质量加成
- **SNARC 显著性**: Surprise/Novelty/Arousal/Reward/Conflict 五维追踪

### 关系系统 (10D亲密度)

经典维度: warmth, trust, intimacy, curiosity, patience, tension
SDT 维度: user_autonomy, user_competence, user_relatedness
元参数: expression_amplitude (表达幅度 0.5含蓄~1.5夸张)

5个关系里程碑: 温暖默契 → 信任分享 → 深刻联结 → 无话不谈 → 心之桥梁

### 认知与心理

- **双系统思维**: 快速直觉 (System1) + 慢速推理 (System2)，每23分钟巩固
- **5种行为模式**: CHAT / DEEP / COMFORT / EXPLORE / PLAY
- **4种唤醒态**: WAKE / FOCUS / REST / CRISIS
- **对话目标追踪**: 倾诉/求助/分享/辩论/闲聊 五类意图识别
- **6大生活领域**: 工作/关系/健康/兴趣/财务/成长 结构化感知
- **好奇心队列**: 信息缺口检测 + LLM富化，追踪 AI "想知道但还没问"
- **统一用户画像**: 聚合 ~20 数据源，60s 缓存，200-500字中文画像

### 个性化能力

- **模块化提示词**: 10个独立模块按需组装，简单闲聊省56% token
- **多段叙事 (Scenes)**: Freytag金字塔结构，分段流式输出 + "下一段"交互
- **两段式精灵生成**: LLM关键词 → 精灵库查询 → 16×16像素网格 → Canvas渲染
- **新闻话题推荐**: 4源并发抓取 (B站/GitHub/Tophub/百度) + 智能推荐

## 定时任务 (9个)

| 任务 | 时间 | 说明 |
|------|------|------|
| 日记生成 | 每天 04:00 | 为昨天生成 AI 日记 |
| 新闻抓取 | 每天 07:00 | 4源并发异步抓取热榜 |
| 空闲思绪 | 每5分钟 | 离线时生成内心独白 |
| 情绪波动 | 每30分钟 | 表达幅度随机游走 |
| 日记种子 | 每小时 | 累积空闲思绪供日记使用 |
| 数据清理 | 每天 03:07 | 7表语义保留式修剪 (chat/memory/mood/archive/trace/audit/token) |
| 离线分析 | 每7分钟 | 预测代理离线分析 |
| System2巩固 | 每23分钟 | 慢速推理结果巩固 |
| 驱动心跳 | 每3分钟 | 驱动值衰减 + 自我情绪衰减 |

## 日志追踪系统

- **JSON 结构化日志**: `memory/logs/app.YYYY-MM-DD.log`，日切 + 30天留存
- **Request ID 传播**: 纯 ASGI middleware 自动分配，响应头 `X-Request-ID`
- **审计追踪**: `audit_log` 表记录所有用户操作（fire-and-forget 非阻塞）
- **Token 追踪**: 内存队列 + `_flush_lock` 批量刷入 `token_usage` 表
- **前端日志转发**: 熔断器保护（3次失败永久禁用），2秒节流
- **调试面板**: 4个标签页（日志/情绪/Token/审计），审计支持筛选+搜索+分页

## API 端点

### 聊天
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 发送消息 (SSE 流式) |
| GET | `/api/chat/history?for_date=&limit=50` | 对话历史 |

### 情绪 & 记忆
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/emotions` | 表情缓存列表 |
| DELETE | `/api/emotions/{label}` | 删除表情缓存 |
| GET | `/api/emotions/self` | AI 自身 6D情绪 + 8D驱动 |
| GET | `/api/affinity` | 10D亲密度 + 里程碑 |
| GET | `/api/memory/persona` | AI 人设 |
| GET | `/api/memory/profile` | 用户档案 |
| GET | `/api/memory/constellation` | 交互式星图数据 |
| GET | `/api/memory/kg` | 知识图谱子图 |
| GET | `/api/mood/calendar?days=60` | 心情日历 |

### 日记 & 新闻
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/diary?limit=30` | 日记列表 |
| GET | `/api/diary/{date}` | 指定日期日记 |
| POST | `/api/diary/generate` | 手动触发 AI 日记 |
| POST | `/api/diary/generate-user` | 手动触发用户日记 |
| GET | `/api/diary/on-this-day` | 往年今日 |
| GET | `/api/news?limit=30` | 新闻列表 |
| GET | `/api/news/topics?limit=4` | 话题推荐 |
| POST | `/api/news/fetch` | 手动抓取新闻 |
| POST | `/api/news/suggest` | 智能话题推荐 |

### 配置 & 视觉
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config/apikey` | 获取 API Key 状态 |
| POST | `/api/config/apikey` | 设置自定义 API Key |
| GET | `/api/config/llm` | 获取 LLM 配置 |
| POST | `/api/config/llm` | 保存 LLM 配置 |
| POST | `/api/visual/upload` | 上传摄像头帧 |
| POST | `/api/visual/analyze` | 视觉 LLM 分析 |
| GET | `/api/visual/latest` | 最新帧预览 |

### 调试 & 审计
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/debug/audit` | 审计日志查询 (筛选+搜索+分页) |
| GET | `/api/debug/audit/categories` | 审计分类列表 |
| GET | `/api/debug/performance` | p50/p95/p99 延迟统计 |
| POST | `/api/debug/loglevel` | 运行时切换日志级别 |
| POST | `/api/log/client` | 前端日志转发 |
| GET | `/api/debug/token-history` | Token 历史 (DB 持久化) |

### 其他
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/idle-thought` | 最新空闲独白 |
| GET | `/api/missing-you` | 思念模式 (离线>12h 累积独白) |
| GET | `/api/narrative/situations` | 叙事情景列表 |
| GET | `/api/narrative/episodes` | 叙事章节列表 |

## 环境变量

| 变量 | 必需 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | 是 | - |
| `DB_PASSWORD` | 否 | 123456 |
| `DB_HOST` | 否 | postgres |
| `DB_PORT` | 否 | 5432 |
| `DB_NAME` | 否 | emotion |
| `DB_USER` | 否 | postgres |

## 数据持久化

- **记忆文件宿主路径**: `/home/xuwl/app/easytalk/memory`
- **容器内挂载点**: `/app/memory`
- **日志文件**: `memory/logs/` (JSON 日切, 30天留存)
- **PostgreSQL 数据**: named volume `pgdata`
- 更新容器时使用宿主路径挂载，避免记忆数据丢失

## 部署

```bash
# 开发/生产部署
docker compose up -d --build

# 查看日志 (JSON 格式)
docker compose logs -f app

# 查看审计日志
curl https://localhost:8443/api/debug/audit?category=chat

# 停止
docker compose down
```

### 阿里云 ACR

```bash
docker build -t easytalk-app:latest .
docker tag easytalk-app:latest crpi-1gdx2774xijb53l6.cn-chengdu.personal.cr.aliyuncs.com/xuwl03/easytalk:latest
docker push crpi-1gdx2774xijb53l6.cn-chengdu.personal.cr.aliyuncs.com/xuwl03/easytalk:latest
```

## 技术栈

- **后端**: Python 3.10 + FastAPI + uvicorn
- **LLM**: DeepSeek Chat API (OpenAI 兼容协议)
- **数据库**: PostgreSQL 15 + pgvector (HNSW 向量索引)
- **前端**: 零构建 Vanilla JS + JSDoc @ts-check + Canvas 2D
- **调度**: APScheduler (9个定时任务)
- **日志**: JSON 结构化日志 + TimedRotatingFileHandler + 审计追踪表
- **部署**: Docker Compose (app + pgvector 双容器)

## 设计原则

1. **人格驱动**: AI风趣幽默知性，主动引导对话，非被动问答
2. **全程序化生成**: 无预制素材，面部像素/星空/音效全部算法生成
3. **单LLM架构**: 一个 DeepSeek API 处理聊天/表情/标签/日记/摘要/记忆/叙事/人格分析
4. **零构建前端**: 纯 vanilla JS，无框架，无打包工具
5. **Docker化**: 双容器 (app + pgvector)，双端口 (8000 HTTP + 8443 HTTPS)

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
- **Freytag 叙事金字塔** (多段叙事结构)
