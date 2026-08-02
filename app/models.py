from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    metaphysics_mode: str = "off"  # "off" | "chat" | "reading"
    temp_birth: dict | None = None
