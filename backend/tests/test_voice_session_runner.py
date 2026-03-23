import asyncio
import json
import time

import numpy as np

from backend.api.voice_session import SpeechState, VoiceSessionRunner


class DummyWebSocket:
    def __init__(self):
        self.text_messages = []
        self.bytes_messages = []
        self.closed = False

    async def send_text(self, text: str):
        self.text_messages.append(json.loads(text))

    async def send_bytes(self, data: bytes):
        self.bytes_messages.append(data)

    async def close(self, code=None):
        self.closed = True


class DummyTts:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


class DummyStt:
    def __init__(self):
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1


def test_stop_current_tts_resets_state_and_stops_tts():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        websocket = DummyWebSocket()
        runner = VoiceSessionRunner(websocket=websocket, session_id="session-id")
        runner.loop = loop
        runner.tts = DummyTts()
        runner.barge_in.speech_state = SpeechState.SPEAKING
        runner._enqueue_audio_chunk(b"old-audio")

        runner._stop_current_tts()
        loop.run_until_complete(asyncio.sleep(0))

        assert runner.tts.stop_calls == 1
        assert runner.barge_in.speech_state == SpeechState.IDLE
        assert runner.out_audio_q.empty()
        assert websocket.text_messages[-1]["event"] == "tts_reset"
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_barge_in_false_alarm_resumes_speaking_state():
    websocket = DummyWebSocket()
    runner = VoiceSessionRunner(websocket=websocket, session_id="session-id")
    runner.barge_in.speech_state = SpeechState.SPEAKING
    runner.send_enabled = True

    runner._interrupt_now()
    assert runner.barge_in.speech_state == SpeechState.INTERRUPT_PENDING
    assert runner.send_enabled is False

    runner._resume_play()
    assert runner.barge_in.speech_state == SpeechState.SPEAKING
    assert runner.send_enabled is True


def test_confirm_interrupt_marks_interrupted_and_stops_tts():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        websocket = DummyWebSocket()
        runner = VoiceSessionRunner(websocket=websocket, session_id="session-id")
        runner.loop = loop
        runner.tts = DummyTts()
        runner.barge_in.speech_state = SpeechState.INTERRUPT_PENDING

        runner._confirm_interrupt()
        loop.run_until_complete(asyncio.sleep(0))

        assert runner.barge_in.speech_state == SpeechState.INTERRUPTED
        assert runner.tts.stop_calls == 1
        assert websocket.text_messages[-1]["event"] == "tts_interrupted"
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_handle_text_command_stop_resets_stt_and_tts():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        websocket = DummyWebSocket()
        runner = VoiceSessionRunner(websocket=websocket, session_id="session-id")
        runner.loop = loop
        runner.tts = DummyTts()
        runner.stt = DummyStt()
        runner.barge_in.speech_state = SpeechState.SPEAKING

        loop.run_until_complete(runner._handle_text_command('{"cmd":"stop"}'))
        loop.run_until_complete(asyncio.sleep(0))

        assert runner.stt.reset_calls == 1
        assert runner.tts.stop_calls == 1
        assert runner.barge_in.speech_state == SpeechState.IDLE
        assert websocket.text_messages[-1]["event"] == "tts_reset"
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_handle_text_command_interrupt_status_reports_explicit_state():
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        websocket = DummyWebSocket()
        runner = VoiceSessionRunner(websocket=websocket, session_id="session-id")
        runner.loop = loop
        runner.barge_in.speech_state = SpeechState.INTERRUPT_PENDING

        loop.run_until_complete(runner._handle_text_command('{"cmd":"interrupt_status"}'))

        status = websocket.text_messages[-1]
        assert status["event"] == "interrupt_status"
        assert status["speech_state"] == SpeechState.INTERRUPT_PENDING.value
        assert status["pausepending"] is True
        assert status["confirmed"] is False
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def test_barge_in_score_is_lower_when_echo_risk_is_high():
    websocket = DummyWebSocket()
    runner = VoiceSessionRunner(websocket=websocket, session_id="session-id")

    low_echo = runner._barge_in_score(
        is_speech=True,
        energy=2800.0,
        speech_ratio=0.8,
        echo_risk=0.0,
    )
    high_echo = runner._barge_in_score(
        is_speech=True,
        energy=2800.0,
        speech_ratio=0.8,
        echo_risk=1.0,
    )

    assert low_echo > high_echo


def test_handle_barge_in_enters_pending_with_high_adaptive_score():
    websocket = DummyWebSocket()
    runner = VoiceSessionRunner(websocket=websocket, session_id="session-id")
    runner.use_native_vad = False
    runner.barge_in.speech_state = SpeechState.SPEAKING
    runner.barge_in.start_frames = 1
    runner.barge_in.min_speech_ms = runner.barge_in.frame_ms
    runner.barge_in.pending_score = 0.5
    runner.barge_in.confirm_score = 10.0
    runner.barge_in.noise_floor = 100.0
    runner.last_tts_end_time = time.time() - 2
    runner.last_tts_chunk_time = time.time() - 2

    frame = (np.ones(runner.frame_bytes // 2, dtype=np.int16) * 3000).tobytes()
    runner._handle_barge_in(frame)

    assert runner.barge_in.speech_state == SpeechState.INTERRUPT_PENDING
    assert runner.send_enabled is False
    assert runner.barge_in.last_score >= runner.barge_in.pending_score


def test_handle_barge_in_confirms_interrupt_with_strong_signal():
    websocket = DummyWebSocket()
    runner = VoiceSessionRunner(websocket=websocket, session_id="session-id")
    runner.use_native_vad = False
    runner.tts = DummyTts()
    runner.barge_in.speech_state = SpeechState.INTERRUPT_PENDING
    runner.barge_in.min_speech_ms = runner.barge_in.frame_ms
    runner.barge_in.confirm_score = 0.5
    runner.barge_in.noise_floor = 100.0
    runner.last_tts_end_time = time.time() - 2
    runner.last_tts_chunk_time = time.time() - 2

    frame = (np.ones(runner.frame_bytes // 2, dtype=np.int16) * 3000).tobytes()
    runner._handle_barge_in(frame)

    assert runner.barge_in.speech_state == SpeechState.INTERRUPTED
    assert runner.tts.stop_calls == 1
