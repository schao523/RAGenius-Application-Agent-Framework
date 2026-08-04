"""
Pydantic schemas for request and response bodies.

These models define the shape of data exchanged over the API.  They are
derived from the data model in the design specification.  Each schema
class contains type annotations and validation logic.  Optional fields
allow partial updates via PATCH endpoints.
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class ApplicationBase(BaseModel):
    name: str = Field(..., title="Application Name", min_length=1)
    description: str = Field(..., title="Description", min_length=1)
    starter_questions: List[str] = Field(..., title="Starter Questions", min_items=4, max_items=4)

    @validator("starter_questions")
    def validate_starter_questions(cls, v: List[str]) -> List[str]:  # noqa: N805
        if len(v) != 4:
            raise ValueError("Exactly four starter questions are required")
        return v


class ApplicationCreate(ApplicationBase):
    config_schema: Dict[str, Any] = Field(default_factory=dict, title="Configuration Schema")
    config_settings: Dict[str, Any] = Field(default_factory=dict, title="Configuration Settings")


class ApplicationUpdate(BaseModel):
    name: Optional[str] = Field(None, title="Application Name", min_length=1)
    description: Optional[str] = Field(None, title="Description")
    starter_questions: Optional[List[str]] = Field(None, title="Starter Questions")

    @validator("starter_questions")
    def validate_starter_questions_len(cls, v: Optional[List[str]]) -> Optional[List[str]]:  # noqa: N805
        if v is not None and len(v) != 4:
            raise ValueError("Exactly four starter questions must be provided when updating")
        return v


class ApplicationOut(BaseModel):
    id: str
    name: str
    description: str
    starter_questions: List[str]
    instructions_uri: Optional[str]
    instructions_version: int
    instructions_updated_at: Optional[str]
    config_settings: Dict[str, Any]
    config_schema: Dict[str, Any]
    created_at: str
    updated_at: str

    class Config:
        orm_mode = True


class InstructionsUpdate(BaseModel):
    content: str = Field(..., title="Markdown Content", min_length=1)


class SettingsUpdate(BaseModel):
    settings: Dict[str, Any] = Field(..., title="Configuration Settings")


class SearchRequest(BaseModel):
    query: str = Field(..., title="Query Text", min_length=1)
    top_k: int = Field(5, ge=1, le=20)


class SearchResultCitation(BaseModel):
    doc_id: str
    file_path: str
    snippet: str


class SearchResultDebug(BaseModel):
    score: float
    metadata: Dict[str, Any]


class SearchResult(BaseModel):
    rank: int
    text: str
    citations: List[SearchResultCitation]
    debug: SearchResultDebug
