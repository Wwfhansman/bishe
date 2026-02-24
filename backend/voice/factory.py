from __future__ import annotations

from typing import Optional

from .errors import VoiceServiceConfigError
from .protocols import SpeechToTextService, TextToSpeechService
from .registry import VoiceProviderSpec, VoiceRegistry, load_voice_registry, resolve_provider_ids


def _create_stt(spec: VoiceProviderSpec) -> SpeechToTextService:
    if spec.provider_type == "sherpa_onnx":
        from .providers.sherpa_onnx_stt import SherpaOnnxSttService

        return SherpaOnnxSttService(**spec.config)
    raise VoiceServiceConfigError(f"Unsupported STT provider type: {spec.provider_type}")


def _create_tts(spec: VoiceProviderSpec) -> TextToSpeechService:
    if spec.provider_type == "piper_onnx":
        from .providers.piper_onnx_tts import PiperOnnxTtsService

        return PiperOnnxTtsService(**spec.config)
    raise VoiceServiceConfigError(f"Unsupported TTS provider type: {spec.provider_type}")


def create_stt_service(registry: Optional[VoiceRegistry] = None) -> SpeechToTextService:
    r = registry or load_voice_registry()
    stt_provider_id, _ = resolve_provider_ids()
    return _create_stt(r.get_stt(stt_provider_id))


def create_tts_service(registry: Optional[VoiceRegistry] = None) -> TextToSpeechService:
    r = registry or load_voice_registry()
    _, tts_provider_id = resolve_provider_ids()
    return _create_tts(r.get_tts(tts_provider_id))

