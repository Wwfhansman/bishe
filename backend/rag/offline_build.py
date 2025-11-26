import os
import re
import glob
import uuid
import json
from pathlib import Path
try:
    from ..config import RAG_DB_PATH, RAG_COLLECTION, HF_ENDPOINT
except Exception:
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import RAG_DB_PATH, RAG_COLLECTION, HF_ENDPOINT

def _set_hf_endpoint():
    if HF_ENDPOINT and os.environ.get("HF_ENDPOINT") != HF_ENDPOINT:
        os.environ["HF_ENDPOINT"] = HF_ENDPOINT

def _read_text(p):
    try:
        return Path(p).read_text(encoding="utf-8").strip()
    except Exception:
        try:
            return Path(p).read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return ""

def _infer_tags(fn):
    name = Path(fn).name
    base = Path(fn).stem
    t = []
    if base.startswith("技法_"):
        t.append("technique:" + base.split("技法_", 1)[1])
    elif base.startswith("食材_"):
        t.append("ingredient:" + base.split("食材_", 1)[1])
    elif base.startswith("菜单_"):
        t.append("scene:" + base.split("菜单_", 1)[1])
    else:
        t.append("cuisine:" + base)
    return t

def _title(text):
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s[:60]
    return ""

def _chunk_text(text, min_size=512, max_size=1024):
    parts = re.split(r"\n\s*\n+", text)
    chunks = []
    buf = ""
    for p in parts:
        if not p.strip():
            continue
        if len(p) >= max_size:
            s = 0
            while s < len(p):
                e = min(s + max_size, len(p))
                chunks.append(p[s:e])
                s = e
            continue
        if len(buf) + len(p) + 1 <= max_size:
            buf = (buf + "\n" + p) if buf else p
            if len(buf) >= min_size:
                chunks.append(buf)
                buf = ""
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks

def _collect_docs(root):
    paths = sorted(glob.glob(str(Path(root) / "*.txt")))
    items = []
    for p in paths:
        text = _read_text(p)
        if not text:
            continue
        chs = _chunk_text(text)
        ts = _infer_tags(p)
        ti = _title(text)
        tag_str = ",".join(ts)
        for i, c in enumerate(chs):
            items.append({
                "id": uuid.uuid4().hex,
                "document": c,
                "metadata": {"source": str(Path(p)), "title": ti, "tags": tag_str, "index": i}
            })
    return items

def _embed_fastembed(chunks):
    from fastembed import TextEmbedding
    _set_hf_endpoint()
    m = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5")
    embs = list(m.embed(chunks))
    return [list(map(float, e)) for e in embs]

def _embed_sbert(chunks):
    _set_hf_endpoint()
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    embs = m.encode(chunks, normalize_embeddings=True)
    return [list(map(float, e)) for e in embs]

def _write_chroma(items):
    import chromadb
    client = chromadb.PersistentClient(path=RAG_DB_PATH)
    coll = client.get_or_create_collection(name=RAG_COLLECTION, metadata={"hnsw:space": "cosine"})
    docs = [it["document"] for it in items]
    ids = [it["id"] for it in items]
    metas = [it["metadata"] for it in items]
    try:
        embs = _embed_fastembed(docs)
    except Exception:
        embs = _embed_sbert(docs)
    coll.add(documents=docs, ids=ids, metadatas=metas, embeddings=embs)
    return {"count": len(ids), "path": RAG_DB_PATH, "collection": RAG_COLLECTION}

def build(root="data/raw"):
    items = _collect_docs(root)
    info = _write_chroma(items)
    return info

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/raw")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if args.dry_run:
        items = _collect_docs(args.root)
        if args.limit and args.limit > 0:
            items = items[:args.limit]
        print(json.dumps({"items": len(items), "sample": items[:1]}, ensure_ascii=False))
        return
    info = build(args.root)
    print(json.dumps(info, ensure_ascii=False))

if __name__ == "__main__":
    main()
