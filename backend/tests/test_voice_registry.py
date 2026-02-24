import os

from backend.voice.registry import load_voice_registry, resolve_registry_path


def test_load_voice_registry_default():
    p = resolve_registry_path()
    assert os.path.exists(p)
    r = load_voice_registry(p)
    assert "local_sherpa_streaming" in r.stt
    assert "local_piper_onnx" in r.tts

