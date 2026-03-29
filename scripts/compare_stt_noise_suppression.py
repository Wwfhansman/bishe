import argparse
import json
import time
import wave
from pathlib import Path

import psutil

from backend.voice import (
    AudioChunk,
    NoiseSuppressorState,
    StreamingNoiseSuppressor,
    create_stt_service,
    load_voice_registry,
)


def read_wav_int16_mono(path: str):
    with wave.open(path, "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        sw = wf.getsampwidth()
        if ch != 1 or sw != 2:
            raise RuntimeError("wav must be mono int16")
        return wf.readframes(wf.getnframes()), sr


def write_wav_int16_mono(path: str, pcm: bytes, sample_rate: int):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


def run_stt_once(pcm: bytes, sr: int, chunk_ms: int, tail_silence_ms: int):
    registry = load_voice_registry()
    stt = create_stt_service(registry)
    stt.initialize()
    bytes_per_chunk = int(sr * chunk_ms / 1000) * 2
    tail_bytes = int(sr * tail_silence_ms / 1000) * 2
    silence = b"\x00\x00" * (tail_bytes // 2)

    t0 = time.perf_counter()
    first_ms = None
    final_text = None
    n_chunks = 0

    off = 0
    while off < len(pcm):
        b = pcm[off : off + bytes_per_chunk]
        off += bytes_per_chunk
        stt.accept_audio(AudioChunk(pcm16_bytes=b, sample_rate=sr, channels=1))
        n_chunks += 1
        for result in stt.poll_result():
            if not result.text:
                continue
            if first_ms is None:
                first_ms = int((time.perf_counter() - t0) * 1000)
            if result.is_final:
                final_text = result.text

    stt.accept_audio(AudioChunk(pcm16_bytes=silence, sample_rate=sr, channels=1))
    for _ in range(20):
        for result in stt.poll_result():
            if not result.text:
                continue
            if first_ms is None:
                first_ms = int((time.perf_counter() - t0) * 1000)
            if result.is_final:
                final_text = result.text
        if final_text:
            break
        time.sleep(0.05)

    elapsed = time.perf_counter() - t0
    stt.close()
    audio_sec = len(pcm) / 2 / sr
    return {
        "first_partial_latency_ms": first_ms,
        "final_text": final_text,
        "audio_sec": audio_sec,
        "rtf": elapsed / audio_sec if audio_sec > 0 else None,
        "chunks": n_chunks,
    }


def main():
    ap = argparse.ArgumentParser(description="Compare STT results before and after lightweight noise suppression.")
    ap.add_argument("wav", help="16kHz mono int16 wav")
    ap.add_argument("--chunk-ms", type=int, default=200)
    ap.add_argument("--tail-silence-ms", type=int, default=1500)
    ap.add_argument("--output-wav", help="Optional enhanced wav output path")
    ap.add_argument("--noise-floor", type=float, default=None)
    ap.add_argument("--noise-alpha", type=float, default=None)
    ap.add_argument("--spectral-alpha", type=float, default=None)
    ap.add_argument("--min-gain", type=float, default=None)
    ap.add_argument("--over-subtraction", type=float, default=None)
    ap.add_argument("--speech-margin", type=float, default=None)
    args = ap.parse_args()

    proc = psutil.Process()
    start_rss = proc.memory_info().rss
    pcm, sr = read_wav_int16_mono(args.wav)
    if sr != 16000:
        raise RuntimeError("wav sample rate must be 16000")

    suppressor = StreamingNoiseSuppressor(state=NoiseSuppressorState(enabled=True), sample_rate=sr)
    suppressor.update_config(
        enabled=True,
        noise_floor=args.noise_floor,
        noise_alpha=args.noise_alpha,
        spectral_alpha=args.spectral_alpha,
        min_gain=args.min_gain,
        over_subtraction=args.over_subtraction,
        speech_margin=args.speech_margin,
    )
    enhanced = suppressor.process(pcm) + suppressor.flush()

    if args.output_wav:
        out_path = Path(args.output_wav).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_wav_int16_mono(str(out_path), enhanced, sr)

    raw_result = run_stt_once(
        pcm=pcm,
        sr=sr,
        chunk_ms=args.chunk_ms,
        tail_silence_ms=args.tail_silence_ms,
    )
    enhanced_result = run_stt_once(
        pcm=enhanced,
        sr=sr,
        chunk_ms=args.chunk_ms,
        tail_silence_ms=args.tail_silence_ms,
    )
    end_rss = proc.memory_info().rss

    payload = {
        "ok": True,
        "input_path": str(Path(args.wav).resolve()),
        "enhanced_output_path": str(Path(args.output_wav).resolve()) if args.output_wav else None,
        "noise_suppression": suppressor.collect_metrics(),
        "raw_stt": raw_result,
        "enhanced_stt": enhanced_result,
        "rss_mb": start_rss / 1024 / 1024,
        "end_rss_mb": end_rss / 1024 / 1024,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
