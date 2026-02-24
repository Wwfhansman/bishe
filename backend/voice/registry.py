from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from backend.config import env

from .errors import VoiceServiceConfigError


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def resolve_registry_path(path: Optional[str] = None) -> str:
    p = path or env("VOICE_REGISTRY_PATH", None)
    if not p:
        return os.path.join(_repo_root(), "backend", "voice", "registry.json")
    if os.path.isabs(p):
        return p
    return os.path.abspath(os.path.join(_repo_root(), p))


def _resolve_path(base_dir: str, p: str) -> str:
    if os.path.isabs(p):
        return p
    return os.path.abspath(os.path.join(base_dir, p))


@dataclass(frozen=True)
class VoiceProviderSpec:
    provider_id: str
    provider_type: str
    config: dict[str, Any]


@dataclass(frozen=True)
class VoiceRegistry:
    path: str
    base_dir: str
    stt: dict[str, VoiceProviderSpec]
    tts: dict[str, VoiceProviderSpec]

    def get_stt(self, provider_id: str) -> VoiceProviderSpec:
        try:
            return self.stt[provider_id]
        except KeyError as e:
            raise VoiceServiceConfigError(f"Unknown STT provider_id: {provider_id}") from e

    def get_tts(self, provider_id: str) -> VoiceProviderSpec:
        try:
            return self.tts[provider_id]
        except KeyError as e:
            raise VoiceServiceConfigError(f"Unknown TTS provider_id: {provider_id}") from e


def load_voice_registry(path: Optional[str] = None) -> VoiceRegistry:
    registry_path = resolve_registry_path(path)
    if not os.path.exists(registry_path):
        raise VoiceServiceConfigError(f"VOICE_REGISTRY_PATH not found: {registry_path}")
    # Use repo root as base for resolving relative paths in registry
    base_dir = _repo_root()
    with open(registry_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise VoiceServiceConfigError("registry.json must be an object")
    stt_raw = raw.get("stt")
    tts_raw = raw.get("tts")
    if not isinstance(stt_raw, dict) or not isinstance(tts_raw, dict):
        raise VoiceServiceConfigError("registry.json must contain object fields: stt, tts")

    stt: dict[str, VoiceProviderSpec] = {}
    for pid, cfg in stt_raw.items():
        if not isinstance(cfg, dict) or "type" not in cfg:
            raise VoiceServiceConfigError(f"Invalid STT provider spec: {pid}")
        ptype = cfg["type"]
        if not isinstance(ptype, str) or not ptype:
            raise VoiceServiceConfigError(f"Invalid STT provider type: {pid}")
        normalized = dict(cfg)
        normalized.pop("type", None)
        for k in ("model_dir", "model_path", "config_path", "tokens_path", "data_dir"):
            v = normalized.get(k)
            if isinstance(v, str) and v:
                normalized[k] = _resolve_path(base_dir, v)
        stt[pid] = VoiceProviderSpec(provider_id=pid, provider_type=ptype, config=normalized)

    tts: dict[str, VoiceProviderSpec] = {}
    for pid, cfg in tts_raw.items():
        if not isinstance(cfg, dict) or "type" not in cfg:
            raise VoiceServiceConfigError(f"Invalid TTS provider spec: {pid}")
        ptype = cfg["type"]
        if not isinstance(ptype, str) or not ptype:
            raise VoiceServiceConfigError(f"Invalid TTS provider type: {pid}")
        normalized = dict(cfg)
        normalized.pop("type", None)
        for k in ("model_dir", "model_path", "config_path", "tokens_path", "data_dir"):
            v = normalized.get(k)
            if isinstance(v, str) and v:
                normalized[k] = _resolve_path(base_dir, v)
        tts[pid] = VoiceProviderSpec(provider_id=pid, provider_type=ptype, config=normalized)

    return VoiceRegistry(path=registry_path, base_dir=base_dir, stt=stt, tts=tts)


def resolve_provider_ids() -> tuple[str, str]:
    stt_provider = env("STT_PROVIDER", "local_sherpa_streaming")
    tts_provider = env("TTS_PROVIDER", "local_piper_onnx")
    return stt_provider, tts_provider

