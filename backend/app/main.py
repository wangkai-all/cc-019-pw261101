"""FastAPI application: metric workbench API."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import definitions as defs_mod
from . import engine
from .db import init_db
from .schemas import (
    CompareIn,
    DefinitionSetIn,
    DrillIn,
    QueryIn,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _app.state.conn = init_db()
    yield


app = FastAPI(title="指标工作台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _conn():
    return app.state.conn


def _error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/stores")
def stores():
    rows = _conn().execute(
        "SELECT store_id, store_name FROM stores ORDER BY store_id"
    ).fetchall()
    return [{"store_id": r[0], "store_name": r[1]} for r in rows]


@app.get("/api/versions")
def versions():
    return defs_mod.list_versions(_conn())


@app.get("/api/versions/{version_id}/definitions")
def version_definitions(version_id: str):
    try:
        return defs_mod.list_definitions(_conn(), version_id)
    except defs_mod.DefinitionError as exc:
        raise _error(exc) from exc


@app.post("/api/validate")
def validate(payload: DefinitionSetIn):
    """Validate a definition snapshot without persisting it (editor preview)."""
    try:
        defs_mod.validate_definition_set(
            [d.model_dump() for d in payload.base],
            [d.model_dump() for d in payload.derived],
        )
    except defs_mod.DefinitionError as exc:
        return {"valid": False, "errors": [str(exc)]}
    return {"valid": True, "errors": []}


@app.post("/api/versions/{source_version_id}/draft")
def create_draft(source_version_id: str, body: dict):
    try:
        return defs_mod.create_draft_from(
            _conn(), source_version_id, body["version_id"], body["label"]
        )
    except (defs_mod.DefinitionError, KeyError) as exc:
        raise _error(exc) from exc


@app.put("/api/versions/{version_id}/definitions")
def save_draft(version_id: str, payload: DefinitionSetIn):
    try:
        defs_mod.save_draft(
            _conn(),
            version_id,
            [d.model_dump() for d in payload.base],
            [d.model_dump() for d in payload.derived],
        )
    except defs_mod.DefinitionError as exc:
        raise _error(exc) from exc
    return {"status": "saved"}


@app.post("/api/versions/{version_id}/publish")
def publish(version_id: str):
    try:
        return defs_mod.publish(_conn(), version_id)
    except defs_mod.DefinitionError as exc:
        raise _error(exc) from exc


@app.post("/api/query")
def query(payload: QueryIn):
    try:
        return engine.run_query(
            _conn(),
            payload.version_id,
            payload.start_date,
            payload.end_date,
            payload.store_id,
        )
    except defs_mod.DefinitionError as exc:
        raise _error(exc) from exc


@app.post("/api/compare")
def compare(payload: CompareIn):
    conn = _conn()
    try:
        left = engine.run_query(
            conn, payload.left_version_id, payload.start_date,
            payload.end_date, payload.store_id,
        )
        right = engine.run_query(
            conn, payload.right_version_id, payload.start_date,
            payload.end_date, payload.store_id,
        )
    except defs_mod.DefinitionError as exc:
        raise _error(exc) from exc
    return {"left": left, "right": right}


@app.post("/api/drill")
def drill(payload: DrillIn):
    try:
        return engine.drill_down(
            _conn(), payload.version_id, payload.date, payload.store_id
        )
    except defs_mod.DefinitionError as exc:
        raise _error(exc) from exc
