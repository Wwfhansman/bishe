from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AudioChunk:
    pcm16_bytes: bytes
    sample_rate: int = 16000
    channels: int = 1
    is_final: bool = False
    timestamp_ms: Optional[int] = None


@dataclass(frozen=True)
class SttResult:
    text: str
    is_final: bool
    confidence: Optional[float] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    raw: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class TtsChunk:
    pcm16_bytes: bytes
    sample_rate: int
    is_final: bool = False

