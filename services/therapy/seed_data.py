"""危机热线种子数据 — 在 app 启动时 idempotent 插入."""

import logging
from app.db import q, execute

logger = logging.getLogger("emoji-chat")

_CRISIS_RESOURCES = [
    {
        "name": "北京24小时心理援助热线",
        "phone": "010-82951332",
        "description": "北京市心理危机研究与干预中心, 提供24小时免费心理支持",
        "country": "中国",
        "hours": "24小时",
    },
    {
        "name": "全国希望24热线",
        "phone": "400-161-9995",
        "description": "全国性24小时心理危机干预热线, 由专业志愿者值守",
        "country": "中国",
        "hours": "24小时",
    },
    {
        "name": "生命热线",
        "phone": "400-821-1215",
        "description": "面向全国的免费心理支持热线",
        "country": "中国",
        "hours": "24小时",
    },
    {
        "name": "青少年心理援助热线",
        "phone": "12355",
        "description": "共青团中央设立的青少年心理健康服务热线",
        "country": "中国",
        "hours": "工作日 9:00-17:00",
    },
    {
        "name": "北京危机干预中心",
        "phone": "010-82951332",
        "description": "北京回龙观医院心理危机研究与干预中心",
        "country": "中国",
        "hours": "工作日 9:00-17:00",
    },
]


def seed_crisis_resources():
    """Idempotent: 将默认热线号码插入 crisis_resources 表 (如不存在)."""
    try:
        existing = q("SELECT COUNT(*) as cnt FROM crisis_resources", fetch="one")
        if existing and existing["cnt"] > 0:
            return

        for r in _CRISIS_RESOURCES:
            execute(
                """INSERT INTO crisis_resources (name, phone, description, country, hours)
                   VALUES (%s, %s, %s, %s, %s)""",
                [r["name"], r["phone"], r["description"], r["country"], r["hours"]],
            )
        logger.info("Seeded %d crisis resources", len(_CRISIS_RESOURCES))
    except Exception:
        logger.warning("seed_crisis_resources failed (table may not exist yet)", exc_info=True)
