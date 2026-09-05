from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .domain import AnalysisResponse


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatSource(BaseModel):
    inn: str
    field: str
    value: Any = None


class ChatMessage(BaseModel):
    message_id: str
    role: ChatRole
    content: str
    sources: list[ChatSource] = Field(default_factory=list)
    created_at: datetime


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)


class ChatMessageResponse(BaseModel):
    chat_id: str
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)


class ChatHistoryResponse(BaseModel):
    chat_id: str
    inns: list[str]
    messages: list[ChatMessage] = Field(default_factory=list)


class ChatSession(BaseModel):
    chat_id: str
    inns: list[str]
    analyses: dict[str, AnalysisResponse]
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime


class ChatAgentResult(BaseModel):
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)
