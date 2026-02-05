from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import load_config
from .content import load_content
from .models import ApiResponse, Message
from .orchestrator import (
    action_select,
    build_response,
    chat,
    create_initial_state,
    day_end,
    day_start,
)
from .storage import InMemoryStore

app = FastAPI(title="Forgotten Girl Orchestrator")
root_path = Path(__file__).resolve().parent.parent
config = load_config(root_path)
content = load_content(root_path)
store = InMemoryStore()


class ActionRequest(BaseModel):
    session_id: str
    location: str
    time_slot: str


class ChatRequest(BaseModel):
    session_id: str
    text: str


class SessionRequest(BaseModel):
    session_id: str


@app.post("/api/session/new", response_model=ApiResponse)
def new_session() -> ApiResponse:
    state = create_initial_state(config)
    store.save(state)
    messages = [Message(role="system", content="新的旅程开始。", kind="session_start")]
    return build_response(state, messages, [])


@app.get("/api/state", response_model=ApiResponse)
def get_state(session_id: str) -> ApiResponse:
    if not store.exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    state = store.get(session_id)
    return build_response(state, [], [])


@app.post("/api/day/start", response_model=ApiResponse)
def api_day_start(request: SessionRequest) -> ApiResponse:
    if not store.exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    state = store.get(request.session_id)
    messages = day_start(state, config)
    store.save(state)
    return build_response(state, messages, [])


@app.post("/api/action/select", response_model=ApiResponse)
def api_action_select(request: ActionRequest) -> ApiResponse:
    if not store.exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    state = store.get(request.session_id)
    messages, ui_hints = action_select(state, content, request.location, request.time_slot)
    store.save(state)
    return build_response(state, messages, ui_hints)


@app.post("/api/chat", response_model=ApiResponse)
def api_chat(request: ChatRequest) -> ApiResponse:
    if not store.exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    state = store.get(request.session_id)
    messages = chat(state, request.text, content)
    store.save(state)
    return build_response(state, messages, [])


@app.post("/api/day/end", response_model=ApiResponse)
def api_day_end(request: SessionRequest) -> ApiResponse:
    if not store.exists(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    state = store.get(request.session_id)
    messages = day_end(state, config, content)
    store.save(state)
    return build_response(state, messages, [])
