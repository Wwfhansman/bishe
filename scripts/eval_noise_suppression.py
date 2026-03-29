import argparse
import json
import wave
from pathlib import Path

from backend.voice import NoiseSuppressorState, StreamingNoiseSuppressor


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


def main():
    ap = argparse.ArgumentParser(description="Offline evaluator for the lightweight noise suppressor.")
    ap.add_argument("wav", help="16kHz mono int16 wav")
    ap.add_argument("--output-wav", help="Optional path to save enhanced wav")
    ap.add_argument("--enabled", action="store_true", help="Enable suppression explicitly")
    ap.add_argument("--noise-floor", type=float, default=None)
    ap.add_argument("--noise-alpha", type=float, default=None)
    ap.add_argument("--spectral-alpha", type=float, default=None)
    ap.add_argument("--min-gain", type=float, default=None)
    ap.add_argument("--over-subtraction", type=float, default=None)
    ap.add_argument("--speech-margin", type=float, default=None)
    args = ap.parse_args()

    pcm, sr = read_wav_int16_mono(args.wav)
    if sr != 16000:
        raise RuntimeError("wav sample rate must be 16000")

    state = NoiseSuppressorState(enabled=True)
    suppressor = StreamingNoiseSuppressor(state=state, sample_rate=sr)
    suppressor.update_config(
        enabled=True if args.enabled else state.enabled,
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

    input_energy = suppressor.frame_energy(pcm)
    output_energy = suppressor.frame_energy(enhanced)
    payload = {
        "ok": True,
        "input_path": str(Path(args.wav).resolve()),
        "output_path": str(Path(args.output_wav).resolve()) if args.output_wav else None,
        "input_bytes": len(pcm),
        "output_bytes": len(enhanced),
        "input_energy": round(input_energy, 2),
        "output_energy": round(output_energy, 2),
        "energy_ratio": round(output_energy / max(input_energy, 1e-6), 4),
        "noise_suppression": suppressor.collect_metrics(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
