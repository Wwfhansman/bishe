import json
import time

import psutil

from backend.voice import create_tts_service, load_voice_registry


def main():
    proc = psutil.Process()
    start_rss = proc.memory_info().rss
    text = "你好，我是妮妮。"
    r = load_voice_registry()
    tts = create_tts_service(r)
    tts.initialize()
    sr = int(getattr(tts, "sample_rate", 0) or 0)
    t0 = time.perf_counter()
    first_ms = None
    total_bytes = 0
    chunk_count = 0
    for ch in tts.synthesize_stream(text):
        if getattr(ch, "is_final", False):
            break
        b = getattr(ch, "pcm16_bytes", b"")
        if not b:
            continue
        if first_ms is None:
            first_ms = int((time.perf_counter() - t0) * 1000)
        total_bytes += len(b)
        chunk_count += 1
    t1 = time.perf_counter()
    tts.close()
    end_rss = proc.memory_info().rss
    audio_sec = None
    rtf = None
    if sr > 0 and total_bytes > 0:
        audio_sec = total_bytes / 2 / sr
        if audio_sec > 0:
            rtf = (t1 - t0) / audio_sec
    out = {
        "ok": True,
        "provider": "tts",
        "sample_rate": sr,
        "first_audio_latency_ms": first_ms,
        "chunk_count": chunk_count,
        "total_bytes": total_bytes,
        "audio_sec": audio_sec,
        "rtf": rtf,
        "rss_mb": start_rss / 1024 / 1024,
        "end_rss_mb": end_rss / 1024 / 1024,
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

