import os
import time

import pytest

from backend.voice import AudioChunk, create_stt_service, load_voice_registry


def test_stt_smoke():
    r = load_voice_registry()
    spec = r.get_stt("local_sherpa_streaming")
    model_dir = spec.config.get("model_dir")
    if not isinstance(model_dir, str) or not os.path.isdir(model_dir):
        pytest.skip("missing sherpa model")
    stt = create_stt_service(r)
    stt.initialize()
    silence = b"\x00\x00" * (16000 // 5)
    stt.accept_audio(AudioChunk(pcm16_bytes=silence))
    time.sleep(0.2)
    stt.poll_result()
    stt.close()

