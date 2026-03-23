import argparse
import json
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend import database
from backend.api.voice_session import SpeechState, VoiceSessionRunner


class DummyWebSocket:
    async def send_text(self, text: str):
        return None

    async def send_bytes(self, data: bytes):
        return None

    async def close(self, code=None):
        return None


class DummyTts:
    def __init__(self):
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


def read_wav_int16_mono(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        if channels != 1 or sample_width != 2:
            raise RuntimeError(f"{path} must be mono int16 wav")
        if sample_rate != 16000:
            raise RuntimeError(f"{path} sample rate must be 16000, got {sample_rate}")
        return wf.readframes(wf.getnframes())


def iter_manifest(path: Path) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid json on line {line_no}: {exc}") from exc
        if "path" not in item:
            raise RuntimeError(f"manifest line {line_no} missing path")
        samples.append(item)
    return samples


def make_runner(force_energy_only: bool) -> VoiceSessionRunner:
    runner = VoiceSessionRunner(websocket=DummyWebSocket(), session_id="barge-in-eval")
    runner.tts = DummyTts()
    runner.barge_in.speech_state = SpeechState.SPEAKING
    runner.send_enabled = True
    if force_energy_only:
        runner.use_native_vad = False
        runner.vad = None
    return runner


def evaluate_sample(
    sample: Dict[str, Any],
    manifest_dir: Path,
    force_energy_only: bool,
) -> Dict[str, Any]:
    wav_path = Path(sample["path"])
    if not wav_path.is_absolute():
        wav_path = (manifest_dir / wav_path).resolve()
    pcm = read_wav_int16_mono(wav_path)

    runner = make_runner(force_energy_only=force_energy_only)
    if isinstance(sample.get("config"), dict):
        cfg = sample["config"]
        for key, value in cfg.items():
            if hasattr(runner.barge_in, key):
                setattr(runner.barge_in, key, value)

    start_offset_ms = int(sample.get("tts_offset_ms", 0))
    runner.last_tts_chunk_time = time.time() - (start_offset_ms / 1000.0)
    runner.last_tts_end_time = 0.0

    first_pending_ms: Optional[int] = None
    first_interrupted_ms: Optional[int] = None
    max_score = 0.0
    frame_bytes = runner.frame_bytes

    for idx in range(0, len(pcm), frame_bytes):
        frame = pcm[idx : idx + frame_bytes]
        if len(frame) < frame_bytes:
            frame = frame + b"\x00" * (frame_bytes - len(frame))

        prev_state = runner.barge_in.speech_state
        runner._handle_barge_in(frame)
        frame_end_ms = ((idx // frame_bytes) + 1) * runner.barge_in.frame_ms
        max_score = max(max_score, runner.barge_in.last_score)

        if prev_state != SpeechState.INTERRUPT_PENDING and runner.barge_in.speech_state == SpeechState.INTERRUPT_PENDING:
            first_pending_ms = frame_end_ms
        if runner.barge_in.speech_state == SpeechState.INTERRUPTED:
            first_interrupted_ms = frame_end_ms
            break

    expected_interrupt = sample.get("expected_interrupt")
    if expected_interrupt is None:
        label = str(sample.get("label", "")).lower()
        expected_interrupt = label in {"interrupt", "positive", "1", "true", "yes"}

    expected_interrupt_ms = sample.get("expected_interrupt_ms")
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
        "final_state": runner.barge_in.speech_state.value,
    }


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    positives = [r for r in results if r["label"] == "interrupt"]
    negatives = [r for r in results if r["label"] == "no_interrupt"]
    tp = sum(1 for r in positives if r["predicted_interrupt"])
    fn = sum(1 for r in positives if not r["predicted_interrupt"])
    fp = sum(1 for r in negatives if r["predicted_interrupt"])
    tn = sum(1 for r in negatives if not r["predicted_interrupt"])

    detected_positives = [r for r in positives if r["first_interrupted_ms"] is not None]
    latency_values = [r["first_interrupted_ms"] for r in detected_positives if r["first_interrupted_ms"] is not None]
    delta_values = [r["latency_delta_ms"] for r in detected_positives if r["latency_delta_ms"] is not None]

    total = len(results)
    false_interrupt_rate = fp / len(negatives) if negatives else 0.0
    miss_rate = fn / len(positives) if positives else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    return {
        "total_samples": total,
        "positive_samples": len(positives),
        "negative_samples": len(negatives),
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "false_interrupt_rate": round(false_interrupt_rate, 4),
        "miss_rate": round(miss_rate, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "avg_detect_latency_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else None,
        "avg_latency_delta_ms": round(sum(delta_values) / len(delta_values), 2) if delta_values else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline evaluator for adaptive barge-in detection.")
    ap.add_argument("manifest", help="JSONL manifest. Each line should contain path and label/expected_interrupt.")
    ap.add_argument("--output-json", help="Optional path to save evaluation result JSON.")
    ap.add_argument("--force-energy-only", action="store_true", help="Disable webrtcvad and evaluate energy fallback only.")
    args = ap.parse_args()

    database.init_db()
    manifest_path = Path(args.manifest).resolve()
    samples = iter_manifest(manifest_path)
    results = [
        evaluate_sample(sample, manifest_path.parent, force_energy_only=args.force_energy_only)
        for sample in samples
    ]
    summary = summarize(results)
    payload = {
        "manifest": str(manifest_path),
        "force_energy_only": args.force_energy_only,
        "summary": summary,
        "results": results,
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.output_json:
        out_path = Path(args.output_json).resolve()
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
