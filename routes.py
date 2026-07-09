"""Emotion chat API — DeepSeek-powered real-time expression generation."""

import os
import json
import hashlib
from fastapi import APIRouter

from db import q, execute, init_db
from models import ChatRequest

router = APIRouter()

# Init DB on first use
_init_done = False

def _ensure_db():
    global _init_done
    if not _init_done:
        init_db()
        _init_done = True

# DeepSeek client (lazy)
_client = None

def _get_llm():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com",
        )
    return _client

SYSTEM_PROMPT = """你是一个极简像素头像的表情控制器。根据用户输入，分析情绪并输出 JSON。

你的输出可以是一个**单一表情**，也可以是一个**情绪变化序列**（当文字描述了情绪转变时）。

## 参数说明（10 个连续值）

脸部参数：
- eye_curve: 眼角弯曲，-1(垂眼/悲伤) ~ 0(平眼/正常) ~ 1(拱眼/开心大笑)
- eye_open: 睁眼程度，0(闭眼/一条线) ~ 0.5(正常) ~ 1(瞪大圆睁/震惊)
- eye_pupil: 瞳孔偏移，-1(向左看/回避) ~ 0(正视) ~ 1(向右看/思考)
- mouth_curve: 嘴角弯曲，-1(深深撇嘴/悲痛) ~ 0(平嘴) ~ 1(灿烂微笑)
- mouth_open: 张嘴程度，0(紧闭) ~ 0.4(微张说话) ~ 1(大张/惊呼)
- mouth_width: 嘴宽度，0.3(抿成一点/害羞) ~ 0.7(正常) ~ 1(咧到最大)
- sparkle: 眼睛高光亮度，0(无神暗淡/困倦绝望) ~ 0.5(平常) ~ 1(闪闪发亮/狂喜)

眉毛参数（极简但极关键）：
- brow_angle: 眉角，-1(内端低外端高/V字形/愤怒坚毅) ~ 0(平眉) ~ 1(内端高外端低/八字眉/悲伤担忧)
- brow_height: 眉高度，0(低压在眼上/紧张疲惫) ~ 0.5(正常) ~ 1(高高在上/震惊)
- brow_asym: 眉不对称，0(完全对称) ~ 1(一高一低极不对称/困惑狐疑嘲讽)

回复：
- reply: 简短中文，≤20字

## 示例

用户说"为了妹妹，我必须活下去":
{"emotions":[{"label":"determined_sorrow","duration_ms":4000,"eye_curve":-0.2,"eye_open":0.5,"eye_pupil":0,"mouth_curve":-0.3,"mouth_open":0.05,"mouth_width":0.6,"sparkle":0.3,"brow_angle":-0.7,"brow_height":0.3,"brow_asym":0}],"reply":"一定要活下去..."}

用户说"搞错了步骤结果项目反而成功了":
{"emotions":[{"label":"confused_tilt","duration_ms":2000,"eye_curve":0,"eye_open":0.5,"eye_pupil":0.4,"mouth_curve":-0.1,"mouth_open":0,"mouth_width":0.4,"sparkle":0.2,"brow_angle":0.2,"brow_height":0.6,"brow_asym":0.8},{"label":"surprised_delight","duration_ms":4000,"eye_curve":0.7,"eye_open":0.75,"eye_pupil":0,"mouth_curve":0.8,"mouth_open":0.5,"mouth_width":0.9,"sparkle":0.9,"brow_angle":-0.2,"brow_height":0.7,"brow_asym":0}],"reply":"诶？等等...居然成了？！哈哈"}

用户说"像周星驰那样夸张大笑":
{"emotions":[{"label":"exaggerated_laugh","duration_ms":4000,"eye_curve":1,"eye_open":0.3,"mouth_curve":1,"mouth_open":1,"mouth_width":1,"sparkle":1,"brow_angle":-0.5,"brow_height":0.8,"brow_asym":0}],"reply":"哇哈哈哈哈！"}

只输出 JSON，不要其他内容。"""


@router.post("/api/chat")
async def chat(req: ChatRequest):
    _ensure_db()
    msg = req.message.strip()
    if not msg:
        return {"error": "empty message"}

    # Exact-match cache (same text → same result)
    key = "exact:" + hashlib.md5(msg.encode()).hexdigest()[:16]
    row = q("SELECT * FROM emotion_cache WHERE label = %s", [key], fetch="one")
    if row:
        execute("UPDATE emotion_cache SET use_count = use_count + 1, updated_at = NOW() WHERE id = %s", [row["id"]])
        result = _row_to_response(row)
        result["source"] = "cache"
        return result

    # Call DeepSeek
    try:
        client = _get_llm()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.8,
            max_tokens=600,
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        return {
            "emotions": [_default_frame()],
            "reply": "嗯...",
            "source": "fallback",
        }

    emotions = data.get("emotions", [])
    if not emotions:
        emotions = [_default_frame()]

    parsed = [_clamp(f) for f in emotions]
    result = {"emotions": parsed, "reply": str(data.get("reply", "嗯"))[:20]}

    # Store — by exact key and by semantic label
    first = parsed[0]
    seq = json.dumps(parsed) if len(parsed) > 1 else None
    _upsert(key, first["eye_curve"], first["eye_open"], first["eye_pupil"],
            first["mouth_curve"], first["mouth_open"], first["mouth_width"],
            first["sparkle"], first["brow_angle"], first["brow_height"],
            first["brow_asym"], result["reply"], seq)
    _upsert(first["label"], first["eye_curve"], first["eye_open"], first["eye_pupil"],
            first["mouth_curve"], first["mouth_open"], first["mouth_width"],
            first["sparkle"], first["brow_angle"], first["brow_height"],
            first["brow_asym"], result["reply"], seq)

    result["source"] = "llm"
    return result


def _default_frame():
    return {"label":"neutral","duration_ms":3000,"eye_curve":0,"eye_open":0.5,"eye_pupil":0,
            "mouth_curve":0,"mouth_open":0,"mouth_width":0.8,"sparkle":0.5,
            "brow_angle":0,"brow_height":0.5,"brow_asym":0}


def _clamp(f):
    return {
        "label": str(f.get("label","unknown"))[:30],
        "duration_ms": max(500, min(10000, int(f.get("duration_ms",3000)))),
        "eye_curve": max(-1, min(1, float(f.get("eye_curve",0)))),
        "eye_open": max(0, min(1, float(f.get("eye_open",0.5)))),
        "eye_pupil": max(-1, min(1, float(f.get("eye_pupil",0)))),
        "mouth_curve": max(-1, min(1, float(f.get("mouth_curve",0)))),
        "mouth_open": max(0, min(1, float(f.get("mouth_open",0)))),
        "mouth_width": max(0.3, min(1, float(f.get("mouth_width",0.8)))),
        "sparkle": max(0, min(1, float(f.get("sparkle",0.5)))),
        "brow_angle": max(-1, min(1, float(f.get("brow_angle",0)))),
        "brow_height": max(0, min(1, float(f.get("brow_height",0.5)))),
        "brow_asym": max(0, min(1, float(f.get("brow_asym",0)))),
    }


def _upsert(label, ec, eo, ep, mc, mo, mw, sp, ba, bh, bas, reply, seq):
    existing = q("SELECT id FROM emotion_cache WHERE label = %s", [label], fetch="one")
    if existing:
        execute("""
            UPDATE emotion_cache SET eye_curve=%s, eye_open=%s, eye_pupil=%s,
                mouth_curve=%s, mouth_open=%s, mouth_width=%s, sparkle=%s,
                brow_angle=%s, brow_height=%s, brow_asym=%s,
                reply=%s, sequence_data=%s,
                use_count=use_count+1, updated_at=NOW()
            WHERE id=%s
        """, [ec, eo, ep, mc, mo, mw, sp, ba, bh, bas, reply, seq, existing["id"]])
    else:
        execute("""
            INSERT INTO emotion_cache (label, eye_curve, eye_open, eye_pupil,
                mouth_curve, mouth_open, mouth_width, sparkle,
                brow_angle, brow_height, brow_asym, reply, sequence_data)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, [label, ec, eo, ep, mc, mo, mw, sp, ba, bh, bas, reply, seq])


def _row_to_response(row):
    result = {
        "label": row["label"],
        "eye_curve": row["eye_curve"], "eye_open": row["eye_open"],
        "eye_pupil": row.get("eye_pupil", 0),
        "mouth_curve": row["mouth_curve"], "mouth_open": row["mouth_open"],
        "mouth_width": row["mouth_width"], "sparkle": row["sparkle"],
        "brow_angle": row.get("brow_angle", 0),
        "brow_height": row.get("brow_height", 0.5),
        "brow_asym": row.get("brow_asym", 0),
        "reply": row["reply"],
    }
    seq = row.get("sequence_data")
    if seq:
        result["emotions"] = json.loads(seq) if isinstance(seq, str) else seq
        for f in result["emotions"]:
            if "duration_ms" not in f:
                f["duration_ms"] = 3000
    else:
        result["emotions"] = [{**result, "duration_ms": 3000}]
    return result


# ── Cache management ──

@router.get("/api/emotions")
def list_emotions():
    _ensure_db()
    rows = q("SELECT * FROM emotion_cache WHERE label NOT LIKE 'exact:%%' ORDER BY use_count DESC")
    return rows


@router.delete("/api/emotions/{label}")
def delete_emotion(label: str):
    execute("DELETE FROM emotion_cache WHERE label = %s", [label])
    return {"ok": True}
