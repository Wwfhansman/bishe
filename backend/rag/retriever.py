import os
import json
from pathlib import Path

try:
    from ..config import RAG_DB_PATH, RAG_COLLECTION, HF_ENDPOINT, EMBED_LOCAL_DIR
except Exception:
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import RAG_DB_PATH, RAG_COLLECTION, HF_ENDPOINT, EMBED_LOCAL_DIR

def _set_hf_endpoint():
    if HF_ENDPOINT and os.environ.get("HF_ENDPOINT") != HF_ENDPOINT:
        os.environ["HF_ENDPOINT"] = HF_ENDPOINT
    if os.environ.get("TRANSFORMERS_NO_TF") != "1":
        os.environ["TRANSFORMERS_NO_TF"] = "1"
    if os.environ.get("TRANSFORMERS_NO_FLAX") != "1":
        os.environ["TRANSFORMERS_NO_FLAX"] = "1"
    if os.environ.get("USE_TF") not in ("0", "NO", "False"):
        os.environ["USE_TF"] = "NO"
    if os.environ.get("USE_FLAX") not in ("0", "NO", "False"):
        os.environ["USE_FLAX"] = "NO"

def _embed_texts(texts):
    from sentence_transformers import SentenceTransformer
    _set_hf_endpoint()
    local_dir = EMBED_LOCAL_DIR
    if local_dir and Path(local_dir).exists():
        m = SentenceTransformer(local_dir)
    else:
        m = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    embs = m.encode(texts, normalize_embeddings=True)
    return [list(map(float, e)) for e in embs]

def _get_collection():
    import chromadb
    client = chromadb.PersistentClient(path=RAG_DB_PATH)
    coll = client.get_or_create_collection(name=RAG_COLLECTION, metadata={"hnsw:space": "cosine"})
    return coll

def search(q: str, top_k: int = 5):
    coll = _get_collection()
    emb = _embed_texts([q])[0]
    res = coll.query(query_embeddings=[emb], n_results=int(top_k), include=["documents", "metadatas", "distances"])
    return res

def best_text(q: str, top_k: int = 5, max_chars: int = 1200):
    r = search(q, top_k)
    docs = r.get("documents") or [[]]
    buf = []
    total = 0
    for d in docs[0]:
        if not isinstance(d, str):
            continue
        if total + len(d) + 1 > max_chars:
            break
        buf.append(d)
        total += len(d) + 1
    return "\n".join(buf)

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("q")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--mode", default="json")
    args = ap.parse_args()
    if args.mode == "text":
        print(best_text(args.q, args.k))
        return
    r = search(args.q, args.k)
    print(json.dumps(r, ensure_ascii=False))

if __name__ == "__main__":
    main()
