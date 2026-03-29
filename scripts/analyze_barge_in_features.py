import argparse
import audioop
import json
import wave
from pathlib import Path


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise RuntimeError(f"{path} must be mono int16 wav")
        if wf.getframerate() != 16000:
            raise RuntimeError(f"{path} sample rate must be 16000")
        return wf.readframes(wf.getnframes())


def iter_manifest(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def longest_run(values, threshold):
    longest = 0
    current = 0
    for value in values:
        if value >= threshold:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def analyze_one(path: Path):
    pcm = read_wav(path)
    frame_bytes = int(16000 * 0.02) * 2
    energies = []
    for idx in range(0, len(pcm), frame_bytes):
        frame = pcm[idx : idx + frame_bytes]
        if len(frame) < frame_bytes:
            frame += b"\x00" * (frame_bytes - len(frame))
        energies.append(audioop.rms(frame, 2))

    sorted_energies = sorted(energies)
    q50 = sorted_energies[len(sorted_energies) // 2]
    q90 = sorted_energies[int(len(sorted_energies) * 0.9)]
    onset = max((energies[i] - energies[i - 1]) for i in range(1, len(energies))) if len(energies) > 1 else 0
    base_05 = sum(energies[:25]) / max(1, len(energies[:25]))
    max_to_base = max(energies) / max(base_05, 1.0)

    return {
        "mean_energy": round(sum(energies) / len(energies), 2),
        "q50_energy": q50,
        "q90_energy": q90,
        "max_energy": max(energies),
        "onset_max_delta": onset,
        "base_05_energy": round(base_05, 2),
        "max_to_base_ratio": round(max_to_base, 2),
        "frames_ge_1500": sum(1 for x in energies if x >= 1500),
        "frames_ge_2000": sum(1 for x in energies if x >= 2000),
        "frames_ge_4000": sum(1 for x in energies if x >= 4000),
        "longest_run_ge_2000": longest_run(energies, 2000),
        "longest_run_ge_4000": longest_run(energies, 4000),
        "first_ge_2000_ms": next(((i + 1) * 20 for i, x in enumerate(energies) if x >= 2000), None),
    }


def main():
    ap = argparse.ArgumentParser(description="Analyze feature statistics for barge-in wav samples.")
    ap.add_argument("manifest")
    ap.add_argument("--output-json")
    args = ap.parse_args()

    manifest_path = Path(args.manifest).resolve()
    rows = iter_manifest(manifest_path)
    results = []
    for row in rows:
        wav_path = Path(row["path"])
        if not wav_path.is_absolute():
            wav_path = (manifest_path.parent / wav_path).resolve()
        item = {
            "file": wav_path.name,
            "label": row.get("label"),
        }
        item.update(analyze_one(wav_path))
        results.append(item)

    payload = {
        "manifest": str(manifest_path),
        "results": results,
    }

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
