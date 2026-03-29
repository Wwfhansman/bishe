import numpy as np

from backend.voice.noise_suppressor import NoiseSuppressorState, StreamingNoiseSuppressor


def test_noise_suppressor_preserves_frame_length():
    suppressor = StreamingNoiseSuppressor(
        state=NoiseSuppressorState(enabled=True, frame_ms=20),
        sample_rate=16000,
    )
    frame = (np.ones(suppressor.frame_bytes // 2, dtype=np.int16) * 500).tobytes()

    out = suppressor.process(frame)

    assert len(out) == len(frame)


def test_noise_suppressor_reduces_low_energy_stationary_noise():
    suppressor = StreamingNoiseSuppressor(
        state=NoiseSuppressorState(
            enabled=True,
            frame_ms=20,
            noise_floor=800.0,
            speech_margin=2.5,
            spectral_alpha=0.5,
            noise_alpha=0.2,
            min_gain=0.2,
            over_subtraction=1.2,
        ),
        sample_rate=16000,
    )
    noise = (np.ones(suppressor.frame_bytes // 2, dtype=np.int16) * 300).tobytes()

    suppressor.process(noise)
    out = suppressor.process(noise)

    in_energy = suppressor.frame_energy(noise)
    out_energy = suppressor.frame_energy(out)
    assert out_energy <= in_energy


def test_noise_suppressor_can_be_disabled():
    suppressor = StreamingNoiseSuppressor(
        state=NoiseSuppressorState(enabled=False, frame_ms=20),
        sample_rate=16000,
    )
    frame = (np.arange((suppressor.frame_bytes // 2) - 7, dtype=np.int16) - 100).tobytes()

    out = suppressor.process(frame)

    assert out == frame


def test_noise_suppressor_update_config_applies_valid_values():
    suppressor = StreamingNoiseSuppressor(
        state=NoiseSuppressorState(enabled=False, frame_ms=20),
        sample_rate=16000,
    )

    changed = suppressor.update_config(
        enabled=True,
        noise_floor=900.0,
        noise_alpha=0.15,
        spectral_alpha=0.2,
        min_gain=0.4,
        over_subtraction=1.3,
        speech_margin=2.2,
    )

    metrics = suppressor.collect_metrics()
    assert changed is True
    assert metrics["enabled"] is True
    assert metrics["noise_floor"] == 900.0
    assert metrics["noise_alpha"] == 0.15
    assert metrics["spectral_alpha"] == 0.2
    assert metrics["min_gain"] == 0.4
    assert metrics["over_subtraction"] == 1.3
    assert metrics["speech_margin"] == 2.2
