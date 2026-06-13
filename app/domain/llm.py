from typing import Any

from pydantic import BaseModel


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]


class LlmReply(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = []