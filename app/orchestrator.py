from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .config import ConfigBundle
from .content import ContentBundle
from .models import (
    ApiResponse,
    Caps,
    CurrentContext,
    Fragment,
    FragmentCandidate,
    GamePhase,
    GameState,
    Message,
    ProactiveState,
    Resources,
    Trigger,
    TriggerState,
)


@dataclass
class RollResult:
    success: bool
    roll: float
    probability: float


def stable_seed(*parts: Any) -> int:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def roll_with_pity(p0: float, dp: float, p_max: float, exposures: int, seed: int) -> RollResult:
    probability = min(p_max, p0 + exposures * dp)
    rng = hashlib.sha256(str(seed).encode("utf-8")).digest()
    roll = int.from_bytes(rng[:8], "big") / 2**64
    return RollResult(success=roll <= probability, roll=roll, probability=probability)


def select_weighted(items: List[Dict[str, Any]], seed: int) -> Optional[Dict[str, Any]]:
    if not items:
        return None
    total = sum(item.get("base_weight", 1.0) for item in items)
    if total <= 0:
        return items[0]
    rng_value = (seed % 10_000) / 10_000
    threshold = rng_value * total
    cumulative = 0.0
    for item in items:
        cumulative += item.get("base_weight", 1.0)
        if cumulative >= threshold:
            return item
    return items[-1]


def create_initial_state(config: ConfigBundle) -> GameState:
    session_id = str(uuid.uuid4())
    resources = Resources(**config.resources)
    caps = Caps(**config.caps)
    return GameState(
        session_id=session_id,
        resources=resources,
        caps=caps,
        max_runs=int(config.run.get("max_runs", 5)),
        run_seed=stable_seed(session_id, "run_seed"),
    )


def day_start(state: GameState, config: ConfigBundle) -> List[Message]:
    state.resources = Resources(**config.resources)
    state.daily_fragment_count = 0
    state.daily_proactive_count = 0
    state.current_context = CurrentContext()
    return [Message(role="system", content=f"第{state.day_index}天开始。", kind="day_start")]


def action_select(
    state: GameState,
    content: ContentBundle,
    location: str,
    time_slot: str,
    stage_id: str = "event_flow",
) -> Tuple[List[Message], List[str]]:
    messages: List[Message] = []
    ui_hints: List[str] = []
    if state.resources.ap <= 0:
        messages.append(Message(role="system", content="体力不足，无法行动。", kind="warning"))
        return messages, ui_hints
    state.resources.ap -= 1
    state.current_context = CurrentContext(location=location, time_slot=time_slot, stage_id=stage_id)

    fragment_message = fragment_trigger_check(state, location, stage_id)
    if fragment_message:
        messages.append(fragment_message)
    event = select_event(content, location, time_slot, state)
    if event:
        state.current_context.event_id = event.get("event_id")
        if state.current_context.event_id:
            state.event_history.append(state.current_context.event_id)
        messages.append(Message(role="narrator", content=event.get("intro", ""), kind="event_intro"))
        for choice in event.get("choice_points", []):
            ui_hints.extend(choice.get("options", []))
        if fragment_message is None:
            candidate_hooks = event.get("fragment_hooks", [])
            for hook in candidate_hooks:
                state.fragment_candidates_today.append(
                    FragmentCandidate(
                        anchor=hook.get("anchor", ""),
                        emotion_tag=hook.get("emotion_tag", "neutral"),
                        score=hook.get("base_score", 0.2),
                        reveal_level=hook.get("reveal_level", 1),
                        trigger_hint=hook.get("trigger_hint", {}),
                    )
                )
        messages.append(Message(role="narrator", content=event.get("outro", ""), kind="event_outro"))
    else:
        messages.append(Message(role="narrator", content="这里没有发生特别的事。", kind="event_fallback"))

    proactive_messages = proactive_check(state, content, stage_id)
    messages.extend(proactive_messages)
    return messages, ui_hints


def chat(state: GameState, text: str, content: ContentBundle, stage_id: str = "chat") -> List[Message]:
    messages: List[Message] = []
    if state.resources.chat_turns <= 0:
        return [Message(role="system", content="今天聊得够多了。", kind="warning")]
    state.resources.chat_turns -= 1
    state.fragment_candidates_today.append(
        FragmentCandidate(
            anchor="对话",
            emotion_tag="curious",
            score=0.3,
            reveal_level=1,
            trigger_hint={"kind": "location", "value": state.current_context.location or ""},
        )
    )
    messages.append(Message(role="npc", content="她认真听着，像在拼凑新的线索。", kind="chat"))
    messages.extend(proactive_check(state, content, stage_id))
    return messages


def day_end(state: GameState, config: ConfigBundle, content: ContentBundle) -> List[Message]:
    messages: List[Message] = []
    fragment = pick_fragment(state, config)
    if fragment:
        state.fragments_active.append(fragment)
        messages.append(Message(role="system", content="有新的记忆碎片留下。", kind="fragment_gain"))
    state.fragment_candidates_today.clear()
    state.current_context = CurrentContext()
    state.day_index += 1

    if state.day_index > int(config.run.get("days_per_run", 7)):
        state.game_phase = GamePhase.RUN_END
        messages.extend(run_end(state, config, content))

    return messages


def run_end(state: GameState, config: ConfigBundle, content: ContentBundle) -> List[Message]:
    messages: List[Message] = [Message(role="system", content=f"第{state.run_index}轮结束。", kind="run_end")]
    if state.fragments_active:
        deep_fragment = max(state.fragments_active, key=lambda fragment: fragment.salience_score)
        state.deep_fragments = [deep_fragment]
    state.fragments_active = []
    if state.run_index >= state.max_runs:
        state.game_phase = GamePhase.FINAL_END
        messages.extend(final_ending(state, content))
        state.game_phase = GamePhase.ENDED
        return messages
    state.run_index += 1
    state.day_index = 1
    state.game_phase = GamePhase.RUNNING
    state.run_seed = stable_seed(state.session_id, "run_seed", state.run_index)
    state.event_history.clear()
    return messages


def final_ending(state: GameState, content: ContentBundle) -> List[Message]:
    ending = content.endings[0] if content.endings else {"scenes": ["故事落幕。"]}
    scenes = ending.get("scenes", [])
    return [Message(role="narrator", content=scene, kind="final_ending") for scene in scenes]


def pick_fragment(state: GameState, config: ConfigBundle) -> Optional[Fragment]:
    if not state.fragment_candidates_today:
        return None
    best = max(state.fragment_candidates_today, key=lambda candidate: candidate.score)
    trigger_hint = best.trigger_hint or {"kind": "location", "value": state.current_context.location or ""}
    fragment_id = f"fragment_{state.run_index}_{state.day_index}_{len(state.fragments_active) + 1}"
    pity_defaults = config.pity.get("fragment", {})
    trigger_state = TriggerState(
        exposures=0,
        p0=pity_defaults.get("p0", 0.2),
        dp=pity_defaults.get("dp", 0.15),
        p_max=pity_defaults.get("p_max", 0.85),
    )
    return Fragment(
        fragment_id=fragment_id,
        day_created=state.day_index,
        run_created=state.run_index,
        anchor=best.anchor,
        emotion_tag=best.emotion_tag,
        salience_score=best.score,
        reveal_level=best.reveal_level,
        trigger=Trigger(kind=trigger_hint.get("kind", "location"), value=trigger_hint.get("value", "")),
        trigger_state=trigger_state,
    )


def fragment_trigger_check(state: GameState, location: str, stage_id: str) -> Optional[Message]:
    if state.daily_fragment_count >= state.caps.daily_fragment_cap:
        return None
    eligible = [
        fragment
        for fragment in state.fragments_active
        if not fragment.consumed
        and fragment.trigger.kind == "location"
        and fragment.trigger.value == location
        and fragment.trigger_state.cooldown_until_day <= state.day_index
    ]
    if not eligible:
        return None
    fragment = max(
        eligible,
        key=lambda item: item.salience_score + item.trigger_state.exposures * 0.1,
    )
    last_day = fragment.trigger_state.last_check_day
    last_stage = fragment.trigger_state.last_check_stage
    if last_day == state.day_index and last_stage == stage_id:
        return None

    seed = stable_seed(state.session_id, state.run_index, state.day_index, stage_id, fragment.fragment_id)
    result = roll_with_pity(
        fragment.trigger_state.p0,
        fragment.trigger_state.dp,
        fragment.trigger_state.p_max,
        fragment.trigger_state.exposures,
        seed,
    )
    fragment.trigger_state.last_check_day = state.day_index
    fragment.trigger_state.last_check_stage = stage_id
    trace_entry = {
        "kind": "fragment_roll",
        "fragment_id": fragment.fragment_id,
        "probability": result.probability,
        "roll": result.roll,
        "success": result.success,
        "exposures": fragment.trigger_state.exposures,
        "stage_id": stage_id,
    }
    state.trace_log.append(trace_entry)

    if result.success:
        fragment.trigger_state.exposures = 0
        fragment.consumed = fragment.one_shot
        state.daily_fragment_count += 1
        return Message(
            role="narrator",
            content=f"她触碰到{fragment.anchor}时，脑海里闪过模糊的画面。",
            kind="fragment_event",
        )
    fragment.trigger_state.exposures += 1
    intensity = min(fragment.trigger_state.exposures, 3)
    micro_lines = [
        "她短暂失神，像是有什么要浮上来又退回去。",
        "她按住太阳穴，似乎听见极远处的回声。",
        "她呼吸一滞，眼神里有更深的空洞。",
    ]
    return Message(role="narrator", content=micro_lines[intensity - 1], kind="micro_flashback")


def proactive_check(state: GameState, content: ContentBundle, stage_id: str) -> List[Message]:
    if state.daily_proactive_count >= state.caps.daily_proactive_cap:
        return []
    if state.resources.npc_initiative <= 0:
        return []
    eligible = [
        hook
        for hook in content.hooks
        if hook_matches_conditions(hook, state)
        and state.proactive_state.hook_cooldowns.get(hook.get("hook_id", ""), 0) <= state.day_index
    ]
    if not eligible:
        return []
    hook = select_hook(eligible, state, stage_id)
    if hook is None:
        return []
    hook_id = hook.get("hook_id", "hook")
    exposures = state.proactive_state.hook_exposures.get(hook_id, 0)
    seed = stable_seed(state.session_id, state.run_index, state.day_index, stage_id, hook_id)
    result = roll_with_pity(hook.get("p0", 0.2), hook.get("dp", 0.1), hook.get("p_max", 0.7), exposures, seed)
    state.trace_log.append(
        {
            "kind": "proactive_roll",
            "hook_id": hook_id,
            "probability": result.probability,
            "roll": result.roll,
            "success": result.success,
            "exposures": exposures,
            "stage_id": stage_id,
        }
    )
    if not result.success:
        state.proactive_state.hook_exposures[hook_id] = exposures + 1
        return []
    state.proactive_state.hook_exposures[hook_id] = 0
    state.proactive_state.hook_cooldowns[hook_id] = state.day_index + hook.get("cooldown_days", 1)
    state.resources.npc_initiative -= 1
    state.daily_proactive_count += 1
    payload = hook.get("payload_template", {})
    message = Message(
        role="npc",
        content=payload.get("text", "她似乎想主动说点什么。"),
        kind=f"proactive_{hook.get('kind', 'soft')}",
        options=payload.get("options", []),
    )
    state.pending_npc_messages.append(message)
    return []


def hook_matches_conditions(hook: Dict[str, Any], state: GameState) -> bool:
    conditions = hook.get("conditions", {}) or {}
    location = conditions.get("location")
    time_slot = conditions.get("time_slot")
    min_day = conditions.get("min_day")
    max_day = conditions.get("max_day")
    if location and location != state.current_context.location:
        return False
    if time_slot and time_slot != state.current_context.time_slot:
        return False
    if min_day and state.day_index < min_day:
        return False
    if max_day and state.day_index > max_day:
        return False
    return True


def select_hook(eligible: List[Dict[str, Any]], state: GameState, stage_id: str) -> Optional[Dict[str, Any]]:
    weighted: List[Tuple[Dict[str, Any], float]] = []
    for hook in eligible:
        hook_id = hook.get("hook_id", "")
        exposure = state.proactive_state.hook_exposures.get(hook_id, 0)
        weight = hook.get("base_weight", 1.0) + exposure * 0.2
        weighted.append((hook, max(weight, 0.1)))
    total = sum(weight for _, weight in weighted)
    if total <= 0:
        return None
    seed = stable_seed(state.session_id, state.run_index, state.day_index, stage_id, "hook_select")
    rng_value = (seed % 10_000) / 10_000
    threshold = rng_value * total
    cumulative = 0.0
    for hook, weight in weighted:
        cumulative += weight
        if cumulative >= threshold:
            return hook
    return weighted[-1][0]


def select_event(content: ContentBundle, location: str, time_slot: str, state: GameState) -> Optional[Dict[str, Any]]:
    candidates = [
        event
        for event in content.events
        if event.get("location") == location and event.get("time_slot") == time_slot
    ]
    weighted: List[Dict[str, Any]] = []
    last_event_id = state.event_history[-1] if state.event_history else None
    for event in candidates:
        weight = event.get("base_weight", 1.0)
        if last_event_id and event.get("event_id") == last_event_id:
            weight *= 0.5
        adjusted = dict(event)
        adjusted["base_weight"] = weight
        weighted.append(adjusted)
    seed = stable_seed(state.session_id, state.run_index, state.day_index, location, time_slot)
    return select_weighted(weighted, seed)


def build_response(state: GameState, messages: List[Message], ui_hints: List[str]) -> ApiResponse:
    trace_id = str(uuid.uuid4())
    if state.pending_npc_messages:
        messages.extend(state.pending_npc_messages)
        state.pending_npc_messages.clear()
    return ApiResponse(state=state, messages=messages, ui_hints=ui_hints, trace_id=trace_id)
