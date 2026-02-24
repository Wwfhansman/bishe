import argparse
import json
import time
import wave

import psutil

from backend.voice import AudioChunk, create_stt_service, load_voice_registry


def read_wav_int16_mono(path: str):
    with wave.open(path, "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        sw = wf.getsampwidth()
        if ch != 1 or sw != 2:
            raise RuntimeError("wav must be mono int16")
        n = wf.getnframes()
        pcm = wf.readframes(n)
        return pcm, sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav", help="16kHz mono int16 wav")
    ap.add_argument("--chunk-ms", type=int, default=200)
    ap.add_argument("--tail-silence-ms", type=int, default=1500)
    args = ap.parse_args()

    proc = psutil.Process()
    start_rss = proc.memory_info().rss
    pcm, sr = read_wav_int16_mono(args.wav)
    if sr != 16000:
        raise RuntimeError("wav sample rate must be 16000")

    r = load_voice_registry()
    stt = create_stt_service(r)
    stt.initialize()

    bytes_per_chunk = int(sr * args.chunk_ms / 1000) * 2
    tail_bytes = int(sr * args.tail_silence_ms / 1000) * 2
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
        for r0 in stt.poll_result():
            if not r0.text:
                continue
            if first_ms is None:
                first_ms = int((time.perf_counter() - t0) * 1000)
            if r0.is_final:
                final_text = r0.text

    stt.accept_audio(AudioChunk(pcm16_bytes=silence, sample_rate=sr, channels=1))
    for _ in range(20):
        for r0 in stt.poll_result():
            if not r0.text:
                continue
            if first_ms is None:
                first_ms = int((time.perf_counter() - t0) * 1000)
            if r0.is_final:
                final_text = r0.text
        if final_text:
            break
        time.sleep(0.05)

    t1 = time.perf_counter()
    stt.close()
    end_rss = proc.memory_info().rss

    audio_sec = len(pcm) / 2 / sr
    rtf = (t1 - t0) / audio_sec if audio_sec > 0 else None
    out = {
        "ok": True,
        "provider": "stt",
        "chunk_ms": args.chunk_ms,
        "first_partial_latency_ms": first_ms,
        "final_text": final_text,
        "audio_sec": audio_sec,
        "rtf": rtf,
        "chunks": n_chunks,
        "rss_mb": start_rss / 1024 / 1024,
        "end_rss_mb": end_rss / 1024 / 1024,
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

