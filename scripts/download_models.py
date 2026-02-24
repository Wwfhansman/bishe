#!/usr/bin/env python3
"""
模型自动下载脚本 - 智能语音厨房助手

下载项目运行所需的三个本地模型:
1. STT: sherpa-onnx streaming zipformer (中英双语)
2. TTS: piper 中文语音 (huayan)
3. Embedding: BAAI/bge-small-zh-v1.5 (RAG 向量化)

用法:
    python scripts/download_models.py          # 下载全部模型
    python scripts/download_models.py --stt     # 只下载 STT 模型
    python scripts/download_models.py --tts     # 只下载 TTS 模型
    python scripts/download_models.py --embed   # 只下载 Embedding 模型
"""

import argparse
import os
import sys
import shutil
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

# Windows 终端 UTF-8 兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── 项目根目录 ──────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "models"

# ── HuggingFace 镜像（国内加速）───────────────────────────────
HF_MIRROR = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")

# ── 模型配置 ────────────────────────────────────────────────
STT_MODEL = {
    "name": "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20",
    "repo": "csukuangfj/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20",
    "dest": MODELS_DIR / "stt" / "sherpa-onnx",
    "files": [
        "encoder-epoch-99-avg-1.onnx",
        "decoder-epoch-99-avg-1.onnx",
        "joiner-epoch-99-avg-1.onnx",
        "tokens.txt",
        "bpe.model",
    ],
}

TTS_MODEL = {
    "name": "piper-zh_CN-huayan-medium",
    "url_onnx": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/voice-zh_CN-huayan-medium.onnx",
    "url_json": "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/voice-zh_CN-huayan-medium.onnx.json",
    # 备用：从 HuggingFace 下载
    "hf_repo": "rhasspy/piper-voices",
    "hf_onnx": "zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx",
    "hf_json": "zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json",
    "dest": MODELS_DIR / "tts" / "piper-onnx",
}

EMBED_MODEL = {
    "name": "BAAI/bge-small-zh-v1.5",
    "repo": "BAAI/bge-small-zh-v1.5",
    "dest": MODELS_DIR / "bge-small-zh-v1.5",
}


# ── 工具函数 ────────────────────────────────────────────────
def _progress(block_num, block_size, total_size):
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(100, downloaded * 100 // total_size)
        mb = downloaded / 1024 / 1024
        total_mb = total_size / 1024 / 1024
        sys.stdout.write(f"\r  下载中... {mb:.1f}/{total_mb:.1f} MB ({pct}%)")
    else:
        mb = downloaded / 1024 / 1024
        sys.stdout.write(f"\r  下载中... {mb:.1f} MB")
    sys.stdout.flush()


def download_file(url: str, dest: Path):
    """下载单个文件，带进度条"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  ✓ 已存在: {dest.name}")
        return
    print(f"  → {url}")
    try:
        urlretrieve(url, str(dest), reporthook=_progress)
        print(f"\n  ✓ 完成: {dest.name}")
    except Exception as e:
        print(f"\n  ✗ 下载失败: {e}")
        raise


def hf_file_url(repo: str, filepath: str) -> str:
    """生成 HuggingFace 文件直接下载链接"""
    return f"{HF_MIRROR}/{repo}/resolve/main/{filepath}"


# ── STT 模型下载 ────────────────────────────────────────────
def download_stt():
    print("\n" + "=" * 60)
    print("📢 下载 STT 模型 (sherpa-onnx streaming zipformer)")
    print("=" * 60)

    dest = STT_MODEL["dest"]
    dest.mkdir(parents=True, exist_ok=True)

    all_exist = all((dest / f).exists() for f in STT_MODEL["files"])
    if all_exist:
        print("  ✓ STT 模型已完整，跳过下载")
        return

    repo = STT_MODEL["repo"]
    for f in STT_MODEL["files"]:
        url = hf_file_url(repo, f)
        download_file(url, dest / f)

    print("✅ STT 模型下载完成")


# ── TTS 模型下载 ────────────────────────────────────────────
def download_tts():
    print("\n" + "=" * 60)
    print("🔊 下载 TTS 模型 (piper 中文语音 huayan)")
    print("=" * 60)

    dest = TTS_MODEL["dest"]
    dest.mkdir(parents=True, exist_ok=True)
    onnx_path = dest / "voice.onnx"
    json_path = dest / "voice.onnx.json"

    if onnx_path.exists() and json_path.exists():
        print("  ✓ TTS 模型已完整，跳过下载")
        return

    # 优先从 GitHub 下载
    try:
        if not onnx_path.exists():
            download_file(TTS_MODEL["url_onnx"], onnx_path)
        if not json_path.exists():
            download_file(TTS_MODEL["url_json"], json_path)
    except Exception:
        print("  ⚠ GitHub 下载失败，尝试从 HuggingFace 镜像下载...")
        repo = TTS_MODEL["hf_repo"]
        if not onnx_path.exists():
            download_file(hf_file_url(repo, TTS_MODEL["hf_onnx"]), onnx_path)
        if not json_path.exists():
            download_file(hf_file_url(repo, TTS_MODEL["hf_json"]), json_path)

    print("✅ TTS 模型下载完成")


# ── Embedding 模型下载 ──────────────────────────────────────
def download_embed():
    print("\n" + "=" * 60)
    print("🧠 下载 Embedding 模型 (bge-small-zh-v1.5)")
    print("=" * 60)

    dest = EMBED_MODEL["dest"]

    # 检查是否已存在关键文件
    if (dest / "model.safetensors").exists() or (dest / "pytorch_model.bin").exists():
        print("  ✓ Embedding 模型已完整，跳过下载")
        return

    # 使用 huggingface_hub 下载整个 repo
    try:
        from huggingface_hub import snapshot_download
        print(f"  使用 huggingface_hub 下载到 {dest}")
        snapshot_download(
            repo_id=EMBED_MODEL["repo"],
            local_dir=str(dest),
            local_dir_use_symlinks=False,
        )
        print("✅ Embedding 模型下载完成")
    except ImportError:
        # 回退：手动下载关键文件
        print("  ⚠ 未安装 huggingface_hub，手动下载关键文件...")
        dest.mkdir(parents=True, exist_ok=True)
        repo = EMBED_MODEL["repo"]
        key_files = [
            "config.json",
            "model.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.txt",
            "sentence_bert_config.json",
            "config_sentence_transformers.json",
            "modules.json",
            "1_Pooling/config.json",
        ]
        for f in key_files:
            fpath = dest / f
            fpath.parent.mkdir(parents=True, exist_ok=True)
            url = hf_file_url(repo, f)
            download_file(url, fpath)
        print("✅ Embedding 模型下载完成")


# ── 主函数 ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="下载智能语音厨房助手所需的本地模型",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/download_models.py          # 下载全部
  python scripts/download_models.py --stt     # 只下 STT
  python scripts/download_models.py --embed   # 只下 Embedding
  
设置 HuggingFace 镜像 (国内加速):
  set HF_ENDPOINT=https://hf-mirror.com      # Windows
  export HF_ENDPOINT=https://hf-mirror.com   # Linux/Mac
""",
    )
    parser.add_argument("--stt", action="store_true", help="只下载 STT 模型")
    parser.add_argument("--tts", action="store_true", help="只下载 TTS 模型")
    parser.add_argument("--embed", action="store_true", help="只下载 Embedding 模型")
    args = parser.parse_args()

    download_all = not (args.stt or args.tts or args.embed)

    print("🍳 智能语音厨房助手 — 模型下载工具")
    print(f"   模型目录: {MODELS_DIR}")
    print(f"   HF 镜像:  {HF_MIRROR}")

    if download_all or args.stt:
        download_stt()
    if download_all or args.tts:
        download_tts()
    if download_all or args.embed:
        download_embed()

    print("\n" + "=" * 60)
    print("🎉 模型下载完成！现在可以启动服务了：")
    print("   uvicorn backend.api.server:app --reload")
    print("=" * 60)


if __name__ == "__main__":
    main()
