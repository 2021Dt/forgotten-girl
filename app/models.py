from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GamePhase(str, Enum):
    RUNNING = "RUNNING"
    RUN_END = "RUN_END"
    FINAL_END = "FINAL_END"
    ENDED = "ENDED"


class TriggerState(BaseModel):
    exposures: int = 0
    p0: float = 0.2
    dp: float = 0.15
    p_max: float = 0.85
    last_check_day: Optional[int] = None
    last_check_stage: Optional[str] = None
    cooldown_until_day: int = 0


class Trigger(BaseModel):
    kind: str
    value: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class Fragment(BaseModel):
    fragment_id: str
    version: int = 1
    day_created: int
    run_created: int
    anchor: str
    emotion_tag: str
    salience_score: float
    reveal_level: int
    trigger: Trigger
    trigger_state: TriggerState
    one_shot: bool = True
    consumed: bool = False
    reward: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class FragmentCandidate(BaseModel):
    anchor: str
    emotion_tag: str
    score: float
    reveal_level: int
    trigger_hint: Dict[str, Any]


class ProactiveState(BaseModel):
    hook_exposures: Dict[str, int] = Field(default_factory=dict)
    hook_cooldowns: Dict[str, int] = Field(default_factory=dict)


class Resources(BaseModel):
    ap: int
    chat_turns: int
    key_q: int
    npc_initiative: int


class Caps(BaseModel):
    daily_fragment_cap: int
    daily_proactive_cap: int


class Stats(BaseModel):
    affection: int = 0
    trust: int = 0
    stress: int = 0
    clarity: int = 0


class CurrentContext(BaseModel):
    event_id: Optional[str] = None
    location: Optional[str] = None
    time_slot: Optional[str] = None
    stage_id: Optional[str] = None


class Message(BaseModel):
    role: str
    content: str
    kind: str
    options: List[str] = Field(default_factory=list)


class GameState(BaseModel):
    session_id: str
    state_version: int = 1
    game_phase: GamePhase = GamePhase.RUNNING
    run_index: int = 1
    max_runs: int = 5
    day_index: int = 1
    run_seed: int = 0
    resources: Resources
    caps: Caps
    stats: Stats = Field(default_factory=Stats)
    current_context: CurrentContext = Field(default_factory=CurrentContext)
    fragments_active: List[Fragment] = Field(default_factory=list)
    deep_fragments: List[Fragment] = Field(default_factory=list)
    fragment_candidates_today: List[FragmentCandidate] = Field(default_factory=list)
    proactive_state: ProactiveState = Field(default_factory=ProactiveState)
    pending_npc_messages: List[Message] = Field(default_factory=list)
    route_flags_local: List[str] = Field(default_factory=list)
    route_flags_global: List[str] = Field(default_factory=list)
    meta_progress: Dict[str, Any] = Field(default_factory=dict)
    inventory: Dict[str, int] = Field(default_factory=dict)
    history_refs: Dict[str, Any] = Field(default_factory=dict)
    trace_log: List[Dict[str, Any]] = Field(default_factory=list)
    daily_fragment_count: int = 0
    daily_proactive_count: int = 0
    event_history: List[str] = Field(default_factory=list)


class ApiResponse(BaseModel):
    state: GameState
    messages: List[Message] = Field(default_factory=list)
    ui_hints: List[str] = Field(default_factory=list)
    trace_id: str
