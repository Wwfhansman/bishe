import os

import pytest

from backend.voice import create_tts_service, load_voice_registry


def test_tts_smoke():
    r = load_voice_registry()
    spec = r.get_tts("local_piper_onnx")
    model_path = spec.config.get("model_path")
    if not isinstance(model_path, str) or not os.path.exists(model_path):
        pytest.skip("missing piper model")
    tts = create_tts_service(r)
    tts.initialize()
    chunks = list(tts.synthesize_stream("你好"))
    assert len(chunks) > 0
    assert hasattr(tts, "sample_rate")
    tts.close()

