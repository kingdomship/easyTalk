"""Prediction error learning — Active Inference inspired.

After each reply, AI generates a quick implicit prediction of what
the user might say next. On the following turn, the prediction is
compared against the actual message. Large prediction errors trigger:

- Boosted salience surprise
- Enhanced memory consolidation
- Higher priority for profile updates

Prediction runs in background thread to avoid adding latency.
"""

import json
import logging
import os

logger = logging.getLogger("emoji-chat")

from app.config import PREDICTION_PATH

_PREDICTION_PATH = PREDICTION_PATH

_PREDICT_PROMPT = """根据刚才的对话，猜测用户最可能回复什么。用一句话（10-20字）写出你的预期。直接输出，不要JSON。"""


def generate_prediction(user_msg: str, avatar_reply: str):
    """Generate a prediction of what the user will say next.

    Called in background thread after each reply. Uses short LLM call.
    """
    if len(user_msg) < 5 or len(avatar_reply) < 5:
        return

    try:
        from app.utils import get_llm, get_llm_model
        client = get_llm()
        if client is None:
            return

        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _PREDICT_PROMPT},
                {"role": "user", "content": f"用户说：{user_msg[:100]}"},
                {"role": "assistant", "content": f"AI回复：{avatar_reply[:100]}"},
            ],
            temperature=0.5,
            max_tokens=40,
        )
        prediction = resp.choices[0].message.content.strip()
        if prediction:
            os.makedirs(os.path.dirname(_PREDICTION_PATH), exist_ok=True)
            with open(_PREDICTION_PATH, "w") as f:
                json.dump({"prediction": prediction, "user_msg": user_msg[:80]}, f)
            logger.info("Prediction: %s", prediction[:50])
    except Exception:
        logger.warning("Operation failed", exc_info=True)


def check_prediction(user_msg: str) -> float:
    """Compare current user message against saved prediction.

    Returns prediction error score (0-1). 0 = perfectly predicted,
    1 = completely unexpected. Uses simple text overlap heuristic
    since a full semantic comparison would require another LLM call.

    The score feeds into salience.surprise boost.
    """
    try:
        if not os.path.exists(_PREDICTION_PATH):
            return 0.0

        with open(_PREDICTION_PATH) as f:
            prev = json.load(f)

        predicted = prev.get("prediction", "")
        if not predicted:
            return 0.0

        # Simple overlap: what fraction of predicted chars are in the actual msg
        overlap = sum(1 for c in predicted if c in user_msg)
        overlap_ratio = overlap / max(1, len(predicted))

        # Also check if key words match
        pred_words = set(predicted)
        msg_words = set(user_msg)
        word_overlap = len(pred_words & msg_words) / max(1, len(pred_words))

        # Combined score: lower overlap = higher error
        combined = (overlap_ratio + word_overlap) / 2
        error = max(0.0, min(1.0, 1.0 - combined))

        return error
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return 0.0


def get_prediction_context() -> str:
    """Prediction error is injected via salience boost during _build_context."""
    return ""
