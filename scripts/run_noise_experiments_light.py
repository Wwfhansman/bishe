import argparse
import csv
import json
import wave
from pathlib import Path

import numpy as np


def read_wav_int16_mono(path):
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        if channels != 1 or sample_width != 2:
            raise RuntimeError("{} must be mono int16 wav".format(path))
        return wf.readframes(wf.getnframes()), sample_rate


def write_wav_int16_mono(path, pcm, sample_rate):
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)


class LightweightNoiseSuppressor:
    def __init__(
        self,
        sample_rate=16000,
        frame_ms=20,
        noise_floor=800.0,
        noise_alpha=0.08,
        spectral_alpha=0.12,
        min_gain=0.35,
        over_subtraction=1.1,
        speech_margin=1.8,
    ):
        self.sample_rate = int(sample_rate)
        self.frame_ms = int(frame_ms)
        self.frame_bytes = int(self.sample_rate * self.frame_ms / 1000) * 2
        self.noise_floor = float(noise_floor)
        self.noise_alpha = float(noise_alpha)
        self.spectral_alpha = float(spectral_alpha)
        self.min_gain = float(min_gain)
        self.over_subtraction = float(over_subtraction)
        self.speech_margin = float(speech_margin)
        self.noise_mag = None

    def frame_energy(self, frame):
        samples = np.frombuffer(frame, dtype=np.int16)
        if samples.size == 0:
            return 0.0
        return float(np.mean(np.abs(samples)))

    def process_frame(self, frame):
        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            return frame, 1.0

        input_energy = float(np.mean(np.abs(samples)))
        speech_like = input_energy > self.noise_floor * self.speech_margin

        spectrum = np.fft.rfft(samples)
        magnitude = np.abs(spectrum).astype(np.float32)
        phase = np.angle(spectrum)

        if self.noise_mag is None:
            self.noise_mag = magnitude.copy()
        else:
            alpha = self.spectral_alpha * (0.1 if speech_like else 1.0)
            self.noise_mag = (1.0 - alpha) * self.noise_mag + alpha * magnitude

        denom = np.maximum(magnitude, 1e-6)
        raw_gain = 1.0 - self.over_subtraction * (self.noise_mag / denom)
        gain = np.clip(raw_gain, self.min_gain, 1.0)
        enhanced_mag = magnitude * gain
        enhanced = np.fft.irfft(enhanced_mag * np.exp(1j * phase), n=samples.size)
        enhanced = np.clip(np.round(enhanced), -32768, 32767).astype(np.int16)

        alpha = self.noise_alpha * (0.2 if speech_like else 1.0)
        self.noise_floor = self.noise_floor * (1.0 - alpha) + input_energy * alpha
        self.noise_floor = max(50.0, self.noise_floor)

        return enhanced.tobytes(), float(np.mean(gain))

    def process(self, pcm):
        out = bytearray()
        gains = []
        input_energies = []
        output_energies = []

        for idx in range(0, len(pcm), self.frame_bytes):
            frame = pcm[idx : idx + self.frame_bytes]
            if len(frame) < self.frame_bytes:
                frame = frame + b"\x00" * (self.frame_bytes - len(frame))
                trim = len(pcm[idx : idx + self.frame_bytes])
            else:
                trim = None

            input_energies.append(self.frame_energy(frame))
            enhanced, gain_mean = self.process_frame(frame)
            gains.append(gain_mean)
            output_energies.append(self.frame_energy(enhanced))
            if trim is not None:
                out.extend(enhanced[:trim])
            else:
                out.extend(enhanced)

        return bytes(out), {
            "input_energy_mean": round(sum(input_energies) / len(input_energies), 2) if input_energies else 0.0,
            "output_energy_mean": round(sum(output_energies) / len(output_energies), 2) if output_energies else 0.0,
            "gain_mean": round(sum(gains) / len(gains), 4) if gains else 1.0,
            "final_noise_floor": round(self.noise_floor, 2),
        }


def load_refs(path):
    rows = []
    with open(str(path), "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(description="Run lightweight noise suppression experiments on STT wav samples.")
    ap.add_argument("--refs", default="samples/stt_refs.csv")
    ap.add_argument("--audio-dir", default="samples/stt")
    ap.add_argument("--enhanced-dir", default="samples/outputs/enhanced_stt")
    ap.add_argument("--output-json", default="samples/outputs/noise_experiment_summary.json")
    ap.add_argument("--output-markdown", default="samples/outputs/noise_experiment_summary.md")
    args = ap.parse_args()

    refs = load_refs(Path(args.refs))
    audio_dir = Path(args.audio_dir)
    enhanced_dir = Path(args.enhanced_dir)
    enhanced_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for row in refs:
        wav_path = audio_dir / Path(row["file"]).with_suffix(".wav")
        pcm, sr = read_wav_int16_mono(wav_path)
        suppressor = LightweightNoiseSuppressor(sample_rate=sr)
        enhanced_pcm, metrics = suppressor.process(pcm)
        out_path = enhanced_dir / wav_path.name
        write_wav_int16_mono(out_path, enhanced_pcm, sr)

        energy_drop = metrics["input_energy_mean"] - metrics["output_energy_mean"]
        ratio = (
            round(metrics["output_energy_mean"] / metrics["input_energy_mean"], 4)
            if metrics["input_energy_mean"] > 0
            else None
        )
        result = {
            "file": wav_path.name,
            "scene": row["scene"],
            "text": row["text"],
            "enhanced_path": str(out_path),
            "input_energy_mean": metrics["input_energy_mean"],
            "output_energy_mean": metrics["output_energy_mean"],
            "energy_drop": round(energy_drop, 2),
            "energy_ratio": ratio,
            "gain_mean": metrics["gain_mean"],
            "final_noise_floor": metrics["final_noise_floor"],
        }
        results.append(result)

    summary = {
        "sample_count": len(results),
        "avg_input_energy": round(sum(r["input_energy_mean"] for r in results) / len(results), 2),
        "avg_output_energy": round(sum(r["output_energy_mean"] for r in results) / len(results), 2),
        "avg_energy_drop": round(sum(r["energy_drop"] for r in results) / len(results), 2),
        "avg_gain_mean": round(sum(r["gain_mean"] for r in results) / len(results), 4),
    }

    payload = {"summary": summary, "results": results}
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 噪声抑制实验汇总",
        "",
        "## 总体结果",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        "| 样本数 | {} |".format(summary["sample_count"]),
        "| 平均输入能量 | {} |".format(summary["avg_input_energy"]),
        "| 平均输出能量 | {} |".format(summary["avg_output_energy"]),
        "| 平均能量下降 | {} |".format(summary["avg_energy_drop"]),
        "| 平均增益 | {} |".format(summary["avg_gain_mean"]),
        "",
        "## 分样本结果",
        "",
        "| 文件 | 场景 | 输入能量 | 输出能量 | 能量下降 | 能量比 | 平均增益 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in results:
        lines.append(
            "| {file} | {scene} | {input_energy_mean} | {output_energy_mean} | {energy_drop} | {energy_ratio} | {gain_mean} |".format(
                **row
            )
        )
    Path(args.output_markdown).write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
