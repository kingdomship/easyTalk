"""Condense conversation history into a compact memory summary.

Reads the full JSONL conversation history, extracts the transcript,
and uses DeepSeek to generate a ~1-2KB summary capturing:
- Key facts about the user
- AI persona in action
- Interaction patterns and inside jokes
"""

import json
import os
import sys


def extract_transcript(jsonl_path: str) -> str:
    """Extract user/assistant dialogue from JSONL."""
    with open(jsonl_path) as f:
        lines = f.readlines()

    transcript = []
    for line in lines:
        try:
            d = json.loads(line)
            t = d.get("type", "")
            if t == "user":
                msg = d.get("message", {})
                if isinstance(msg, dict) and not msg.get("isMeta"):
                    c = msg.get("content", "")
                    if c and len(c.strip()) > 10:
                        transcript.append(f"用户：{c.strip()}")
            elif t == "assistant":
                msg = d.get("message", {})
                if isinstance(msg, dict):
                    c = msg.get("content", "")
                    if isinstance(c, list):
                        texts = []
                        for b in c:
                            if isinstance(b, dict) and b.get("type") == "text":
                                texts.append(b.get("text", ""))
                        c = "\n".join(texts)
                    if isinstance(c, str) and len(c.strip()) > 10:
                        transcript.append(f"AI：{c.strip()}")
        except Exception:
            pass

    return "\n\n".join(transcript)


CONDENSE_PROMPT = """你正在阅读一段用户和一个AI角色之间的完整对话记录。

AI角色的人设是：风趣、幽默、知性的漂亮女性，主动找话题，用表情符号表达情绪。

请将这段对话浓缩为一篇「关系记忆」摘要，用于之后每次新对话时注入到AI的system prompt中。

摘要需要包含以下内容（用中文，控制在1500字以内）：

## 用户关键信息
- 从对话中提取用户的基本情况、职业、性格、重要经历、偏好

## 互动模式
- AI和用户之间形成的独特互动风格
- 常用梗和callback（如文竹、两根面条、三字代码等）
- 用户对AI风格的偏好

## 代表性对话片段
- 选2-3个最能体现AI语气和互动风格的简短对话片段

## 注意事项
- AI应该主动找话题，不被动等待
- 适当使用表情符号
- 保持风趣幽默但不失真诚
- 用户讨厌虚假的东西

只输出摘要内容，不要加额外说明。"""


def condense(transcript: str, api_key: str) -> str:
    """Call DeepSeek to condense the transcript."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": CONDENSE_PROMPT},
            {"role": "user", "content": f"以下是完整对话记录：\n\n{transcript}"},
        ],
        temperature=0.5,
        max_tokens=2000,
    )
    return resp.choices[0].message.content


def main():
    jsonl_path = os.path.join(os.path.dirname(__file__), "memory", "conversation_history.jsonl")
    output_path = os.path.join(os.path.dirname(__file__), "memory", "conversation_summary.md")

    if not os.path.exists(jsonl_path):
        print(f"File not found: {jsonl_path}")
        sys.exit(1)

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("DEEPSEEK_API_KEY not set")
        sys.exit(1)

    print("Extracting transcript...")
    transcript = extract_transcript(jsonl_path)
    print(f"Transcript: {len(transcript)} chars, ~{len(transcript)//4} tokens")

    print("Calling DeepSeek to condense...")
    summary = condense(transcript, api_key)

    with open(output_path, "w") as f:
        f.write(summary)

    print(f"Summary written to {output_path} ({len(summary)} chars)")


if __name__ == "__main__":
    main()
