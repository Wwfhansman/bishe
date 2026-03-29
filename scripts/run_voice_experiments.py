import argparse
import json
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from backend import database
from backend.api.voice_session import SpeechState, VoiceSessionRunner
from backend.voice import (
    AudioChunk,
    NoiseSuppressorState,
    StreamingNoiseSuppressor,
    create_stt_service,
    load_voice_registry,
)


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


def read_wav_int16_mono(path: str):
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        if channels != 1 or sample_width != 2:
            raise RuntimeError("wav must be mono int16")
        return wf.readframes(wf.getnframes()), sample_rate


def write_wav_int16_mono(path: str, pcm: bytes, sample_rate: int):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


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


def build_noise_config(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "noise_floor": args.noise_floor,
        "noise_alpha": args.noise_alpha,
        "spectral_alpha": args.spectral_alpha,
        "min_gain": args.min_gain,
        "over_subtraction": args.over_subtraction,
        "speech_margin": args.speech_margin,
    }


def apply_noise_suppression(
    pcm: bytes,
    sample_rate: int,
    config: Dict[str, Any],
) -> tuple[bytes, Dict[str, Any]]:
    suppressor = StreamingNoiseSuppressor(state=NoiseSuppressorState(enabled=True), sample_rate=sample_rate)
    suppressor.update_config(enabled=True, **config)
    enhanced = suppressor.process(pcm) + suppressor.flush()
    metrics = suppressor.collect_metrics()
    metrics["input_energy"] = round(suppressor.frame_energy(pcm), 2)
    metrics["output_energy"] = round(suppressor.frame_energy(enhanced), 2)
    metrics["energy_ratio"] = round(metrics["output_energy"] / max(metrics["input_energy"], 1e-6), 4)
    return enhanced, metrics


def run_stt_once(pcm: bytes, sr: int, chunk_ms: int, tail_silence_ms: int) -> Dict[str, Any]:
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


def make_runner(force_energy_only: bool) -> VoiceSessionRunner:
    runner = VoiceSessionRunner(websocket=DummyWebSocket(), session_id="barge-in-experiment")
    runner.tts = DummyTts()
    runner.barge_in.speech_state = SpeechState.SPEAKING
    runner.send_enabled = True
    if force_energy_only:
        runner.use_native_vad = False
        runner.vad = None
    return runner


def evaluate_barge_sample(
    sample: Dict[str, Any],
    manifest_dir: Path,
    force_energy_only: bool,
    noise_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    wav_path = Path(sample["path"])
    if not wav_path.is_absolute():
        wav_path = (manifest_dir / wav_path).resolve()
    pcm, sr = read_wav_int16_mono(str(wav_path))
    if sr != 16000:
        raise RuntimeError(f"{wav_path} sample rate must be 16000, got {sr}")

    ns_metrics = None
    processed_pcm = pcm
    merged_noise_cfg = dict(noise_config or {})
    if isinstance(sample.get("noise_suppression_config"), dict):
        merged_noise_cfg.update(sample["noise_suppression_config"])
    if merged_noise_cfg:
        processed_pcm, ns_metrics = apply_noise_suppression(
            pcm=pcm,
            sample_rate=sr,
            config=merged_noise_cfg,
        )

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

    for idx in range(0, len(processed_pcm), frame_bytes):
        frame = processed_pcm[idx : idx + frame_bytes]
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
        "noise_suppression": ns_metrics,
    }


def summarize_barge_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    positives = [r for r in results if r["label"] == "interrupt"]
    negatives = [r for r in results if r["label"] == "no_interrupt"]
    tp = sum(1 for r in positives if r["predicted_interrupt"])
    fn = sum(1 for r in positives if not r["predicted_interrupt"])
    fp = sum(1 for r in negatives if r["predicted_interrupt"])
    tn = sum(1 for r in negatives if not r["predicted_interrupt"])

    detected_positives = [r for r in positives if r["first_interrupted_ms"] is not None]
    latency_values = [r["first_interrupted_ms"] for r in detected_positives if r["first_interrupted_ms"] is not None]
    delta_values = [r["latency_delta_ms"] for r in detected_positives if r["latency_delta_ms"] is not None]

    false_interrupt_rate = fp / len(negatives) if negatives else 0.0
    miss_rate = fn / len(positives) if positives else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "total_samples": len(results),
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
        "f1": round(f1, 4),
        "avg_detect_latency_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else None,
        "avg_latency_delta_ms": round(sum(delta_values) / len(delta_values), 2) if delta_values else None,
    }


def markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = "\n".join("| " + " | ".join(str(v) for v in row) + " |" for row in rows)
    return "\n".join([head, sep, body]) if body else "\n".join([head, sep])


def render_markdown(payload: Dict[str, Any]) -> str:
    lines: List[str] = ["# 语音实验结果汇总", ""]

    if "noise_suppression_eval" in payload:
        noise_eval = payload["noise_suppression_eval"]
        lines.extend(
            [
                "## 降噪结果",
                "",
                markdown_table(
                    ["指标", "数值"],
                    [
                        ["input_energy", noise_eval["input_energy"]],
                        ["output_energy", noise_eval["output_energy"]],
                        ["energy_ratio", noise_eval["energy_ratio"]],
                        ["noise_floor", noise_eval["noise_suppression"]["noise_floor"]],
                        ["last_gain_mean", noise_eval["noise_suppression"]["last_gain_mean"]],
                    ],
                ),
                "",
            ]
        )

    if "stt_comparison" in payload:
        stt = payload["stt_comparison"]
        lines.extend(
            [
                "## STT 对比",
                "",
                markdown_table(
                    ["版本", "first_partial_latency_ms", "final_text", "rtf"],
                    [
                        [
                            "raw",
                            stt["raw_stt"]["first_partial_latency_ms"],
                            stt["raw_stt"]["final_text"],
                            stt["raw_stt"]["rtf"],
                        ],
                        [
                            "enhanced",
                            stt["enhanced_stt"]["first_partial_latency_ms"],
                            stt["enhanced_stt"]["final_text"],
                            stt["enhanced_stt"]["rtf"],
                        ],
                    ],
                ),
                "",
            ]
        )

    if "barge_in_comparison" in payload:
        barge = payload["barge_in_comparison"]
        lines.extend(
            [
                "## 打断检测对比",
                "",
                markdown_table(
                    ["版本", "precision", "recall", "f1", "false_interrupt_rate", "miss_rate", "avg_detect_latency_ms"],
                    [
                        [
                            "raw",
                            barge["raw"]["summary"]["precision"],
                            barge["raw"]["summary"]["recall"],
                            barge["raw"]["summary"]["f1"],
                            barge["raw"]["summary"]["false_interrupt_rate"],
                            barge["raw"]["summary"]["miss_rate"],
                            barge["raw"]["summary"]["avg_detect_latency_ms"],
                        ],
                        [
                            "enhanced",
                            barge["enhanced"]["summary"]["precision"],
                            barge["enhanced"]["summary"]["recall"],
                            barge["enhanced"]["summary"]["f1"],
                            barge["enhanced"]["summary"]["false_interrupt_rate"],
                            barge["enhanced"]["summary"]["miss_rate"],
                            barge["enhanced"]["summary"]["avg_detect_latency_ms"],
                        ],
                    ],
                ),
                "",
            ]
        )

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Unified voice experiment runner for noise suppression, STT, and barge-in evaluation.")
    ap.add_argument("--wav", help="16kHz mono int16 wav for noise/STT experiments")
    ap.add_argument("--manifest", help="JSONL manifest for barge-in experiments")
    ap.add_argument("--output-json", help="Optional path to save merged JSON result")
    ap.add_argument("--output-markdown", help="Optional path to save a markdown summary")
    ap.add_argument("--enhanced-wav", help="Optional path to save enhanced wav from --wav")
    ap.add_argument("--chunk-ms", type=int, default=200)
    ap.add_argument("--tail-silence-ms", type=int, default=1500)
    ap.add_argument("--force-energy-only", action="store_true", help="Disable webrtcvad for barge-in evaluation")
    ap.add_argument("--noise-floor", type=float, default=None)
    ap.add_argument("--noise-alpha", type=float, default=None)
    ap.add_argument("--spectral-alpha", type=float, default=None)
    ap.add_argument("--min-gain", type=float, default=None)
    ap.add_argument("--over-subtraction", type=float, default=None)
    ap.add_argument("--speech-margin", type=float, default=None)
    args = ap.parse_args()

    if not args.wav and not args.manifest:
        raise RuntimeError("At least one of --wav or --manifest is required")

    proc = psutil.Process()
    start_rss = proc.memory_info().rss
    payload: Dict[str, Any] = {
        "ok": True,
        "noise_suppression_config": build_noise_config(args),
    }
    noise_config = build_noise_config(args)

    if args.wav:
        pcm, sr = read_wav_int16_mono(args.wav)
        if sr != 16000:
            raise RuntimeError("wav sample rate must be 16000")
        enhanced, ns_metrics = apply_noise_suppression(pcm=pcm, sample_rate=sr, config=noise_config)
        if args.enhanced_wav:
            out_path = Path(args.enhanced_wav).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            write_wav_int16_mono(str(out_path), enhanced, sr)
        payload["noise_suppression_eval"] = {
            "input_path": str(Path(args.wav).resolve()),
            "output_path": str(Path(args.enhanced_wav).resolve()) if args.enhanced_wav else None,
            "input_energy": ns_metrics["input_energy"],
            "output_energy": ns_metrics["output_energy"],
            "energy_ratio": ns_metrics["energy_ratio"],
            "noise_suppression": ns_metrics,
        }
        payload["stt_comparison"] = {
            "raw_stt": run_stt_once(
                pcm=pcm,
                sr=sr,
                chunk_ms=args.chunk_ms,
                tail_silence_ms=args.tail_silence_ms,
            ),
            "enhanced_stt": run_stt_once(
                pcm=enhanced,
                sr=sr,
                chunk_ms=args.chunk_ms,
                tail_silence_ms=args.tail_silence_ms,
            ),
        }

    if args.manifest:
        database.init_db()
        manifest_path = Path(args.manifest).resolve()
        samples = iter_manifest(manifest_path)
        raw_results = [
            evaluate_barge_sample(
                sample,
                manifest_dir=manifest_path.parent,
                force_energy_only=args.force_energy_only,
                noise_config=None,
            )
            for sample in samples
        ]
        enhanced_results = [
            evaluate_barge_sample(
                sample,
                manifest_dir=manifest_path.parent,
                force_energy_only=args.force_energy_only,
                noise_config=noise_config,
            )
            for sample in samples
        ]
        payload["barge_in_comparison"] = {
            "manifest": str(manifest_path),
            "raw": {
                "summary": summarize_barge_results(raw_results),
                "results": raw_results,
            },
            "enhanced": {
                "summary": summarize_barge_results(enhanced_results),
                "results": enhanced_results,
            },
        }

    end_rss = proc.memory_info().rss
    payload["rss_mb"] = start_rss / 1024 / 1024
    payload["end_rss_mb"] = end_rss / 1024 / 1024

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.output_json:
        out_path = Path(args.output_json).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_markdown:
        out_path = Path(args.output_markdown).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_markdown(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
