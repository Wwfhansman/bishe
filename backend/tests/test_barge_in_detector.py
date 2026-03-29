import time

import numpy as np

from backend.voice.barge_in_detector import AdaptiveBargeInDetector, BargeInEventKind, SpeechState


def test_detector_score_drops_when_echo_risk_rises():
    detector = AdaptiveBargeInDetector()
    detector.state.noise_floor = 100.0

    low_echo = detector.score(
        is_speech=True,
        energy=2800.0,
        speech_ratio=0.8,
        echo_risk=0.0,
    )
    high_echo = detector.score(
        is_speech=True,
        energy=2800.0,
        speech_ratio=0.8,
        echo_risk=1.0,
    )

    assert low_echo > high_echo


def test_detector_process_audio_emits_pending_and_confirmed_events():
    detector = AdaptiveBargeInDetector()
    detector.state.speech_state = SpeechState.SPEAKING
    detector.state.start_frames = 1
    detector.state.min_speech_ms = detector.state.frame_ms
    detector.state.pending_score = 0.5
    detector.state.confirm_score = 0.5
    detector.state.noise_floor = 100.0

    frame = (np.ones(detector.frame_bytes // 2, dtype=np.int16) * 3000).tobytes()
    events = detector.process_audio(
        audio_bytes=frame,
        detect_speech=lambda _: True,
        last_tts_chunk_time=time.time() - 2.0,
        last_tts_end_time=time.time() - 2.0,
    )

    event_kinds = [event.kind for event in events]
    assert BargeInEventKind.PENDING in event_kinds
    assert BargeInEventKind.CONFIRMED in event_kinds
    assert detector.state.speech_state == SpeechState.INTERRUPTED


def test_detector_resumes_after_pending_false_alarm():
    detector = AdaptiveBargeInDetector()
    detector.state.speech_state = SpeechState.INTERRUPT_PENDING
    detector.state.silence_end_frames = 1
    detector.state.noise_floor = 100.0

    frame = np.zeros(detector.frame_bytes // 2, dtype=np.int16).tobytes()
    events = detector.process_audio(
        audio_bytes=frame,
        detect_speech=lambda _: False,
        last_tts_chunk_time=time.time() - 2.0,
        last_tts_end_time=time.time() - 2.0,
    )

    assert events[-1].kind == BargeInEventKind.RESUMED
    assert detector.state.speech_state == SpeechState.SPEAKING
