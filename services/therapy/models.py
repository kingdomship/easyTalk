"""治疗模块 Pydantic 模型."""

from pydantic import BaseModel, Field


class AcknowledgeRequest(BaseModel):
    event_id: int = Field(..., ge=1, description="要标记为已处理的危机事件 ID")
