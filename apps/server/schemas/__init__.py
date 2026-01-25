"""
Pydantic schemas for API request/response models.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# Thread schemas
class ThreadCreate(BaseModel):
    title: Optional[str] = None
    metadata: Optional[str] = None


class Thread(BaseModel):
    id: str
    title: Optional[str]
    created_at: str
    updated_at: str
    metadata: Optional[str]


# Message schemas
class MessageCreate(BaseModel):
    content: str


class Message(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    created_at: str
    tool_calls: Optional[str] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


# Memory schemas
class MemoryCreate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


class Memory(BaseModel):
    id: str
    key: str
    value: str
    description: Optional[str]
    created_at: str
    updated_at: str


# Chat schemas
class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


class ChatResponse(BaseModel):
    thread_id: str
    message: Message
    assistant_message: Message


# Settings schemas
class SettingsUpdate(BaseModel):
    model_name: Optional[str] = None
    openai_api_key: Optional[str] = None


class Settings(BaseModel):
    model_name: str
    has_api_key: bool
