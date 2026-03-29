import argparse
import audioop
import json
import time
import wave
from pathlib import Path

from backend.config import (
    BARGE_IN_ADAPTIVE_ENERGY_MARGIN,
    BARGE_IN_CONFIRM_SCORE,
    BARGE_IN_ECHO_SUPPRESSION_WINDOW_MS,
    BARGE_IN_FRAME_MS,
    BARGE_IN_LATE_PEAK_MIN_FRAMES,
    BARGE_IN_LATE_PLATEAU_LIMIT,
    BARGE_IN_LATE_WINDOW_MS,
    BARGE_IN_MIN_SPEECH_MS,
    BARGE_IN_NOISE_FLOOR,
    BARGE_IN_NOISE_FLOOR_ALPHA,
    BARGE_IN_PENDING_SCORE,
    BARGE_IN_PEAK_GATE_MIN,
    BARGE_IN_PEAK_GATE_SCALE,
    BARGE_IN_PEAK_MIN_FRAMES,
    BARGE_IN_PEAK_PLATEAU_LIMIT,
    BARGE_IN_SILENCE_END_FRAMES,
    BARGE_IN_SILENCE_RESET_FRAMES,
    BARGE_IN_SPEECH_RATIO_WINDOW,
    BARGE_IN_START_FRAMES,
)


def read_wav(path: Path):
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        if channels != 1 or sample_width != 2:
            raise RuntimeError(f"{path} must be mono int16 wav")
        if sample_rate != 16000:
            raise RuntimeError(f"{path} sample rate must be 16000, got {sample_rate}")
        return wf.readframes(wf.getnframes())


def iter_manifest(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def frame_energy(frame: bytes) -> float:
    if not frame:
        return 0.0
    return float(audioop.rms(frame, 2))


def confirm_frames_required(score: float, frame_ms: int, min_speech_ms: int, confirm_score: float) -> int:
    base_frames = max(1, min_speech_ms // frame_ms)
    if score >= confirm_score + 0.75:
        return max(1, base_frames // 3)
    if score >= confirm_score + 0.35:
        return max(1, base_frames // 2)
    return base_frames


def evaluate_one(
    wav_path: Path,
    expected_interrupt: bool,
    expected_interrupt_ms,
    frame_ms: int,
    start_frames: int,
    min_speech_ms: int,
    pending_score: float,
    confirm_score: float,
    adaptive_energy_margin: float,
    noise_floor_alpha: float,
    speech_ratio_window: int,
    silence_end_frames: int,
    silence_reset_frames: int,
    noise_floor: float,
    peak_gate_min: float,
    peak_gate_scale: float,
    peak_min_frames: int,
    peak_plateau_limit: int,
    late_window_ms: int,
    late_peak_min_frames: int,
    late_plateau_limit: int,
):
    pcm = read_wav(wav_path)
    frame_bytes = int(16000 * frame_ms / 1000) * 2

    current_noise_floor = float(noise_floor)
    recent_flags = []
    speaking_frames = 0
    silence_frames = 0
    peak_frames = 0
    peak_run = 0
    max_peak_run = 0
    state = "speaking"
    first_pending_ms = None
    first_interrupted_ms = None
    max_score = 0.0
    last_peak_gate = 0.0
    pending_tts_elapsed_ms = None

    for idx in range(0, len(pcm), frame_bytes):
        frame = pcm[idx: idx + frame_bytes]
        if len(frame) < frame_bytes:
            frame = frame + b"\x00" * (frame_bytes - len(frame))

        energy = frame_energy(frame)
        energy_gain = max(0.0, (energy - max(current_noise_floor, 1.0)) / max(current_noise_floor, 1.0))
        speech_like = energy_gain >= adaptive_energy_margin or energy >= max(current_noise_floor * 1.25, current_noise_floor + 120.0)

        recent_flags.append(1 if speech_like else 0)
        if len(recent_flags) > speech_ratio_window:
            recent_flags.pop(0)
        speech_ratio = (sum(recent_flags) / len(recent_flags)) if recent_flags else 0.0

        energy_score = min(1.5, energy_gain / max(adaptive_energy_margin, 0.05))
        vad_score = 0.8 if speech_like else 0.0
        ratio_score = min(1.0, speech_ratio * 1.2)
        score = max(0.0, vad_score + energy_score + ratio_score)
        max_score = max(max_score, score)
        peak_gate = max(peak_gate_min, current_noise_floor * peak_gate_scale)
        last_peak_gate = peak_gate
        high_peak = energy >= peak_gate

        frame_end_ms = ((idx // frame_bytes) + 1) * frame_ms

        if speech_like:
            speaking_frames += 1
            silence_frames = 0
            if high_peak:
                peak_frames += 1
                peak_run += 1
                max_peak_run = max(max_peak_run, peak_run)
            else:
                peak_run = 0
            if state == "speaking" and speaking_frames >= start_frames and score >= pending_score:
                state = "interrupt_pending"
                if first_pending_ms is None:
                    first_pending_ms = frame_end_ms
                pending_tts_elapsed_ms = frame_end_ms

            if state == "interrupt_pending":
                need = confirm_frames_required(
                    score=score,
                    frame_ms=frame_ms,
                    min_speech_ms=min_speech_ms,
                    confirm_score=confirm_score,
                )
                required_peak_frames = peak_min_frames
                allowed_peak_run = peak_plateau_limit
                if pending_tts_elapsed_ms is not None and pending_tts_elapsed_ms > late_window_ms:
                    required_peak_frames = max(required_peak_frames, late_peak_min_frames)
                    allowed_peak_run = min(allowed_peak_run, late_plateau_limit)
                if speaking_frames >= need and score >= confirm_score:
                    if peak_frames >= required_peak_frames and max_peak_run <= allowed_peak_run:
                        state = "interrupted"
                        first_interrupted_ms = frame_end_ms
                        break
        else:
            silence_frames += 1
            peak_run = 0
            if silence_frames > silence_reset_frames:
                speaking_frames = 0
                peak_frames = 0
                max_peak_run = 0
            if state == "interrupt_pending" and silence_frames >= silence_end_frames:
                state = "speaking"
                speaking_frames = 0
                silence_frames = 0
                peak_frames = 0
                peak_run = 0
                max_peak_run = 0
                pending_tts_elapsed_ms = None

        alpha = noise_floor_alpha * (0.25 if speech_like else 1.0)
        current_noise_floor = current_noise_floor * (1.0 - alpha) + energy * alpha
        current_noise_floor = max(50.0, current_noise_floor)

    latency_delta_ms = None
    if expected_interrupt and expected_interrupt_ms is not None and first_interrupted_ms is not None:
        latency_delta_ms = first_interrupted_ms - int(expected_interrupt_ms)

    return {
        "path": str(wav_path),
        "label": "interrupt" if expected_interrupt else "no_interrupt",
        "expected_interrupt_ms": expected_interrupt_ms,
        "first_pending_ms": first_pending_ms,
        "first_interrupted_ms": first_interrupted_ms,
        "predicted_interrupt": first_interrupted_ms is not None,
        "latency_delta_ms": latency_delta_ms,
        "max_score": round(max_score, 3),
        "final_state": state,
        "peak_frames": peak_frames,
        "max_peak_run": max_peak_run,
        "last_peak_gate": round(last_peak_gate, 2),
        "pending_tts_elapsed_ms": pending_tts_elapsed_ms,
    }


def summarize(results):
    positives = [r for r in results if r["label"] == "interrupt"]
    negatives = [r for r in results if r["label"] == "no_interrupt"]
    tp = sum(1 for r in positives if r["predicted_interrupt"])
    fn = sum(1 for r in positives if not r["predicted_interrupt"])
    fp = sum(1 for r in negatives if r["predicted_interrupt"])
    tn = sum(1 for r in negatives if not r["predicted_interrupt"])
    deltas = [r["latency_delta_ms"] for r in positives if r["latency_delta_ms"] is not None]

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    false_interrupt_rate = fp / len(negatives) if negatives else 0.0
    miss_rate = fn / len(positives) if positives else 0.0

    return {
        "total_samples": len(results),
        "positive_samples": len(positives),
        "negative_samples": len(negatives),
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "false_interrupt_rate": round(false_interrupt_rate, 4),
        "miss_rate": round(miss_rate, 4),
        "avg_latency_delta_ms": round(sum(deltas) / len(deltas), 2) if deltas else None,
    }


def main():
    ap = argparse.ArgumentParser(description="Lightweight offline barge-in evaluator without project runtime dependencies.")
    ap.add_argument("manifest")
    ap.add_argument("--output-json")
    ap.add_argument("--frame-ms", type=int, default=BARGE_IN_FRAME_MS)
    ap.add_argument("--start-frames", type=int, default=BARGE_IN_START_FRAMES)
    ap.add_argument("--min-speech-ms", type=int, default=300)
    ap.add_argument("--pending-score", type=float, default=BARGE_IN_PENDING_SCORE)
    ap.add_argument("--confirm-score", type=float, default=BARGE_IN_CONFIRM_SCORE)
    ap.add_argument("--adaptive-energy-margin", type=float, default=BARGE_IN_ADAPTIVE_ENERGY_MARGIN)
    ap.add_argument("--noise-floor-alpha", type=float, default=BARGE_IN_NOISE_FLOOR_ALPHA)
    ap.add_argument("--speech-ratio-window", type=int, default=BARGE_IN_SPEECH_RATIO_WINDOW)
    ap.add_argument("--silence-end-frames", type=int, default=BARGE_IN_SILENCE_END_FRAMES)
    ap.add_argument("--silence-reset-frames", type=int, default=BARGE_IN_SILENCE_RESET_FRAMES)
    ap.add_argument("--noise-floor", type=float, default=BARGE_IN_NOISE_FLOOR)
    ap.add_argument("--peak-gate-min", type=float, default=BARGE_IN_PEAK_GATE_MIN)
    ap.add_argument("--peak-gate-scale", type=float, default=BARGE_IN_PEAK_GATE_SCALE)
    ap.add_argument("--peak-min-frames", type=int, default=BARGE_IN_PEAK_MIN_FRAMES)
    ap.add_argument("--peak-plateau-limit", type=int, default=BARGE_IN_PEAK_PLATEAU_LIMIT)
    ap.add_argument("--late-window-ms", type=int, default=BARGE_IN_LATE_WINDOW_MS)
    ap.add_argument("--late-peak-min-frames", type=int, default=BARGE_IN_LATE_PEAK_MIN_FRAMES)
    ap.add_argument("--late-plateau-limit", type=int, default=BARGE_IN_LATE_PLATEAU_LIMIT)
    args = ap.parse_args()

    manifest_path = Path(args.manifest).resolve()
    samples = iter_manifest(manifest_path)
    results = []

    for sample in samples:
        wav_path = Path(sample["path"])
        if not wav_path.is_absolute():
            wav_path = (manifest_path.parent / wav_path).resolve()
        label = str(sample.get("label", "")).lower()
        expected_interrupt = label == "interrupt"
        results.append(
            evaluate_one(
                wav_path=wav_path,
                expected_interrupt=expected_interrupt,
                expected_interrupt_ms=sample.get("expected_interrupt_ms"),
                frame_ms=args.frame_ms,
                start_frames=args.start_frames,
                min_speech_ms=args.min_speech_ms,
                pending_score=args.pending_score,
                confirm_score=args.confirm_score,
                adaptive_energy_margin=args.adaptive_energy_margin,
                noise_floor_alpha=args.noise_floor_alpha,
                speech_ratio_window=args.speech_ratio_window,
                silence_end_frames=args.silence_end_frames,
                silence_reset_frames=args.silence_reset_frames,
                noise_floor=args.noise_floor,
                peak_gate_min=args.peak_gate_min,
                peak_gate_scale=args.peak_gate_scale,
                peak_min_frames=args.peak_min_frames,
                peak_plateau_limit=args.peak_plateau_limit,
                late_window_ms=args.late_window_ms,
                late_peak_min_frames=args.late_peak_min_frames,
                late_plateau_limit=args.late_plateau_limit,
            )
        )

    payload = {
        "manifest": str(manifest_path),
        "params": {
            "frame_ms": args.frame_ms,
            "start_frames": args.start_frames,
            "min_speech_ms": args.min_speech_ms,
            "pending_score": args.pending_score,
            "confirm_score": args.confirm_score,
            "adaptive_energy_margin": args.adaptive_energy_margin,
            "noise_floor_alpha": args.noise_floor_alpha,
            "speech_ratio_window": args.speech_ratio_window,
            "silence_end_frames": args.silence_end_frames,
            "silence_reset_frames": args.silence_reset_frames,
            "noise_floor": args.noise_floor,
            "peak_gate_min": args.peak_gate_min,
            "peak_gate_scale": args.peak_gate_scale,
            "peak_min_frames": args.peak_min_frames,
            "peak_plateau_limit": args.peak_plateau_limit,
            "late_window_ms": args.late_window_ms,
            "late_peak_min_frames": args.late_peak_min_frames,
            "late_plateau_limit": args.late_plateau_limit,
            "echo_suppression_window_ms": BARGE_IN_ECHO_SUPPRESSION_WINDOW_MS,
        },
        "summary": summarize(results),
        "results": results,
        "generated_at": int(time.time()),
    }

    if args.output_json:
      Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
      Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
