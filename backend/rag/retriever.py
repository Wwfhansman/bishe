import os
import json
from pathlib import Path

try:
    from ..config import RAG_DB_PATH, RAG_COLLECTION, HF_ENDPOINT, EMBED_LOCAL_DIR, RAG_MAX_DISTANCE
except Exception:
    import sys
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from config import RAG_DB_PATH, RAG_COLLECTION, HF_ENDPOINT, EMBED_LOCAL_DIR, RAG_MAX_DISTANCE


_embed_model = None
_collection = None

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
    global _embed_model
    from sentence_transformers import SentenceTransformer
    _set_hf_endpoint()
    if _embed_model is None:
        local_dir = EMBED_LOCAL_DIR
        if local_dir and Path(local_dir).exists():
            _embed_model = SentenceTransformer(local_dir, device="cpu")
        else:
            _embed_model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")
    embs = _embed_model.encode(texts, normalize_embeddings=True)
    return [list(map(float, e)) for e in embs]

def _get_collection():
    global _collection
    import chromadb
    if _collection is None:
        client = chromadb.PersistentClient(path=RAG_DB_PATH)
        _collection = client.get_or_create_collection(name=RAG_COLLECTION, metadata={"hnsw:space": "cosine"})
    return _collection

def search(q: str, top_k: int = 5):
    coll = _get_collection()
    emb = _embed_texts([q])[0]
    res = coll.query(query_embeddings=[emb], n_results=int(top_k), include=["documents", "metadatas", "distances"])
    return res

def best_text(q: str, top_k: int = 5, max_chars: int = 1200):
    r = search(q, top_k)
    docs = r.get("documents") or [[]]
    distances = r.get("distances") or [[]]
    buf = []
    total = 0
    for idx, d in enumerate(docs[0]):
        if not isinstance(d, str):
            continue
        distance = None
        if distances and distances[0] and idx < len(distances[0]):
            distance = distances[0][idx]
        if isinstance(distance, (int, float)) and distance > RAG_MAX_DISTANCE:
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
