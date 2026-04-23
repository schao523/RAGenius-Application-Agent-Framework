"""
Simple in‑memory data store for the RAG web platform.

This module provides minimal persistence for Applications and Documents.  It
stores everything in Python lists and dictionaries so that the FastAPI
backend can run without a real database during development.  In a
production deployment this module should be replaced with calls to a
database layer (e.g. SQLAlchemy or an ORM).  The functions defined here
mirror the behaviours described in the design specification.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def generate_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Application:
    id: str
    name: str
    description: str
    starter_questions: List[str]
    instructions_uri: Optional[str] = None
    instructions_version: int = 0
    instructions_updated_at: Optional[datetime.datetime] = None
    config_settings: Dict[str, any] = field(default_factory=dict)
    config_schema: Dict[str, any] = field(default_factory=dict)
    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)

    def to_dict(self) -> Dict[str, any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "starter_questions": self.starter_questions,
            "instructions_uri": self.instructions_uri,
            "instructions_version": self.instructions_version,
            "instructions_updated_at": self.instructions_updated_at.isoformat() if self.instructions_updated_at else None,
            "config_settings": self.config_settings,
            "config_schema": self.config_schema,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class Document:
    id: str
    app_id: str
    filename: str
    mime_type: str
    size_bytes: int
    language: Optional[str] = "auto"
    tags: List[str] = field(default_factory=list)
    status: str = "pending"
    error_message: Optional[str] = None
    created_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.utcnow)

    def to_dict(self) -> Dict[str, any]:
        return {
            "id": self.id,
            "app_id": self.app_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "language": self.language,
            "tags": self.tags,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class InMemoryDB:
    def __init__(self) -> None:
        self.applications: Dict[str, Application] = {}
        self.documents: Dict[str, Document] = {}

    # Application functions
    def add_application(self, app: Application) -> None:
        self.applications[app.id] = app

    def get_app_by_id(self, app_id: str) -> Optional[Application]:
        return self.applications.get(app_id)

    def get_app_by_name(self, name: str) -> Optional[Application]:
        name_lower = name.strip().lower()
        for app in self.applications.values():
            if app.name.strip().lower() == name_lower:
                return app
        return None

    def list_apps(self) -> List[Application]:
        # Return applications sorted by updated_at descending
        return sorted(self.applications.values(), key=lambda a: a.updated_at, reverse=True)

    def update_application(self, app_id: str, **kwargs) -> Application:
        app = self.get_app_by_id(app_id)
        if not app:
            raise KeyError(f"Application {app_id} not found")
        for key, value in kwargs.items():
            if hasattr(app, key) and value is not None:
                setattr(app, key, value)
        app.updated_at = datetime.datetime.utcnow()
        return app

    # Document functions
    def add_document(self, doc: Document) -> None:
        self.documents[doc.id] = doc

    def list_documents(self, app_id: str) -> List[Document]:
        return [d for d in self.documents.values() if d.app_id == app_id]

    def get_document(self, doc_id: str) -> Optional[Document]:
        return self.documents.get(doc_id)

    def delete_document(self, doc_id: str) -> None:
        if doc_id in self.documents:
            del self.documents[doc_id]

    def update_document_status(self, doc_id: str, status: str, error_message: Optional[str] = None) -> None:
        doc = self.get_document(doc_id)
        if not doc:
            raise KeyError(f"Document {doc_id} not found")
        doc.status = status
        doc.error_message = error_message
        doc.updated_at = datetime.datetime.utcnow()


# Instantiate a global DB instance that can be imported by the API layer
db = InMemoryDB()