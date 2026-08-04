"""
FastAPI backend for the multi‑application RAG platform.

This module wires together the in‑memory database, Pydantic schemas and the
`rag_stub` integration.  It exposes endpoints described in the design
specification v3.3, supporting CRUD operations on applications, editing
instructions and settings, uploading documents and performing searches.

The backend enforces uniqueness of application names, maintains an
instructions file per application and validates configuration settings
against the stored JSON schema.  It does not implement any RAG logic and
delegates ingestion and retrieval to the `rag_stub` functions.

To run the server locally:

    uvicorn answer.backend.main:app --reload

"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, File, HTTPException, Path as PathParam
from fastapi import UploadFile, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from . import database, rag_stub, schemas

try:
    import jsonschema
except ImportError:  # pragma: no cover - jsonschema may not be installed
    jsonschema = None  # type: ignore

app = FastAPI(title="RAG Application Platform", version="3.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in development allow all; tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> database.InMemoryDB:
    return database.db


# Utility: generate instructions file path
def instructions_path(app_id: str) -> Path:
    base = Path(__file__).resolve().parent.parent / "storage" / "instructions" / app_id
    return base / "instructions.md"


@app.get("/api/apps", response_model=List[schemas.ApplicationOut])
def list_applications(db: database.InMemoryDB = Depends(get_db)) -> List[Dict[str, Any]]:
    """Return a list of all applications.  Sorted by last update time descending."""
    return [app.to_dict() for app in db.list_apps()]


@app.post("/api/apps", response_model=schemas.ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(app_in: schemas.ApplicationCreate, db: database.InMemoryDB = Depends(get_db)) -> Dict[str, Any]:
    """Create a new application after validating uniqueness of the name."""
    # Ensure unique name (case‑insensitive)
    if db.get_app_by_name(app_in.name):
        raise HTTPException(status_code=409, detail="Application name already exists")
    app_id = database.generate_uuid()
    now = datetime.datetime.utcnow()
    # Initialize instructions file
    inst_path = instructions_path(app_id)
    inst_path.parent.mkdir(parents=True, exist_ok=True)
    inst_path.write_text("", encoding="utf-8")
    # Persist application
    app_record = database.Application(
        id=app_id,
        name=app_in.name,
        description=app_in.description,
        starter_questions=app_in.starter_questions,
        instructions_uri=str(inst_path),
        instructions_version=1,
        instructions_updated_at=now,
        config_settings=app_in.config_settings,
        config_schema=app_in.config_schema,
        created_at=now,
        updated_at=now,
    )
    db.add_application(app_record)
    return app_record.to_dict()


@app.get("/api/apps/by-name/{name}", response_model=schemas.ApplicationOut)
def get_app_by_name(name: str, db: database.InMemoryDB = Depends(get_db)) -> Dict[str, Any]:
    app_rec = db.get_app_by_name(name)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    return app_rec.to_dict()


@app.get("/api/apps/{app_id}", response_model=schemas.ApplicationOut)
def get_app(app_id: str = PathParam(..., description="Application ID"), db: database.InMemoryDB = Depends(get_db)) -> Dict[str, Any]:
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    return app_rec.to_dict()


@app.patch("/api/apps/{app_id}", response_model=schemas.ApplicationOut)
def update_app(app_id: str, app_update: schemas.ApplicationUpdate, db: database.InMemoryDB = Depends(get_db)) -> Dict[str, Any]:
    """Update an application.  Only internal actors may change the name."""
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    # If renaming, ensure uniqueness
    if app_update.name and app_update.name.lower() != app_rec.name.lower():
        if db.get_app_by_name(app_update.name):
            raise HTTPException(status_code=409, detail="Another application with that name exists")
    # Apply updates
    updates: Dict[str, Any] = {}
    if app_update.name:
        updates["name"] = app_update.name
    if app_update.description is not None:
        updates["description"] = app_update.description
    if app_update.starter_questions is not None:
        updates["starter_questions"] = app_update.starter_questions
    updated_app = db.update_application(app_id, **updates)
    return updated_app.to_dict()


@app.get("/api/apps/{app_id}/instructions")
def read_instructions(app_id: str, db: database.InMemoryDB = Depends(get_db)) -> FileResponse:
    """Return the markdown instructions file for the given application."""
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    path = app_rec.instructions_uri
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Instructions file not found")
    # Use FileResponse so that clients can download raw markdown
    return FileResponse(path, media_type="text/markdown")


@app.patch("/api/apps/{app_id}/instructions", status_code=status.HTTP_204_NO_CONTENT)
def update_instructions(app_id: str, update: schemas.InstructionsUpdate, db: database.InMemoryDB = Depends(get_db)) -> None:
    """Update the instructions markdown for the application."""
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    path = instructions_path(app_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write the file
    path.write_text(update.content, encoding="utf-8")
    now = datetime.datetime.utcnow()
    # Update DB pointer/version/time
    app_rec.instructions_uri = str(path)
    app_rec.instructions_version += 1
    app_rec.instructions_updated_at = now
    app_rec.updated_at = now
    return None


@app.get("/api/apps/{app_id}/settings")
def read_settings(app_id: str, db: database.InMemoryDB = Depends(get_db)) -> Dict[str, Any]:
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    return {
        "settings": app_rec.config_settings,
        "schema": app_rec.config_schema,
    }


@app.patch("/api/apps/{app_id}/settings", status_code=status.HTTP_204_NO_CONTENT)
def update_settings(app_id: str, update: schemas.SettingsUpdate, db: database.InMemoryDB = Depends(get_db)) -> None:
    """Validate and persist configuration settings for an application."""
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    # Validate settings against stored schema using jsonschema if available
    if jsonschema and app_rec.config_schema:
        try:
            jsonschema.validate(instance=update.settings, schema=app_rec.config_schema)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Config settings validation error: {exc}") from exc
    # Persist
    app_rec.config_settings = update.settings
    app_rec.updated_at = datetime.datetime.utcnow()
    return None


@app.post("/api/apps/{app_id}/uploads")
async def upload_documents(
    app_id: str,
    files: List[UploadFile] = File(...),
    db: database.InMemoryDB = Depends(get_db),
) -> Dict[str, Any]:
    """Upload one or more documents and queue them for ingestion."""
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    uploaded_docs: List[str] = []
    # Save each uploaded file and register it in the DB
    documents_for_rag = []
    storage_base = Path(__file__).resolve().parent.parent / "storage" / "uploads" / app_id
    storage_base.mkdir(parents=True, exist_ok=True)
    for file in files:
        doc_id = database.generate_uuid()
        contents = await file.read()
        file_path = storage_base / file.filename
        with open(file_path, "wb") as out_f:
            out_f.write(contents)
        # Create document record
        doc_rec = database.Document(
            id=doc_id,
            app_id=app_id,
            filename=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            size_bytes=len(contents),
            status="uploading",
        )
        db.add_document(doc_rec)
        documents_for_rag.append(file)
        uploaded_docs.append(doc_id)
        # Mark as ready for ingestion
        db.update_document_status(doc_id, status="ingesting")
    # Call rag_subsystem to process files (async not required here, but could be offloaded)
    rag_stub.process_files(
        documents=documents_for_rag,
        config=app_rec.config_settings,
        store=None,
        embed_client=None,
        router=None,
    )
    # Update document statuses
    for doc_id in uploaded_docs:
        db.update_document_status(doc_id, status="ready")
    return {"uploaded": uploaded_docs}


@app.get("/api/apps/{app_id}/docs")
def list_docs(app_id: str, db: database.InMemoryDB = Depends(get_db)) -> List[Dict[str, Any]]:
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    return [doc.to_dict() for doc in db.list_documents(app_id)]


@app.get("/api/apps/{app_id}/docs/{doc_id}")
def get_doc(app_id: str, doc_id: str, db: database.InMemoryDB = Depends(get_db)) -> Dict[str, Any]:
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    doc = db.get_document(doc_id)
    if not doc or doc.app_id != app_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc.to_dict()


@app.delete("/api/apps/{app_id}/docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc(app_id: str, doc_id: str, db: database.InMemoryDB = Depends(get_db)) -> None:
    # Confirm document belongs to app
    doc = db.get_document(doc_id)
    if not doc or doc.app_id != app_id:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete_document(doc_id)
    return None


@app.post("/api/apps/{app_id}/docs/{doc_id}/reingest", status_code=status.HTTP_202_ACCEPTED)
def reingest_doc(app_id: str, doc_id: str, db: database.InMemoryDB = Depends(get_db)) -> Dict[str, Any]:
    """Reingest a single document by calling rag_subsystem.process_files again."""
    doc = db.get_document(doc_id)
    if not doc or doc.app_id != app_id:
        raise HTTPException(status_code=404, detail="Document not found")
    # Construct a minimal file object for rag_subsystem; we can't read the file here
    dummy_file = type("DummyFile", (), {"filename": doc.filename})
    rag_stub.process_files(
        documents=[dummy_file],
        config=db.get_app_by_id(app_id).config_settings,
        store=None,
        embed_client=None,
        router=None,
    )
    # Update status
    db.update_document_status(doc_id, status="ingesting")
    db.update_document_status(doc_id, status="ready")
    return {"reingested": doc_id}


@app.post("/api/apps/{app_id}/search", response_model=List[schemas.SearchResult])
def search(
    app_id: str,
    search_req: schemas.SearchRequest,
    db: database.InMemoryDB = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Perform a search within the specified application.

    The query is passed to the rag_subsystem.retrieve_data function with the
    application ID enforced in the filters to prevent cross‑application
    leakage.  The caller may specify the number of results to return via
    `top_k` (bounded between 1 and 20).
    """
    app_rec = db.get_app_by_id(app_id)
    if not app_rec:
        raise HTTPException(status_code=404, detail="Application not found")
    # Force app_id filter; do not allow override from client
    filters = {"app_id": app_id}
    results = rag_stub.retrieve_data(
        query_text=search_req.query,
        top_k=search_req.top_k,
        filters=filters,
        config=app_rec.config_settings,
        store=None,
        embed_client=None,
        router=None,
    )
    return results
