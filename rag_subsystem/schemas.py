"""Shared schemas for RAG subsystem."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import datetime


class ValidationError(Exception):
    """Raised for validation issues with user input."""

    def __init__(self, path: str, msg: str, code: str = "validation_error") -> None:
        super().__init__(msg)
        self.path = path
        self.msg = msg
        self.code = code

    def to_response(self) -> Dict[str, Any]:
        return {"errors": [{"path": self.path, "msg": self.msg, "code": self.code}]}


class ServiceError(Exception):
    """Raised for unexpected service errors."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_response(self) -> Dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


@dataclass
class Block:
    doc_id: str
    type: str
    text: Optional[str] = None
    table_raw: Optional[List[List[str]]] = None
    image_ref: Optional[str] = None
    ocr_text: Optional[str] = None
    caption: Optional[str] = None
    section_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str
    text: str
    section_path: Optional[str]
    order: int
    language: str
    embedding_model: str
    namespace: str
    embedding: List[float]
    metadata: Dict[str, Any]
    hash: str


@dataclass
class Document:
    doc_id: str
    blocks: List[Block]
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    version: str = "0.0.0"


@dataclass
class IngestResult:
    doc_id: str
    inserted: int
    skipped_too_short_count: int
    skipped_boilerplate_count: int
    skipped_near_dup_count: int


@dataclass
class RetrievalCandidate:
    chunk: Chunk
    score: float
    source: str


@dataclass
class RetrievalResult:
    query: str
    results: List[RetrievalCandidate]
    debug: Dict[str, Any]
