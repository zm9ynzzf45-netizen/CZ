"""CZ studio: niche/trend driven short-video planning on top of MoneyPrinterTurbo.

The CZ interface (resource/public/cz) works in two steps so the user stays in
control of what gets paid for:

1. ``build_plan`` asks the configured LLM for a German voice-over script and one
   English video prompt per clip (cheap, no video generation).
2. ``build_video_params`` turns an (optionally edited) plan into the normal
   MoneyPrinterTurbo task parameters with Higgsfield as the clip source.
"""

from __future__ import annotations

import json
import math
import os
import threading
from typing import Any

from loguru import logger

from app.config import config
from app.models.llm_provider import get_llm_provider
from app.models.schema import TaskVideoRequest, VideoAspect
from app.utils import utils

# Providers offered in the CZ settings panel (all exist in MoneyPrinterTurbo).
CZ_LLM_PROVIDERS = ("anthropic", "openai", "gemini", "moonshot", "deepseek")

GERMAN_VOICES = (
    "de-DE-KatjaNeural-Female",
    "de-DE-ConradNeural-Male",
    "de-DE-AmalaNeural-Female",
    "de-DE-KillianNeural-Male",
)

STYLES = (
    "Fotorealistisch, Handyvideo-Look",
    "3D-Cartoon (Pixar)",
    "Hyperreal 3D (Fruit-Island-Stil)",
    "Kino-Trailer",
    "Cyberpunk / Neon-Noir",
)
PLATFORMS = ("TikTok", "Instagram Reels", "YouTube Shorts")
TONES = ("lustig", "episch", "absurd / cringe", "wholesome", "spannend")

# Example trends shown until the user saves their own list.
DEFAULT_TRENDS = [
    {"name": "POV-Alltag eskaliert", "desc": "Normale Situation kippt in Sekunde 2 ins Absurde.", "status": "Beispiel"},
    {"name": "Obst-Drama", "desc": "Hyperreale Früchte in Seifenoper-Szenen.", "status": "Beispiel"},
    {"name": "Vorher/Nachher-Cut", "desc": "Harter Schnitt auf dem Beat, große Verwandlung.", "status": "Beispiel"},
    {"name": "Fake-Doku", "desc": "Tierfilm-Stimme über völlig banale Dinge.", "status": "Beispiel"},
]

_lock = threading.Lock()


def _cz_dir() -> str:
    path = os.path.join(utils.storage_dir(), "cz")
    os.makedirs(path, exist_ok=True)
    return path


def _trends_file() -> str:
    return os.path.join(_cz_dir(), "trends.json")


def get_trends() -> dict:
    try:
        with open(_trends_file(), encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"items": DEFAULT_TRENDS, "updated": "", "examples": True}


def save_trends(items: list[dict], updated: str = "") -> dict:
    clean = []
    for item in items[:20]:
        if not isinstance(item, dict) or not str(item.get("name", "")).strip():
            continue
        clean.append({
            "name": str(item.get("name", "")).strip()[:80],
            "desc": str(item.get("desc", "")).strip()[:240],
            "status": str(item.get("status", "")).strip()[:20],
        })
    data = {"items": clean, "updated": str(updated)[:40]}
    with _lock:
        tmp = _trends_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, _trends_file())
    return data


def _has_value(value: Any) -> bool:
    if isinstance(value, (list, tuple)):
        return any(str(v).strip() for v in value)
    return bool(str(value or "").strip())


def status() -> dict:
    provider_id = str(config.app.get("llm_provider", "")).lower()
    provider = get_llm_provider(provider_id)
    llm_ready = bool(
        provider and _has_value(config.app.get(provider.config_key("api_key"), ""))
    )
    higgsfield_ready = _has_value(config.app.get("higgsfield_api_keys", "")) or bool(
        os.getenv("HF_KEY")
        or (os.getenv("HF_API_KEY") and os.getenv("HF_API_SECRET"))
    )
    return {
        "llm_provider": provider_id,
        "llm_ready": llm_ready,
        "llm_providers": list(CZ_LLM_PROVIDERS),
        "higgsfield_ready": higgsfield_ready,
        "higgsfield_model": config.app.get("higgsfield_model", "")
        or "kling-video/v2.5-turbo/pro/text-to-video",
        "voices": list(GERMAN_VOICES),
        "styles": list(STYLES),
        "platforms": list(PLATFORMS),
        "tones": list(TONES),
    }


def save_settings(body: dict) -> dict:
    """Store keys the CZ settings panel sends. Empty fields keep the old value."""
    provider_id = str(body.get("llm_provider") or "").strip().lower()
    if provider_id:
        if provider_id not in CZ_LLM_PROVIDERS or get_llm_provider(provider_id) is None:
            raise ValueError(f"unsupported llm provider: {provider_id}")
        config.app["llm_provider"] = provider_id
        key = str(body.get("llm_api_key") or "").strip()
        if key:
            config.app[get_llm_provider(provider_id).config_key("api_key")] = key
    hf_key = str(body.get("higgsfield_api_key") or "").strip()
    if hf_key:
        if ":" not in hf_key:
            raise ValueError("Higgsfield key must look like KEY_ID:KEY_SECRET")
        config.app["higgsfield_api_keys"] = hf_key
    model = str(body.get("higgsfield_model") or "").strip().strip("/")
    if model:
        config.app["higgsfield_model"] = model
    config.save_config()
    return status()


def clip_plan(total_seconds: int, clip_seconds: int) -> list[int]:
    total = max(int(total_seconds), 1)
    clip = max(int(clip_seconds), 1)
    count = max(math.ceil(total / clip), 1)
    return [clip] * count


def build_plan_prompt(data: dict) -> str:
    clips = clip_plan(data.get("length", 15), data.get("clip", 5))
    trend = data.get("trend") or {}
    trend_line = (
        f'Trend-Vorlage (nur das FORMAT übernehmen, nie 1:1 kopieren): "{trend.get("name", "")}" – {trend.get("desc", "")}'
        if trend.get("name")
        else "Keine Trend-Vorlage: eigene Idee des Nutzers umsetzen."
    )
    return f"""Du bist Profi für virale KI-Kurzvideos ({data.get('platform', 'TikTok')}).

AUFTRAG
Nische: {data.get('niche', '')}
{trend_line}
Story: {data.get('idea') or '(keine – entwickle eine passende, witzige Story)'}
Figuren: {data.get('chars') or '(frei wählen)'}
Ort: {data.get('place') or '(frei wählen, passend zur Nische)'}
Stil: {data.get('style', STYLES[0])}
Ton: {data.get('tone', TONES[0])}
Gesamtlänge: {sum(clips)} Sekunden = {len(clips)} Clips à {clips[0]} s

REGELN
1. "script": deutscher Sprechertext, so lang, dass er ca. {sum(clips)} Sekunden dauert (ca. {int(sum(clips) * 2.3)} Wörter). Erster Satz ist der Hook (Sekunde 0-2), Ende mit Pointe oder Frage.
2. "clips": genau {len(clips)} englische Video-Prompts, einer pro Clip, in Story-Reihenfolge. Jeder Prompt: ein Absatz, max. 900 Zeichen, beginnt mit Stil-Block ({data.get('style', STYLES[0])}, vertical 9:16), dann identische Figurenbeschreibung in jedem Clip, eine klare Hauptaktion, Kamera-Begriffe (tracking shot, wide-angle 24mm, realistic physics). Clip 1 startet mit Action oder Extreme Close-up.
3. Keine echten Marken, Logos, Prominenten oder Privatpersonen. Kein Blut. Jeder Prompt endet mit "No text, no logos, no watermark."
4. Nische klar erkennbar, ohne andere Gruppen herabzusetzen.

ANTWORT: nur gültiges JSON, ohne Markdown:
{{"title":"kurzer deutscher Titel","hook":"was in Sekunde 0-2 passiert","script":"deutscher Sprechertext","clips":["english prompt clip 1"],"caption":"Post-Caption mit Emojis und Frage","hashtags":"#tag #tag"}}"""


def parse_plan(text: str, expected_clips: int) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM returned no JSON plan")
    plan = json.loads(text[start : end + 1])
    clips = [str(c).strip() for c in plan.get("clips", []) if str(c).strip()]
    if not clips:
        raise ValueError("LLM plan has no clip prompts")
    while len(clips) < expected_clips:
        clips.append(clips[-1])
    return {
        "title": str(plan.get("title", "")).strip()[:120] or "CZ Video",
        "hook": str(plan.get("hook", "")).strip(),
        "script": str(plan.get("script", "")).strip(),
        "clips": clips[:expected_clips],
        "caption": str(plan.get("caption", "")).strip(),
        "hashtags": str(plan.get("hashtags", "")).strip(),
    }


def build_plan(data: dict) -> dict:
    from app.services import llm

    if not str(data.get("niche", "")).strip():
        raise ValueError("Nische fehlt")
    expected = len(clip_plan(data.get("length", 15), data.get("clip", 5)))
    response = llm._generate_response(build_plan_prompt(data))
    plan = parse_plan(response, expected)
    logger.info(f"cz plan created: title={plan['title']!r}, clips={len(plan['clips'])}")
    return plan


def build_video_params(data: dict) -> TaskVideoRequest:
    plan = data.get("plan") or {}
    script = str(plan.get("script", "")).strip()
    clips = [str(c).strip() for c in plan.get("clips", []) if str(c).strip()]
    if not script or not clips:
        raise ValueError("Plan braucht Sprechertext und mindestens einen Clip-Prompt")
    clip_seconds = int(data.get("clip", 5))
    voice = str(data.get("voice") or GERMAN_VOICES[0])
    if voice not in GERMAN_VOICES:
        voice = GERMAN_VOICES[0]
    return TaskVideoRequest(
        video_subject=str(plan.get("title") or data.get("niche") or "CZ Video")[:120],
        video_script=script,
        video_terms=clips,
        video_aspect=VideoAspect.portrait,
        video_source="higgsfield",
        video_clip_duration=max(1, min(clip_seconds, 15)),
        video_concat_mode="sequential",
        video_count=1,
        video_language="de-DE",
        voice_name=voice,
        subtitle_enabled=bool(data.get("subs", True)),
        subtitle_position="bottom",
    )


def _projects_dir() -> str:
    path = os.path.join(_cz_dir(), "projects")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_project_id(project_id: str) -> str:
    clean = "".join(ch for ch in str(project_id) if ch.isalnum() or ch in "-_")[:64]
    if not clean:
        raise ValueError("invalid project id")
    return clean


def save_project(body: dict) -> dict:
    """Create or update one saved CZ project (inputs, plan, task id)."""
    import time

    project_id = _safe_project_id(body.get("id") or f"p-{int(time.time() * 1000)}")
    path = os.path.join(_projects_dir(), f"{project_id}.json")
    existing: dict = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            existing = json.load(handle)
    project = {
        "id": project_id,
        "created": existing.get("created") or int(time.time() * 1000),
        "name": str(body.get("name") or existing.get("name") or "Projekt")[:120],
        "inputs": body.get("inputs", existing.get("inputs", {})),
        "plan": body.get("plan", existing.get("plan")),
        "task_id": str(body.get("task_id") or existing.get("task_id") or ""),
    }
    with _lock:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(project, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    return project


def list_projects(limit: int = 50) -> list[dict]:
    projects = []
    for name in os.listdir(_projects_dir()):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(_projects_dir(), name), encoding="utf-8") as handle:
                projects.append(json.load(handle))
        except (OSError, ValueError):
            continue
    projects.sort(key=lambda p: p.get("created", 0), reverse=True)
    return projects[:limit]


def delete_project(project_id: str) -> None:
    path = os.path.join(_projects_dir(), f"{_safe_project_id(project_id)}.json")
    if os.path.exists(path):
        os.remove(path)
