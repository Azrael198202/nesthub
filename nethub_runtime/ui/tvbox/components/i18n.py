"""Component helpers for TV Box i18n payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _locales_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "i18n" / "locales"


def _load_locale_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    root = _locales_dir()
    if not root.exists() or not root.is_dir():
        return catalog

    for file in sorted(root.glob("*.json")):
        try:
            payload = json.loads(file.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        locale = str(payload.get("locale", file.stem)).strip()
        strings = payload.get("strings", {})
        ui_text = payload.get("uiText", {})
        if not locale or not isinstance(strings, dict):
            continue
        if not isinstance(ui_text, dict):
            ui_text = {}
        catalog[locale] = {
            "label": str(payload.get("label", locale)).strip() or locale,
            "sample": str(payload.get("sample", "")).strip(),
            "strings": strings,
            "uiText": ui_text,
        }
    return catalog


def get_supported_languages() -> list[dict[str, str]]:
    catalog = _load_locale_catalog()
    if not catalog:
        return [{"code": "en-US", "label": "English", "sample": "Hello"}]
    return [
        {"code": locale, "label": data["label"], "sample": data["sample"]}
        for locale, data in sorted(catalog.items(), key=lambda item: item[0])
    ]


def normalize_locale(locale: str | None, fallback: str = "en-US") -> str:
    catalog = _load_locale_catalog()
    supported = set(catalog.keys())
    candidate = str(locale or "").strip()
    if candidate in supported:
        return candidate
    if fallback in supported:
        return fallback
    if "en-US" in supported:
        return "en-US"
    if supported:
        return sorted(supported)[0]
    return "en-US"


def build_settings_i18n(locale: str | None) -> dict[str, Any]:
    catalog = _load_locale_catalog()
    resolved = normalize_locale(locale, "en-US")
    fallback_locale = "en-US" if "en-US" in catalog else resolved
    strings = catalog.get(resolved, {}).get("strings") or catalog.get(fallback_locale, {}).get("strings") or {}
    ui_text = catalog.get(resolved, {}).get("uiText") or catalog.get(fallback_locale, {}).get("uiText") or {}
    fallback_ui_text = catalog.get(fallback_locale, {}).get("uiText") or {}
    return {
        "locale": resolved,
        "strings": strings,
        "uiText": ui_text,
        "fallbackUiText": fallback_ui_text,
        "supported": [item["code"] for item in get_supported_languages()],
        "supportedLanguages": get_supported_languages(),
    }
