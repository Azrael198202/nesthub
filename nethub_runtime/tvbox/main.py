"""Lightweight TV Box UI entrypoint.

This module avoids importing optional runtime-only dependencies at import time.
If `fastapi` or `uvicorn` are missing, `main()` will print a friendly message and exit
instead of raising an import error during module import.
"""

from __future__ import annotations

import copy
import json
import re
import base64
from datetime import UTC, datetime
import asyncio
from typing import Any


def _create_core_engine() -> Any:
    from nethub_runtime.core.services.core_engine import AICore

    return AICore()


def _load_bridge_config() -> tuple[str, str, int]:
    from pathlib import Path

    import yaml

    config_path = Path(__file__).resolve().parents[1] / "config" / "bridge_external.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    bridge_api = str(config.get("bridge_api") or "").strip()
    bridge_token = str(config.get("bridge_token") or "").strip()
    if not bridge_token:
        token_env = str(config.get("bridge_token_env") or "").strip()
        if token_env:
            import os

            bridge_token = os.getenv(token_env, "").strip()
    poll_interval = int(config.get("poll_interval_seconds") or 5)
    return bridge_api, bridge_token, poll_interval


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
    from nethub_runtime.generated.store import GeneratedArtifactStore

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
    artifact_store = GeneratedArtifactStore()
    core_engine = _create_core_engine()
    bridge_api, bridge_token, bridge_poll_interval = _load_bridge_config()
    bridge_worker: dict[str, asyncio.Task[Any] | None] = {"task": None}

    def _now_time() -> str:
        return datetime.now(UTC).astimezone().strftime("%H:%M")

    def _artifact_url(category: str, artifact_id: str) -> str:
        return f"/api/generated-artifacts/open/{category}/{artifact_id}"

    def _artifact_file_path(category: str, artifact_id: str) -> Path | None:
        key = GeneratedArtifactStore.CATEGORY_TO_DIR.get(category)
        if not key:
            return None
        directory = artifact_store.paths.get(key)
        if directory is None:
            return None
        candidates = sorted(directory.glob(f"{artifact_id}.*"))
        return candidates[0] if candidates else None

    def _artifact_items_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for artifact in result.get("artifacts", []) or []:
            artifact_type = str(artifact.get("artifact_type") or "file")
            artifact_id = str(artifact.get("artifact_id") or "")
            if not artifact_id:
                continue
            items.append(
                {
                    "label": str(artifact.get("name") or artifact_id),
                    "fileName": str(artifact.get("name") or artifact_id),
                    "url": _artifact_url(artifact_type, artifact_id),
                    "artifactType": artifact_type,
                }
            )
        return items

    def _extract_reply_text(result: dict[str, Any]) -> str:
        execution_result = result.get("execution_result") or {}
        if execution_result.get("execution_type") == "agent":
            agent_result = execution_result.get("agent_result") or {}
            final_answer = str(agent_result.get("final_answer") or "").strip()
            if final_answer:
                return final_answer
        final_output = execution_result.get("final_output") or {}
        for key in ("manage_information_agent", "query_information_knowledge", "file_read", "file_generate", "generate_workflow_artifact", "single_step"):
            payload = final_output.get(key) or {}
            for field in ("content", "message", "answer", "summary", "artifact_path"):
                value = str(payload.get(field) or "").strip()
                if value:
                    return f"Generated artifact: {value}" if field == "artifact_path" else value
        task = result.get("task") or {}
        return f"NestHub completed {task.get('intent', 'the request')}."

    def _to_runtime_agent_card(result: dict[str, Any]) -> dict[str, Any] | None:
        agent = result.get("agent")
        if not isinstance(agent, dict):
            return None
        return {
            "id": str(agent.get("agent_id") or agent.get("name") or "runtime-agent"),
            "name": str(agent.get("name") or "Runtime Agent"),
            "role": str(agent.get("role") or "Runtime Agent"),
            "status": "active",
            "progress": 100,
            "lastUpdate": _now_time(),
        }

    def _to_runtime_blueprint_cards(result: dict[str, Any]) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for blueprint in result.get("blueprints") or []:
            metadata = blueprint.get("metadata") or {}
            synthesis = metadata.get("synthesis") or {}
            cards.append(
                {
                    "id": str(blueprint.get("blueprint_id") or blueprint.get("name") or "runtime-blueprint"),
                    "name": str(blueprint.get("name") or "Runtime Blueprint"),
                    "summary": str(synthesis.get("purpose_summary") or blueprint.get("intent") or "Runtime generated blueprint"),
                    "status": "complete",
                    "createdAt": _now_time(),
                    "latestRecord": str(synthesis.get("reasoning") or ""),
                    "generatedFeaturePath": str(metadata.get("generated_artifact_path") or ""),
                    "generatedFeatureId": str(blueprint.get("blueprint_id") or ""),
                }
            )
        return cards

    def _to_model_provider_cards(result: dict[str, Any]) -> list[dict[str, Any]]:
        plan = (result.get("execution_result") or {}).get("execution_plan") or []
        providers: dict[str, dict[str, Any]] = {}
        for step in plan:
            model_choice = ((step.get("capability") or {}).get("model_choice") or {})
            provider = str(model_choice.get("provider") or "runtime")
            model = str(model_choice.get("model") or "unknown")
            key = f"{provider}:{model}"
            entry = providers.setdefault(key, {"name": key, "capabilities": []})
            step_name = str(step.get("name") or "")
            if step_name and step_name not in entry["capabilities"]:
                entry["capabilities"].append(step_name)
        return list(providers.values())

    def _record_runtime_result(message: str, result: dict[str, Any]) -> dict[str, Any]:
        reply = _extract_reply_text(result)
        artifacts = _artifact_items_from_result(result)
        dashboard_state.setdefault("conversation", [])
        dashboard_state["conversation"].append({"speaker": "You", "text": message, "time": _now_time(), "createdAt": ""})
        dashboard_state["conversation"].append({"speaker": "HomeHub", "text": reply, "time": _now_time(), "createdAt": "", "artifacts": artifacts})
        dashboard_state["conversation"] = dashboard_state["conversation"][-40:]

        runtime_agent = _to_runtime_agent_card(result)
        if runtime_agent:
            agents = [item for item in dashboard_state.get("activeAgents", []) if item.get("id") != runtime_agent["id"]]
            agents.append(runtime_agent)
            dashboard_state["activeAgents"] = agents[-8:]

        runtime_blueprints = _to_runtime_blueprint_cards(result)
        if runtime_blueprints:
            existing = {str(item.get("id") or ""): item for item in dashboard_state.get("customAgents", [])}
            for item in runtime_blueprints:
                existing[item["id"]] = item
            dashboard_state["customAgents"] = list(existing.values())[-12:]

        runtime_models = _to_model_provider_cards(result)
        if runtime_models:
            dashboard_state["modelProviders"] = runtime_models

        dashboard_state.setdefault("timelineEvents", []).append(
            {"time": _now_time(), "title": "NestHub Runtime", "detail": reply[:120]}
        )
        dashboard_state["timelineEvents"] = dashboard_state["timelineEvents"][-30:]
        return {"reply": reply, "artifacts": artifacts}

    async def _process_bridge_message(message: dict[str, Any]) -> None:
        if not isinstance(message, dict):
            return
        bridge_message_id = str(message.get("bridge_message_id") or "").strip()
        text = str(message.get("text") or "").strip()
        if not bridge_message_id or not text:
            return

        import httpx

        headers = {"Authorization": f"Bearer {bridge_token}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            claim_resp = await client.post(
                f"{bridge_api}/hub/claim",
                json={"bridge_message_id": bridge_message_id},
                headers=headers,
            )
            if claim_resp.status_code >= 400:
                return

            try:
                result = await core_engine.handle(
                    text,
                    {
                        "metadata": {
                            "source": "line_bridge",
                            "bridge_message_id": bridge_message_id,
                            "external_user_id": message.get("external_user_id"),
                            "external_chat_id": message.get("external_chat_id"),
                            "external_message_id": message.get("external_message_id"),
                            "attachments": message.get("attachments") or [],
                        }
                    },
                    fmt="dict",
                    use_langraph=True,
                )
            except Exception as engine_exc:
                import logging as _logging
                _logging.getLogger("nethub_runtime.tvbox").error(
                    "core_engine.handle failed bridge_message_id=%s: %s", bridge_message_id, engine_exc
                )
                await client.post(
                    f"{bridge_api}/hub/result",
                    json={"bridge_message_id": bridge_message_id, "result": {
                        "reply": f"处理请求时发生错误，请稍后重试。（{type(engine_exc).__name__}）",
                        "artifacts": [], "downloads": [],
                    }},
                    headers=headers,
                )
                return
            runtime_response = _record_runtime_result(text, result if isinstance(result, dict) else {})
            raw_artifacts = list((result or {}).get("artifacts") or []) if isinstance(result, dict) else []

            # Also include the image_generate step output as an artifact
            _img_payload = (((result or {}).get("execution_result") or {}).get("final_output") or {}).get("image_generate") or {}
            _img_path_str = str(_img_payload.get("artifact_path") or "").strip()
            if _img_path_str and _img_path_str not in {str(a.get("path") or "") for a in raw_artifacts}:
                raw_artifacts = list(raw_artifacts) + [{
                    "path": _img_path_str,
                    "name": _img_payload.get("file_name") or Path(_img_path_str).name,
                    "artifact_type": "image",
                    "artifact_id": Path(_img_path_str).stem,
                    "source": "image_generate",
                }]

            downloads: list[dict[str, Any]] = []
            for artifact in raw_artifacts:
                path_value = str(artifact.get("path") or "").strip()
                if not path_value:
                    continue
                from pathlib import Path

                artifact_path = Path(path_value)
                if not artifact_path.exists() or not artifact_path.is_file():
                    continue
                upload_resp = await client.post(
                    f"{bridge_api}/hub/artifact",
                    json={
                        "bridge_message_id": bridge_message_id,
                        "file_name": str(artifact.get("name") or artifact_path.name),
                        "artifact_type": str(artifact.get("artifact_type") or "file"),
                        "artifact_id": str(artifact.get("artifact_id") or artifact_path.stem),
                        "source": str(artifact.get("source") or "runtime"),
                        "content_base64": base64.b64encode(artifact_path.read_bytes()).decode("utf-8"),
                    },
                    headers=headers,
                )
                if upload_resp.status_code < 400:
                    payload = upload_resp.json()
                    download = payload.get("download") if isinstance(payload, dict) else None
                    if isinstance(download, dict):
                        downloads.append(download)
            await client.post(
                f"{bridge_api}/hub/result",
                json={"bridge_message_id": bridge_message_id, "result": {"reply": runtime_response["reply"], "artifacts": raw_artifacts, "downloads": downloads}},
                headers=headers,
            )

    async def _bridge_poll_loop() -> None:
        if not bridge_api or not bridge_token:
            return
        import httpx
        from nethub_runtime.integrations.external_log_monitor import fetch_and_save

        headers = {"Authorization": f"Bearer {bridge_token}"}
        while True:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(f"{bridge_api}/hub/pending", headers=headers)
                    response.raise_for_status()
                    pending = response.json()
                processed_any = False
                for item in pending:
                    try:
                        await _process_bridge_message(item)
                        processed_any = True
                    except Exception:
                        continue
                # Fetch external log snapshot after each poll round that had messages
                if processed_any:
                    await fetch_and_save(label=f"bridge_poll_{len(pending)}_items")
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(bridge_poll_interval)

    @app.on_event("startup")
    async def startup_bridge_worker() -> None:
        if bridge_api and bridge_token and bridge_worker["task"] is None:
            bridge_worker["task"] = asyncio.create_task(_bridge_poll_loop())

    @app.on_event("shutdown")
    async def shutdown_bridge_worker() -> None:
        task = bridge_worker.get("task")
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            bridge_worker["task"] = None

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
        snapshot["generatedArtifacts"] = artifact_store.list_artifacts()
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

    @app.get("/api/generated-artifacts")
    def api_generated_artifacts():
        return {"ok": True, "items": artifact_store.list_artifacts()}

    @app.get("/api/generated-artifacts/open/{category}/{artifact_id}")
    def api_generated_artifact_open(category: str, artifact_id: str):
        path = _artifact_file_path(category, artifact_id)
        if path is None or not path.exists():
            return JSONResponse(status_code=404, content={"ok": False, "error": "artifact not found"})
        return FileResponse(path)

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
        if not message:
            return JSONResponse(status_code=400, content={"ok": False, "error": "message is required"})
        try:
            result = await core_engine.handle(
                message,
                {"metadata": {"source": "tvbox_debug_console", "locale": locale}},
                fmt="dict",
                use_langraph=True,
            )
        except Exception as exc:
            return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

        runtime_response = _record_runtime_result(message, result if isinstance(result, dict) else {})
        conversation = copy.deepcopy(dashboard_state.get("conversation", []))
        dashboard_state.setdefault("voiceProfile", {})["locale"] = locale
        return {
            "ok": True,
            "reply": runtime_response["reply"],
            "detectedLocale": locale,
            "conversation": conversation,
            "voiceRoute": copy.deepcopy(dashboard_state.get("lastVoiceRoute", {})),
            "pendingVoiceClarification": dashboard_state.get("pendingVoiceClarification"),
            "uiAction": None,
            "lookupResult": None,
            "artifacts": runtime_response["artifacts"],
            "assistantMemory": copy.deepcopy(dashboard_state.get("assistantMemory", {})),
            "audio": None,
            "result": result,
        }

    @app.post("/api/custom-agents/intake")
    async def api_custom_agents_intake():
        return {"ok": True, "item": None}

    @app.post("/api/custom-agents/generate-feature")
    async def api_custom_agents_generate_feature():
        feature_id = "feature_auto_demo"
        feature_path = artifact_store.persist(
            "feature",
            feature_id,
            "from __future__ import annotations\n\n"
            "def run(payload: dict | None = None) -> dict:\n"
            "    payload = payload or {}\n"
            "    return {\"ok\": True, \"feature_id\": \"feature_auto_demo\", \"payload\": payload}\n",
            extension=".py",
        )
        return {"ok": True, "featurePath": str(feature_path), "featureId": feature_id}

    @app.post("/api/custom-agents/delete")
    async def api_custom_agents_delete():
        return {"ok": True}

    @app.post("/api/custom-agents/delete-feature")
    async def api_custom_agents_delete_feature(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        feature_id = str(body.get("featureId", "")).strip()
        if not feature_id:
            return {"ok": True, "deleted": False}

        normalized_feature_id = re.sub(r"[^a-zA-Z0-9_-]", "_", feature_id)
        deleted = artifact_store.delete("feature", normalized_feature_id)
        return {"ok": True, "deleted": deleted["deleted"], "featurePath": deleted["path"]}

    @app.post("/api/generated-artifacts/delete")
    async def api_generated_artifacts_delete(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        category = str(body.get("category", "")).strip()
        artifact_id = str(body.get("artifactId", "")).strip()
        if category not in GeneratedArtifactStore.CATEGORY_TO_DIR or not artifact_id:
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid category or artifactId"})
        return artifact_store.delete(category, artifact_id)

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
