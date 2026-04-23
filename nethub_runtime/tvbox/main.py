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
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import asyncio
from typing import Any


def _create_core_engine() -> Any:
    from nethub_runtime.core_brain.services.core_engine_provider import create_core_engine

    return create_core_engine()


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
    repo_root = Path(__file__).resolve().parents[2]
    demo_dir = repo_root / "examples" / "ui"
    generated_dir = repo_root / "generated"
    if generated_dir.exists() and generated_dir.is_dir():
        app.mount("/generated", StaticFiles(directory=str(generated_dir)), name="generated")

    # Also serve the package-internal generated dir (where document artifacts are written)
    pkg_generated_dir = Path(__file__).resolve().parents[1] / "generated"
    pkg_generated_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/pkg-generated", StaticFiles(directory=str(pkg_generated_dir)), name="pkg_generated")

    def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return copy.deepcopy(fallback)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return copy.deepcopy(fallback)

    async def _safe_request_form(request: Request) -> Any:
        try:
            return await request.form()
        except AssertionError as exc:
            if "python-multipart" in str(exc):
                raise RuntimeError("python-multipart is required for multipart/form-data uploads") from exc
            raise

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
        "languageSettings": {
            "supported": [
                {"code": "zh-CN", "label": "简体中文", "sample": "你好，HomeHub"},
                {"code": "en-US", "label": "English", "sample": "Hello, HomeHub"},
                {"code": "ja-JP", "label": "日本語", "sample": "こんにちは、HomeHub"},
            ],
            "current": "en-US",
        },
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
        "runtimeMemory": {"query": "", "namespace": "*", "promotionArtifacts": [], "vectorHits": [], "semanticMemorySummary": {}, "semanticMemoryLatestRollback": None},
        "trainingAssets": {"summary": {}, "manifest": {}, "repairPreferenceCounts": {}},
        "customAgents": [],
        "customAgentRecentActions": [],
        "studyPlanAgents": [],
        "studyPlanRecentActions": [],
        "pendingVoiceClarification": None,
    }
    cortex_fallback: dict[str, Any] = {"ok": True, "seed": {"agentId": "demo", "agentName": "Demo Brain", "stage": "shared-brain"}, "request": {}, "item": {}}

    def _startup_greeting(locale: str) -> str:
        normalized = normalize_locale(locale or "en-US", "en-US")
        if normalized == "zh-CN":
            return "你好，我是 HomeHub。已准备就绪，可以告诉我今天要处理什么。"
        if normalized == "ja-JP":
            return "こんにちは、HomeHubです。準備できています。今日の依頼をどうぞ。"
        return "Hello, this is HomeHub. I am ready. Tell me what you want to handle today."

    def _build_initial_dashboard_state() -> dict[str, Any]:
        # Default: start clean. Demo seed is opt-in via env.
        use_demo_seed = str(os.getenv("NETHUB_TVBOX_USE_DEMO_SEED", "")).strip().lower() in {"1", "true", "yes", "on"}
        state = _load_json(demo_dir / "dashboard.demo.json", dashboard_fallback) if use_demo_seed else copy.deepcopy(dashboard_fallback)
        state.setdefault("languageSettings", {})
        state["languageSettings"].setdefault("supported", copy.deepcopy(dashboard_fallback["languageSettings"]["supported"]))
        locale = normalize_locale(str(state["languageSettings"].get("current") or "en-US"), "en-US")
        state["languageSettings"]["current"] = locale
        state.setdefault("voiceProfile", {})
        state["voiceProfile"]["locale"] = locale

        # Always clear runtime-volatile data on boot to avoid stale/garbage UI state.
        state["conversation"] = []
        state["lastVoiceRoute"] = {}
        state["activeAgents"] = []
        state["timelineEvents"] = []
        state["customAgents"] = []
        state["customAgentRecentActions"] = []
        state["studyPlanAgents"] = []
        state["studyPlanRecentActions"] = []
        state["pendingVoiceClarification"] = None

        # Optional localized greeting as first message.
        state["conversation"].append(
            {"speaker": "HomeHub", "text": _startup_greeting(locale), "time": datetime.now(UTC).astimezone().strftime("%H:%M"), "createdAt": ""}
        )
        return state

    dashboard_state = _build_initial_dashboard_state()
    cortex_template = _load_json(demo_dir / "cortex_unpacked.demo.json", cortex_fallback)
    artifact_store = GeneratedArtifactStore()
    core_engine = _create_core_engine()
    bridge_api, bridge_token, bridge_poll_interval = _load_bridge_config()
    bridge_worker: dict[str, asyncio.Task[Any] | None] = {"task": None}

    @asynccontextmanager
    async def lifespan(_app: Any):
        if bridge_api and bridge_token and bridge_worker["task"] is None:
            bridge_worker["task"] = asyncio.create_task(_bridge_poll_loop())
        try:
            yield
        finally:
            task = bridge_worker.get("task")
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                bridge_worker["task"] = None

    app.router.lifespan_context = lifespan

    def _tvbox_session_id(agent_id: str | None = None) -> str:
        raw = str(agent_id or "default").strip() or "default"
        normalized = re.sub(r"[^a-zA-Z0-9:_-]", "_", raw)
        return f"tvbox:studio:{normalized}"

    def _tvbox_received_dir(session_id: str) -> Path:
        directory = repo_root / "received" / "tvbox" / session_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _derive_attachment_input_type(file_name: str, mime_type: str, kind: str) -> str:
        lowered_name = file_name.lower()
        lowered_mime = mime_type.lower()
        if kind == "image" or lowered_mime.startswith("image/"):
            return "image"
        if lowered_mime.startswith("text/"):
            return "document"
        if lowered_mime in {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/csv",
        }:
            return "document"
        if lowered_name.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".md")):
            return "document"
        return "file"

    def _persist_tvbox_attachment(raw_attachment: dict[str, Any], *, session_id: str) -> dict[str, Any]:
        file_name = str(raw_attachment.get("name") or "attachment.bin").strip() or "attachment.bin"
        mime_type = str(raw_attachment.get("mimeType") or "application/octet-stream").strip() or "application/octet-stream"
        kind = str(raw_attachment.get("kind") or "file").strip() or "file"
        payload_base64 = str(raw_attachment.get("imageBase64") or raw_attachment.get("fileBase64") or "").strip()
        if not payload_base64:
            raise ValueError("attachment payload is empty")
        content = base64.b64decode(payload_base64)

        target_dir = _tvbox_received_dir(session_id)
        timestamp_prefix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file_name)
        target_path = target_dir / f"{timestamp_prefix}_{safe_name}"
        target_path.write_bytes(content)

        input_type = _derive_attachment_input_type(file_name, mime_type, kind)
        return {
            "file_name": file_name,
            "content_type": mime_type,
            "input_type": input_type,
            "received_path": str(target_path),
            "stored_path": str(target_path),
            "source_message_type": kind,
            "size_bytes": len(content),
        }

    def _normalize_tvbox_attachments(raw_attachments: list[dict[str, Any]] | None, *, session_id: str) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in raw_attachments or []:
            if not isinstance(item, dict):
                continue
            normalized.append(_persist_tvbox_attachment(item, session_id=session_id))
        return normalized

    async def _normalize_tvbox_upload_form(form: Any, *, session_id: str) -> list[dict[str, Any]]:
        uploaded = form.get("attachment")
        if uploaded is None or not hasattr(uploaded, "read"):
            return []
        file_name = str(getattr(uploaded, "filename", "") or "attachment.bin").strip() or "attachment.bin"
        mime_type = str(getattr(uploaded, "content_type", "") or "application/octet-stream").strip() or "application/octet-stream"
        kind = str(form.get("attachment_kind") or "file").strip() or "file"
        content = await uploaded.read()

        target_dir = _tvbox_received_dir(session_id)
        timestamp_prefix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file_name)
        target_path = target_dir / f"{timestamp_prefix}_{safe_name}"
        target_path.write_bytes(content)

        return [
            {
                "file_name": file_name,
                "content_type": mime_type,
                "input_type": _derive_attachment_input_type(file_name, mime_type, kind),
                "received_path": str(target_path),
                "stored_path": str(target_path),
                "source_message_type": kind,
                "size_bytes": len(content),
            }
        ]

    def _default_attachment_message(message: str, attachments: list[dict[str, Any]]) -> str:
        if message.strip():
            return message.strip()
        if not attachments:
            return ""
        first = attachments[0]
        file_name = str(first.get("file_name") or "attachment")
        input_type = str(first.get("input_type") or "file")
        if input_type == "image":
            return f"收到图片: {file_name}"
        if input_type == "document":
            return f"收到文档: {file_name}"
        return f"处理文件: {file_name}"

    def _now_time() -> str:
        return datetime.now(UTC).astimezone().strftime("%H:%M")

    def _artifact_url(category: str, artifact_id: str, artifact_path: str | None = None) -> str:
        raw_path = str(artifact_path or "").strip()
        if raw_path:
            path_obj = Path(raw_path).resolve()
            # Try repo-root generated dir first
            try:
                relative = path_obj.relative_to(generated_dir.resolve())
                return f"/generated/{relative.as_posix()}"
            except Exception:
                pass
            # Then try package-level generated dir
            try:
                relative = path_obj.relative_to(pkg_generated_dir.resolve())
                return f"/pkg-generated/{relative.as_posix()}"
            except Exception:
                pass
        return f"/api/tvbox/generated-artifacts/open/{category}/{artifact_id}"

    def _artifact_file_path(category: str, artifact_id: str) -> Path | None:
        category_aliases = {
            "image": ("trace",),
            "audio": (),
            "video": (),
            # Document pipeline writes to the "feature" bucket; support both names
            "file": ("feature",),
        }
        candidate_categories = (category, *category_aliases.get(category, ()))

        for candidate_category in candidate_categories:
            key = GeneratedArtifactStore.CATEGORY_TO_DIR.get(candidate_category)
            if not key:
                continue
            directory = artifact_store._paths().get(key)
            if directory is None:
                continue
            candidates = sorted(directory.glob(f"{artifact_id}.*"))
            if candidates:
                return candidates[0]

        # Also search the package-level generated dir tree
        if pkg_generated_dir.exists():
            pkg_candidates = sorted(pkg_generated_dir.rglob(f"{artifact_id}.*"))
            if pkg_candidates:
                return pkg_candidates[0]

        # TV Box runtime artifacts such as generated images may be written
        # directly under the repo-local generated/ directory instead of the
        # categorized runtime store.
        generated_root = repo_root / "generated"
        if generated_root.exists():
            direct_candidates = sorted(generated_root.glob(f"{artifact_id}.*"))
            if direct_candidates:
                return direct_candidates[0]
            recursive_candidates = sorted(generated_root.rglob(f"{artifact_id}.*"))
            if recursive_candidates:
                return recursive_candidates[0]

        return None

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
                    "url": _artifact_url(artifact_type, artifact_id, str(artifact.get("path") or "")),
                    "artifactType": artifact_type,
                }
            )
        # Also surface files produced by compound pipeline steps that store their
        # artifact_path in final_output (e.g. save_document_file, file_generate).
        final_output = (result.get("execution_result") or {}).get("final_output") or {}
        for step_name in ("save_document_file", "file_generate", "generate_workflow_artifact"):
            payload = final_output.get(step_name) or {}
            ap = str(payload.get("artifact_path") or "").strip()
            if not ap:
                continue
            file_name = Path(ap).name
            if any(str(item.get("fileName") or "") == file_name for item in items):
                continue  # already listed
            items.append(
                {
                    "label": file_name,
                    "fileName": file_name,
                    "url": _artifact_url("file", Path(ap).stem, ap),
                    "artifactType": "file",
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
        # Compound pipeline: surface the final step's message + artifact path
        for compound_step in ("save_document_file", "translate_summary", "summarize_document"):
            payload = final_output.get(compound_step) or {}
            if payload.get("status") == "completed":
                ap = str(payload.get("artifact_path") or "").strip()
                msg = str(payload.get("message") or "").strip()
                if ap:
                    return f"{msg} 文件已准备好下载：{Path(ap).name}"
                if msg:
                    return msg
        for key, payload in final_output.items():
            if not isinstance(payload, dict):
                continue
            for field in ("content", "message", "answer", "summary", "translation", "itinerary", "reminder", "artifact_path"):
                value = str(payload.get(field) or "").strip()
                if value:
                    return f"Generated artifact: {value}" if field == "artifact_path" else value
        task = result.get("task") or {}
        return f"NestHub completed {task.get('intent', 'the request')}."

    _STEP_DISPLAY_LABELS: dict[str, str] = {
        "summarize_document": "📄 文档总结",
        "translate_summary":  "🌐 翻译摘要",
        "save_document_file": "💾 生成文件",
        "analyze_document":   "📄 文档处理",
    }

    def _workflow_status_from_raw(raw_status: str) -> str:
        normalized = str(raw_status or "").strip().lower()
        return {
            "completed": "packed",
            "success": "packed",
            "ok": "packed",
            "failed": "error",
            "error": "error",
            "skipped": "sleeping",
            "pending": "sleeping",
        }.get(normalized, "working")

    def _capability_label(capability: str) -> str:
        name = str(capability or "").strip()
        if not name:
            return ""
        return name.replace("_", " ").strip().title()

    def _request_plan_to_workflow_steps(request_plan: dict[str, Any] | None) -> list[dict[str, Any]]:
        plan = dict(request_plan or {})
        orchestration = dict(plan.get("capability_orchestration") or {})
        configured_workflow_plan = [
            dict(item)
            for item in list(orchestration.get("workflow_plan") or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
        if configured_workflow_plan:
            steps: list[dict[str, Any]] = [
                {"name": "intent_router", "label": "🧠 意图路由与任务拆解", "status": "working", "preview": "解析复合请求并构建执行流程"},
            ]
            for step in configured_workflow_plan:
                capability = str(step.get("name") or "").strip()
                kind = str(step.get("kind") or "").strip().lower()
                preview = str(step.get("preview") or "").strip()
                if not preview:
                    preview = "执行外部能力" if kind == "external" else "执行本地能力"
                steps.append(
                    {
                        "name": capability,
                        "label": str(step.get("label") or _capability_label(capability)),
                        "status": "sleeping",
                        "preview": preview,
                    }
                )
            steps.append({"name": "result_packaging", "label": "📦 结果组装与回复", "status": "sleeping", "preview": "汇总计划与提醒并返回"})
            return steps

        local_caps = [str(item).strip() for item in orchestration.get("local_capabilities") or [] if str(item).strip()]
        external_caps = [str(item).strip() for item in orchestration.get("external_capabilities") or [] if str(item).strip()]
        if not local_caps and not external_caps:
            return []

        steps: list[dict[str, Any]] = [
            {"name": "intent_router", "label": "🧠 意图路由与任务拆解", "status": "working", "preview": "解析复合请求并构建执行流程"},
        ]
        for capability in local_caps:
            steps.append(
                {
                    "name": capability,
                    "label": _capability_label(capability),
                    "status": "sleeping",
                    "preview": "执行本地能力",
                }
            )
        for capability in external_caps:
            steps.append(
                {
                    "name": capability,
                    "label": _capability_label(capability),
                    "status": "sleeping",
                    "preview": "执行外部能力",
                }
            )
        steps.append({"name": "result_packaging", "label": "📦 结果组装与回复", "status": "sleeping", "preview": "汇总计划与提醒并返回"})
        return steps

    def _execution_steps_to_workflow_steps(result: dict[str, Any]) -> list[dict[str, Any]]:
        steps = ((result.get("execution_result") or {}).get("steps") or [])
        out: list[dict[str, Any]] = []
        for step in steps:
            name = str(step.get("name") or "")
            if not name:
                continue
            raw_status = str(step.get("status") or "pending")
            state = _workflow_status_from_raw(raw_status)
            output = step.get("output") or {}
            preview = str(
                output.get("message") or output.get("summary") or
                output.get("translation") or output.get("itinerary") or
                output.get("reminder") or output.get("model_source") or
                output.get("artifact_path") or ""
            )[:120]
            label = step.get("metadata", {}).get("display_label") or _STEP_DISPLAY_LABELS.get(name) or name
            out.append({"name": name, "label": label, "status": state, "preview": preview})
        return out

    def _extract_workflow_steps(result: dict[str, Any]) -> list[dict[str, Any]]:
        """Build a `workflowSteps` list from the execution result for the Work-tab pipeline."""
        return _execution_steps_to_workflow_steps(result)

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

        # Persist workflow steps into lastVoiceRoute so the Work tab can render the real pipeline.
        workflow_steps = _extract_workflow_steps(result)
        existing_route = dashboard_state.get("lastVoiceRoute") or {}
        dashboard_state["lastVoiceRoute"] = {
            **existing_route,
            "requestText": message,
            "workflowSteps": workflow_steps,
        }

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
                        "session_id": "bridge:line:" + "".join(
                            char if char.isalnum() or char in {"-", "_", ":"} else "_"
                            for char in str(message.get("external_chat_id") or message.get("external_user_id") or bridge_message_id)
                        ),
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

    def _build_model_catalog() -> list[dict[str, Any]]:
        """Build a model catalog list from model_routes.json and local_model_registry.json."""
        from nethub_runtime.config.runtime_paths import (
            LOCAL_MODEL_REGISTRY_PATH,
            MODEL_ROUTES_PATH,
            ensure_runtime_config_dir,
        )

        ensure_runtime_config_dir()
        routes_path = MODEL_ROUTES_PATH
        local_reg_path = LOCAL_MODEL_REGISTRY_PATH

        routes: dict[str, Any] = _load_json(routes_path, {})
        local_reg: dict[str, Any] = _load_json(local_reg_path, {})
        local_models: list[str] = local_reg.get("models") or []

        # Collect unique model names and their task contexts from routes
        model_tasks: dict[str, list[str]] = {}
        for intent, steps in routes.items():
            if intent == "default":
                continue
            if isinstance(steps, dict):
                for step_name, step_cfg in steps.items():
                    if isinstance(step_cfg, dict):
                        model_name = str(step_cfg.get("model") or "").strip()
                        if model_name:
                            model_tasks.setdefault(model_name, []).append(intent)

        # Also include local registry models not already captured
        for m in local_models:
            model_tasks.setdefault(m, [])

        # Also capture models seen in runtime capabilities from recent traces
        for cap_model in ("qwen2.5", "deepseek-coder", "llama3", "gpt-4o", "gpt-4.1", "claude-3.5-sonnet"):
            if cap_model not in model_tasks:
                model_tasks[cap_model] = []

        catalog: list[dict[str, Any]] = []
        for model_name, tasks in model_tasks.items():
            is_local = model_name in local_models or any(
                kw in model_name for kw in ("qwen", "llama", "deepseek", "whisper", "paddle", "openvoice", "stable-diffusion", "runway", "rule-", "state-", "aggregation-", "playwright", "python-docx")
            )
            source = "local" if is_local else "cloud"
            catalog.append({
                "id": f"provider-{model_name.replace('/', '-')}",
                "label": model_name,
                "source": source,
                "deployment": "local" if is_local else "api",
                "access": "free" if is_local else "key-required",
                "status": "active" if model_name in local_models else "configured",
                "capabilities": list(dict.fromkeys(tasks))[:6],
                "models": [model_name],
                "languages": ["zh-CN", "en-US", "ja-JP"],
                "summary": f"Used for: {', '.join(tasks[:3])}" if tasks else model_name,
                "sync": {"openclaw": "manual", "workbuddy": "manual"},
                "requirements": [],
                "notes": [],
                "installCommand": "",
                "editable": False,
                "actions": [],
            })

        return sorted(catalog, key=lambda x: (x["source"] != "local", x["label"]))

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
        model_catalog = _build_model_catalog()
        snapshot["modelCatalog"] = model_catalog
        snapshot.setdefault("audioProviders", {}).setdefault("counts", {})["total"] = len(model_catalog)
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

    @app.get("/api/tvbox/execution-progress")
    def api_execution_progress(session_id: str | None = None):
        """Return live per-step execution progress for the given session.

        The frontend polls this during a request to get real-time step status.
        Returns ``{"steps": [...]}`` where each step has name/label/status/preview.
        Status values match the Work tab states: sleeping | working | packed | error.
        """
        from nethub_runtime.core_brain.services.execution_coordinator import get_session_step_progress

        sid = session_id or ""
        if not sid:
            return {"steps": []}
        return {"steps": get_session_step_progress(sid)}

    @app.post("/api/tvbox/workflow-plan")
    async def api_workflow_plan(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        message = str(body.get("message", "")).strip()
        session_id = str(body.get("sessionId") or _tvbox_session_id(body.get("agentId") or "voice-chat"))
        if not message:
            return {"ok": True, "steps": [], "requestPlan": {}}

        build_plan = getattr(core_engine, "_build_request_plan", None)
        if not callable(build_plan):
            return {"ok": True, "steps": [], "requestPlan": {}}

        try:
            request_plan = build_plan(
                message,
                {
                    "session_id": session_id,
                    "metadata": {"source": "tvbox_workflow_plan_preview"},
                },
            )
        except Exception:
            return {"ok": True, "steps": [], "requestPlan": {}}

        steps = _request_plan_to_workflow_steps(request_plan if isinstance(request_plan, dict) else {})
        return {"ok": True, "steps": steps, "requestPlan": request_plan if isinstance(request_plan, dict) else {}}

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

    @app.get("/api/runtime-memory")
    def api_runtime_memory(query: str | None = None, namespace: str | None = None, top_k: int = 5):
        payload = core_engine.inspect_runtime_memory(query=query, namespace=namespace, top_k=top_k)
        dashboard_state["runtimeMemory"] = {
            "query": payload.get("query", ""),
            "namespace": payload.get("namespace", "*"),
            "promotionArtifacts": payload.get("promotion_artifacts", []),
            "vectorHits": payload.get("vector_hits", []),
            "semanticMemorySummary": payload.get("semantic_memory_summary", {}),
            "semanticMemoryLatestRollback": payload.get("semantic_memory_latest_rollback"),
        }
        return {"ok": True, "result": payload}

    @app.get("/api/training-assets")
    def api_training_assets(profile: str = "lora_sft"):
        summary = core_engine.inspect_private_brain_summary()
        manifest = core_engine.build_training_manifest(profile=profile)
        runner = core_engine.inspect_training_runner(profile=profile, backend="mock")
        training_assets = (summary.get("layers") or {}).get("training_assets") or {}
        latest_runs = (summary.get("artifacts") or {}).get("dataset_run") or []
        dashboard_state["trainingAssets"] = {
            "summary": training_assets,
            "manifest": manifest,
            "runner": runner,
            "latestRuns": latest_runs,
            "repairPreferenceCounts": training_assets.get("repair_preference_counts") or {},
        }
        return {
            "ok": True,
            "result": {
                "summary": training_assets,
                "manifest": manifest,
                "runner": runner,
                "latest_runs": latest_runs,
                "repair_preference_counts": training_assets.get("repair_preference_counts") or {},
                "artifacts": (summary.get("artifacts") or {}),
            },
        }

    @app.post("/api/training-assets/rebuild")
    async def api_training_assets_rebuild(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        profile = str(body.get("profile", "lora_sft") or "lora_sft")
        summary = core_engine.inspect_private_brain_summary()
        manifest = core_engine.build_training_manifest(profile=profile)
        runner = core_engine.inspect_training_runner(profile=profile, backend="mock")
        training_assets = (summary.get("layers") or {}).get("training_assets") or {}
        latest_runs = (summary.get("artifacts") or {}).get("dataset_run") or []
        dashboard_state["trainingAssets"] = {
            "summary": training_assets,
            "manifest": manifest,
            "runner": runner,
            "latestRuns": latest_runs,
            "repairPreferenceCounts": training_assets.get("repair_preference_counts") or {},
        }
        return {
            "ok": True,
            "result": {
                "summary": training_assets,
                "manifest": manifest,
                "runner": runner,
                "latest_runs": latest_runs,
                "repair_preference_counts": training_assets.get("repair_preference_counts") or {},
                "artifacts": (summary.get("artifacts") or {}),
            },
        }

    @app.post("/api/training-assets/run")
    async def api_training_assets_run(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        profile = str(body.get("profile", "lora_sft") or "lora_sft")
        backend = str(body.get("backend", "mock") or "mock")
        dry_run = bool(body.get("dryRun", True))
        note = str(body.get("note", "") or "")
        run_result = core_engine.start_training_run(
            profile=profile,
            backend=backend,
            dry_run=dry_run,
            note=note,
        )
        summary = core_engine.inspect_private_brain_summary()
        manifest = core_engine.build_training_manifest(profile=profile)
        runner = core_engine.inspect_training_runner(profile=profile, backend=backend)
        training_assets = (summary.get("layers") or {}).get("training_assets") or {}
        latest_runs = (summary.get("artifacts") or {}).get("dataset_run") or []
        dashboard_state["trainingAssets"] = {
            "summary": training_assets,
            "manifest": manifest,
            "runner": runner,
            "lastRun": run_result,
            "latestRuns": latest_runs,
            "repairPreferenceCounts": training_assets.get("repair_preference_counts") or {},
        }
        return {
            "ok": True,
            "result": run_result,
            "trainingAssets": {
                "summary": training_assets,
                "manifest": manifest,
                "runner": runner,
                "latest_runs": latest_runs,
                "repair_preference_counts": training_assets.get("repair_preference_counts") or {},
                "artifacts": (summary.get("artifacts") or {}),
            },
        }

    @app.get("/api/tvbox/generated-artifacts/open/{category}/{artifact_id}")
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
            "locale": str(body.get("locale", payload.get("request", {}).get("locale", dashboard_state.get("languageSettings", {}).get("current", "en-US")))),
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
                form = await _safe_request_form(request)
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
        return {"ok": True, "transcript": "This is a demo transcription.", "detectedLocale": dashboard_state.get("languageSettings", {}).get("current", "en-US")}

    @app.post("/api/voice/chat")
    async def api_voice_chat(request: Request):
        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        message = str(body.get("message", "")).strip()
        locale = str(body.get("locale", dashboard_state.get("languageSettings", {}).get("current", "en-US")))
        raw_attachments = body.get("attachments") or []
        session_id = str(body.get("sessionId") or _tvbox_session_id(body.get("agentId") or "voice-chat"))
        try:
            attachments = _normalize_tvbox_attachments(raw_attachments if isinstance(raw_attachments, list) else [], session_id=session_id)
        except Exception as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": f"invalid attachment payload: {exc}"})
        runtime_message = _default_attachment_message(message, attachments)
        if not runtime_message:
            return JSONResponse(status_code=400, content={"ok": False, "error": "message is required"})
        try:
            result = await core_engine.handle(
                runtime_message,
                {
                    "session_id": session_id,
                    "metadata": {
                        "source": "tvbox_debug_console",
                        "locale": locale,
                        "attachments": attachments,
                        **({"input_type": attachments[0].get("input_type", "file")} if attachments else {}),
                    },
                },
                fmt="dict",
                use_langraph=True,
            )
        except Exception as exc:
            return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

        runtime_response = _record_runtime_result(runtime_message, result if isinstance(result, dict) else {})
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
            "sessionId": session_id,
            "result": result,
        }

    @app.post("/api/custom-agents/intake")
    async def api_custom_agents_intake(request: Request):
        content_type = request.headers.get("content-type", "")
        body: dict[str, Any] = {}
        form: Any | None = None
        if content_type.startswith("application/json"):
            body = await request.json()
        elif content_type.startswith("multipart/form-data"):
            try:
                form = await _safe_request_form(request)
            except RuntimeError as exc:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

        agent_id = str((body.get("id") if body else None) or (form.get("id") if form else None) or "default").strip() or "default"
        locale = normalize_locale(
            str((body.get("locale") if body else None) or (form.get("locale") if form else None) or dashboard_state.get("languageSettings", {}).get("current", "en-US")),
            "en-US",
        )
        raw_message = str((body.get("message") if body else None) or (form.get("message") if form else None) or "").strip()
        raw_attachments = body.get("attachments") or []
        session_id = _tvbox_session_id(agent_id)

        try:
            if form is not None:
                attachments = await _normalize_tvbox_upload_form(form, session_id=session_id)
            else:
                attachments = _normalize_tvbox_attachments(raw_attachments if isinstance(raw_attachments, list) else [], session_id=session_id)
        except Exception as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": f"invalid attachment payload: {exc}"})

        runtime_message = _default_attachment_message(raw_message, attachments)
        if not runtime_message:
            return JSONResponse(status_code=400, content={"ok": False, "error": "message or attachment is required"})

        try:
            result = await core_engine.handle(
                runtime_message,
                {
                    "session_id": session_id,
                    "metadata": {
                        "source": "tvbox_custom_agent_intake",
                        "locale": locale,
                        "agent_id": agent_id,
                        "attachments": attachments,
                        **({"input_type": attachments[0].get("input_type", "file")} if attachments else {}),
                    },
                },
                fmt="dict",
                use_langraph=True,
            )
        except Exception as exc:
            return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

        runtime_response = _record_runtime_result(runtime_message, result if isinstance(result, dict) else {})
        return {
            "ok": True,
            "reply": runtime_response["reply"],
            "artifacts": runtime_response["artifacts"],
            "result": result,
            "sessionId": session_id,
            "attachments": attachments,
            "item": None,
        }

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
