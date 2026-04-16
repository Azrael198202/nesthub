"""Lightweight TV Box UI entrypoint.

This module avoids importing optional runtime-only dependencies at import time.
If `fastapi` or `uvicorn` are missing, `main()` will print a friendly message and exit
instead of raising an import error during module import.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any


def _create_app() -> Any:
    """Create and return a FastAPI app instance.

    The import for FastAPI is performed lazily so importing this module does not
    require FastAPI to be installed unless `main()` is executed.
    """
    try:
        from fastapi import FastAPI, Request
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse, JSONResponse
    except Exception as exc:  # pragma: no cover - environment edge-case
        raise ImportError("fastapi is required to run the TV Box UI") from exc

    # Keep Request resolvable for runtime annotation evaluation when
    # `from __future__ import annotations` is enabled.
    globals()["Request"] = Request

    from pathlib import Path
    from urllib.parse import unquote

    from nethub_runtime.tvbox.components.i18n import (
        build_settings_i18n,
        get_supported_languages,
        normalize_locale,
    )

    app = FastAPI()

    # Serve bundled static dashboard if present
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists() and static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    index_file = static_dir / "index.html"
    repo_root = Path(__file__).resolve().parents[3]
    demo_dir = repo_root / "examples" / "ui"

    def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return copy.deepcopy(fallback)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return copy.deepcopy(fallback)

    dashboard_fallback: dict[str, Any] = {
        "hero": {"title": "HomeHub", "subtitle": "AI Box", "tagline": "Demo mode"},
        "boxProfile": {"networkState": "Online", "pairedClients": 1},
        "householdModules": [],
        "activeAgents": [],
        "timelineEvents": [],
        "modelProviders": [],
        "skillCatalog": [],
        "pairingSession": {"code": "DEMO", "expiresInSeconds": 600, "qrPayload": "homehub://pair?code=DEMO"},
        "relayMessages": [],
        "voiceProfile": {"wakeWord": "Hey HomeHub", "sttProvider": "demo", "ttsProvider": "demo", "locale": "en-US"},
        "audioStack": {
            "stt": {"provider": "demo", "primaryModel": "demo", "fallbackModel": "demo", "mode": "demo"},
            "tts": {"provider": "demo", "primaryModel": "demo", "fallbackModel": "demo", "mode": "demo"},
            "recommendedRealtime": "demo",
        },
        "audioProviders": {
            "selected": {"stt": "demo", "tts": "demo"},
            "catalog": {"demo": {"label": "Demo", "editable": True, "stt": {"defaultModel": "demo", "fallbackModel": "demo", "runtime": "local"}, "tts": {"defaultModel": "demo", "fallbackModel": "demo", "runtime": "local"}}},
            "secrets": {"googleConfigured": False, "openaiConfigured": False, "googleSource": "missing", "openaiSource": "missing"},
            "counts": {"total": 1, "editable": 1},
        },
        "modelCatalog": [],
        "runtimeProfile": {"label": "Demo", "summary": "Demo runtime", "localRoles": [], "cloudRoles": [], "localDetected": []},
        "assistantAvatar": {"mode": "house", "customModelUrl": "", "backupMode": "house", "defaultMode": "house", "label": "Demo", "techStack": []},
        "languageSettings": {"supported": [{"code": "zh-CN", "label": "简体中文", "sample": "你好"}], "current": "zh-CN"},
        "weather": {"location": "Tokyo", "condition": "Cloudy", "temperatureC": 20, "highC": 23, "lowC": 16, "gpsEnabled": False},
        "systemStatus": {"mode": "ready", "boxHealth": "Healthy"},
        "conversation": [],
        "lastVoiceRoute": {},
        "semanticMemory": {},
        "features": [],
        "agentTypes": [],
        "bootstrap": {"approved": True, "inProgress": False, "blocking": False, "completed": True, "message": "Demo mode"},
        "externalChannels": {"mailConfig": {}, "mail": {"inbox": [], "outbox": [], "lastSyncAt": ""}, "apps": {"line": {"inbox": [], "outbox": []}, "wechatOfficial": {"inbox": [], "outbox": []}}, "recentActions": []},
        "assistantMemory": {"dueReminders": [], "pendingReminders": [], "upcomingEvents": [], "recentActions": []},
        "customAgents": [],
        "customAgentRecentActions": [],
        "studyPlanAgents": [],
        "studyPlanRecentActions": [],
        "pendingVoiceClarification": None,
    }
    cortex_fallback: dict[str, Any] = {"ok": True, "seed": {"agentId": "demo", "agentName": "Demo Brain", "stage": "shared-brain"}, "request": {}, "item": {}}

    dashboard_state = _load_json(demo_dir / "dashboard.demo.json", dashboard_fallback)
    cortex_template = _load_json(demo_dir / "cortex_unpacked.demo.json", cortex_fallback)

    def _dashboard_snapshot() -> dict[str, Any]:
        snapshot = copy.deepcopy(dashboard_state)
        supported_languages = get_supported_languages()
        current = normalize_locale(
            snapshot.get("languageSettings", {}).get("current", "en-US"),
            "en-US",
        )
        snapshot.setdefault("languageSettings", {})
        snapshot["languageSettings"]["supported"] = supported_languages
        snapshot["languageSettings"]["current"] = current
        snapshot.setdefault("voiceProfile", {})
        snapshot["voiceProfile"]["locale"] = current
        return snapshot

    @app.get("/")
    def home():
        if index_file.exists():
            return FileResponse(index_file)
        return {"status": "TV Box UI running"}

    # API: return last N lines from the tvbox log file (if present)
    @app.get("/api/logs/latest")
    def logs_latest(lines: int = 200):
        try:
            from nethub_runtime.config.settings import ensure_app_dirs
        except Exception:
            return {"error": "log not available"}

        paths = ensure_app_dirs()
        logs_dir = paths.get("logs")
        if logs_dir is None:
            return {"error": "log dir not configured"}

        log_file = logs_dir / "tvbox.log"
        if not log_file.exists():
            return {"lines": []}

        # read last N lines efficiently
        try:
            with open(log_file, "rb") as fh:
                fh.seek(0, 2)
                end = fh.tell()
                size = 1024
                data = b""
                while end > 0 and data.count(b"\n") <= lines:
                    read_size = min(size, end)
                    fh.seek(end - read_size)
                    chunk = fh.read(read_size)
                    data = chunk + data
                    end -= read_size
                text = data.decode("utf-8", errors="replace")
                all_lines = text.splitlines()
                return {"lines": all_lines[-lines:]}
        except Exception as exc:
            return {"error": str(exc)}

    @app.get("/api/dashboard")
    def api_dashboard():
        return _dashboard_snapshot()

    @app.get("/api/i18n/settings")
    def api_i18n_settings(locale: str | None = None):
        resolved = normalize_locale(locale or dashboard_state.get("languageSettings", {}).get("current", "en-US"), "en-US")
        return build_settings_i18n(unquote(resolved))

    @app.get("/api/bootstrap/status")
    def api_bootstrap_status():
        return copy.deepcopy(dashboard_state.get("bootstrap", {}))

    @app.post("/api/bootstrap/approve")
    async def api_bootstrap_approve():
        bootstrap = dashboard_state.setdefault("bootstrap", {})
        bootstrap.update({"approved": True, "inProgress": False, "blocking": False, "completed": True, "message": "Approved in demo mode"})
        return {"ok": True, "bootstrap": copy.deepcopy(bootstrap)}

    @app.get("/api/custom-agents")
    def api_custom_agents():
        return {
            "items": copy.deepcopy(dashboard_state.get("customAgents", [])),
            "recentActions": copy.deepcopy(dashboard_state.get("customAgentRecentActions", [])),
        }

    @app.post("/api/cortex/unpacked")
    async def api_cortex_unpacked(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        payload = copy.deepcopy(cortex_template)
        payload["request"] = {
            "command": str(body.get("command", payload.get("request", {}).get("command", ""))),
            "locale": str(body.get("locale", payload.get("request", {}).get("locale", dashboard_state.get("languageSettings", {}).get("current", "zh-CN")))),
            "taskType": str(body.get("taskType", payload.get("request", {}).get("taskType", "general_chat"))),
            "inputModes": body.get("inputModes", payload.get("request", {}).get("inputModes", ["text"])),
            "requireArtifacts": bool(body.get("requireArtifacts", False)),
            "requiresNetwork": bool(body.get("requiresNetwork", False)),
            "speakReply": bool(body.get("speakReply", False)),
        }
        return payload

    @app.post("/api/device/location")
    async def api_device_location(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        weather = dashboard_state.setdefault("weather", {})
        weather["gpsEnabled"] = True
        weather["location"] = body.get("label") or weather.get("location") or "Detected"
        return {"ok": True, "weather": copy.deepcopy(weather)}

    @app.post("/api/memory/reminders/complete")
    async def api_complete_reminder(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        reminder_id = str(body.get("id", ""))
        memory = dashboard_state.setdefault("assistantMemory", {})
        due = [item for item in memory.get("dueReminders", []) if str(item.get("id", "")) != reminder_id]
        pending = [item for item in memory.get("pendingReminders", []) if str(item.get("id", "")) != reminder_id]
        memory["dueReminders"] = due
        memory["pendingReminders"] = pending
        return {"ok": True, "assistantMemory": copy.deepcopy(memory)}

    @app.post("/api/settings/language")
    async def api_settings_language(request: Request):
        language = ""
        try:
            body = await request.json()
            if isinstance(body, dict):
                language = str(body.get("language", "")).strip()
        except Exception:
            language = ""

        if not language:
            try:
                form = await request.form()
                language = str(form.get("language", "")).strip()
            except Exception:
                language = ""

        if not language:
            language = str(
                dashboard_state.get("languageSettings", {}).get("current", "en-US")
            ).strip() or "en-US"

        language = normalize_locale(language, "en-US")
        dashboard_state.setdefault("languageSettings", {})["current"] = language
        dashboard_state.setdefault("voiceProfile", {})["locale"] = language
        return {"ok": True, "language": language}

    @app.post("/api/settings/audio")
    async def api_settings_audio(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        selected = dashboard_state.setdefault("audioProviders", {}).setdefault("selected", {})
        if body.get("sttProvider"):
            selected["stt"] = body["sttProvider"]
        if body.get("ttsProvider"):
            selected["tts"] = body["ttsProvider"]
        return {"ok": True, "sttProvider": selected.get("stt"), "ttsProvider": selected.get("tts")}

    @app.post("/api/settings/avatar")
    async def api_settings_avatar(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        avatar = dashboard_state.setdefault("assistantAvatar", {})
        avatar["mode"] = str(body.get("mode", avatar.get("mode", "house")))
        if body.get("customModelUrl") is not None:
            avatar["customModelUrl"] = str(body.get("customModelUrl", ""))
        return {"ok": True, "mode": avatar.get("mode"), "customModelUrl": avatar.get("customModelUrl", "")}

    @app.post("/api/settings/audio-provider")
    async def api_settings_audio_provider():
        return {"ok": True}

    @app.post("/api/settings/secrets")
    async def api_settings_secrets():
        return {"ok": True, "googleConfigured": False, "openaiConfigured": True, "mailConfigured": True}

    @app.post("/api/external-channels/email/sync")
    async def api_mail_sync():
        return {"ok": True, "imported": 2}

    @app.post("/api/external-channels/email/send")
    async def api_mail_send():
        return {"ok": True}

    @app.post("/api/audio/transcribe")
    async def api_audio_transcribe():
        return {"ok": True, "transcript": "这是一条演示转写文本", "detectedLocale": dashboard_state.get("languageSettings", {}).get("current", "zh-CN")}

    @app.post("/api/voice/chat")
    async def api_voice_chat(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        message = str(body.get("message", "")).strip()
        locale = str(body.get("locale", dashboard_state.get("languageSettings", {}).get("current", "zh-CN")))
        conversation = dashboard_state.setdefault("conversation", [])
        if message:
            conversation.append({"speaker": "You", "text": message, "time": "", "createdAt": ""})
        reply = "这是 Demo 回复：页面已迁移，接口由示例数据驱动。"
        conversation.append({"speaker": "HomeHub", "text": reply, "time": "", "createdAt": ""})
        dashboard_state.setdefault("voiceProfile", {})["locale"] = locale
        return {
            "ok": True,
            "reply": reply,
            "detectedLocale": locale,
            "conversation": copy.deepcopy(conversation[-40:]),
            "voiceRoute": copy.deepcopy(dashboard_state.get("lastVoiceRoute", {})),
            "pendingVoiceClarification": dashboard_state.get("pendingVoiceClarification"),
            "uiAction": None,
            "lookupResult": None,
            "artifacts": [],
            "assistantMemory": copy.deepcopy(dashboard_state.get("assistantMemory", {})),
            "audio": None,
        }

    @app.post("/api/custom-agents/intake")
    async def api_custom_agents_intake():
        return {"ok": True, "item": None}

    @app.post("/api/custom-agents/generate-feature")
    async def api_custom_agents_generate_feature():
        from nethub_runtime.config.settings import ensure_generated_dirs

        generated_paths = ensure_generated_dirs()
        feature_id = "feature_auto_demo"
        feature_path = generated_paths["features"] / f"{feature_id}.py"
        if not feature_path.exists():
            feature_path.write_text(
                "from __future__ import annotations\n\n"
                "def run(payload: dict | None = None) -> dict:\n"
                "    payload = payload or {}\n"
                "    return {\"ok\": True, \"feature_id\": \"feature_auto_demo\", \"payload\": payload}\n",
                encoding="utf-8",
            )
        return {"ok": True, "featurePath": str(feature_path), "featureId": feature_id}

    @app.post("/api/custom-agents/delete")
    async def api_custom_agents_delete():
        return {"ok": True}

    @app.post("/api/custom-agents/delete-feature")
    async def api_custom_agents_delete_feature(request: Request):
        from nethub_runtime.config.settings import ensure_generated_dirs

        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        feature_id = str(body.get("featureId", "")).strip()
        if not feature_id:
            return {"ok": True, "deleted": False}

        normalized_feature_id = re.sub(r"[^a-zA-Z0-9_-]", "_", feature_id)
        feature_path = ensure_generated_dirs()["features"] / f"{normalized_feature_id}.py"
        if feature_path.exists():
            feature_path.unlink()
            return {"ok": True, "deleted": True, "featurePath": str(feature_path)}
        return {"ok": True, "deleted": False, "featurePath": str(feature_path)}

    return app


def main() -> None:
    """Run the TV Box UI using uvicorn.

    If `uvicorn` or `fastapi` are not available, print a helpful message and exit
    without throwing an unhandled exception.
    """
    try:
        app = _create_app()
    except ImportError as exc:  # pragma: no cover - improves developer experience
        print("TV Box UI dependencies not installed:", exc)
        print("To run the UI, install: pip install fastapi uvicorn[standard]")
        return

    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - environment edge-case
        print("uvicorn is required to serve the TV Box UI:", exc)
        print("To run the UI, install: pip install uvicorn[standard]")
        return

    print("📺 TV Box UI starting at http://127.0.0.1:7788")
    uvicorn.run(app, host="0.0.0.0", port=7788)


if __name__ == "__main__":
    main()
