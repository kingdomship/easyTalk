# emoji-chat 项目关键约定

## 目录结构

```
emoji-chat/
├── app/                    # 应用核心（FastAPI 入口、DB、路由、模型）
│   ├── main.py             # 入口 + lifespan + seed memory
│   ├── db.py               # PostgreSQL 连接池 + init_db
│   ├── models.py           # Pydantic 模型
│   └── routes/             # API 路由（按功能拆分）
│       ├── __init__.py     # 聚合所有子路由
│       ├── chat.py         # /api/chat + 流式 + 工具函数
│       ├── diary.py        # /api/diary/*
│       ├── emotions.py     # /api/emotions/*
│       ├── memory.py       # /api/memory/* + affinity + mood
│       └── news.py         # /api/news/*
├── services/               # 业务逻辑
│   ├── prompt.py           # SYSTEM_PROMPT + 昼夜节律上下文
│   ├── memory_loader.py    # 记忆文件加载
│   ├── memory_search.py    # 语义向量搜索
│   ├── condense.py         # 对话摘要压缩
│   ├── diary.py            # 日记生成
│   ├── news.py             # 多源热榜抓取
│   └── affinity.py         # 6D 亲密度 + 表达幅度学习
├── static/                 # 前端
│   ├── index.html          # HTML 骨架
│   ├── style.css           # 所有样式
│   └── js/
│       ├── engine.js       # 全局变量、工具函数、表情系统、音频
│       ├── visuals.js      # 星空渲染、流星、记忆星点、头像绘制
│       └── ui.js           # 对话框、输入、SSE、面板、主循环
├── memory/                 # 记忆数据（volume 挂载）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 导入规范

- `app/` 是核心层，不依赖 `services/`
- `services/` 依赖 `app.db`，不依赖 `app.routes`
- 跨模块导入使用完整路径：`from app.db import ...`、`from services.xxx import ...`

## 数据持久化

- **记忆文件宿主路径**: `/home/xuwl/app/easyChat/memory`
- 容器内挂载点: `/app/memory`
- 该目录存放: `user_persona.md`（人设）、`user_profile.md`（用户档案）、`conversation_history.jsonl`（对话历史）、`conversation_summary.md`（对话摘要）
- 更新容器时使用此宿主路径，避免记忆数据丢失
- PostgreSQL 数据通过 named volume `pgdata` 持久化

## 记忆系统架构

分三层：
1. **原始消息**: 最近 20 条（10 轮）直接注入 context
2. **语义检索**: `services/memory_search.py` — LLM 提取标签 + pgvector HNSW 索引，按话题相关性检索
3. **定期摘要**: `_maybe_condense()` — 每 50 轮自动压缩为 `conversation_summary.md`

## 部署

- 使用 `docker-compose.yml` 构建和启动
- PostgreSQL 镜像: `pgvector/pgvector:pg15`（支持向量搜索）
- 服务端口: `9010:8000`
- 需要环境变量 `DEEPSEEK_API_KEY`、`DB_PASSWORD`（可选，默认 123456）
