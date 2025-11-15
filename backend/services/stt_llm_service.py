import sys
import threading
import queue
import time
from ..stt.asr_client import ASRClient
from ..stt.audio_source import MicrophoneSource
from ..llm.llm_client import LLMClient
from ..config import APP_ID, ACCESS_TOKEN, ARK_API_KEY, ARK_MODEL_ID

def main():
    if not APP_ID or not ACCESS_TOKEN:
        print("Missing ASR_APP_ID or ASR_ACCESS_TOKEN")
        sys.exit(1)
    if not ARK_API_KEY or not ARK_MODEL_ID:
        print("Missing ARK_API_KEY or ARK_MODEL_ID")
        sys.exit(1)
    print("Listening... Press Ctrl+C to stop")
    client = ASRClient()
    client.connect()
    client.send_full_request()
    out_q = queue.Queue()
    seen = set()
    def on_obj(obj):
        res = obj.get("result")
        if isinstance(res, dict):
            uts = res.get("utterances")
            if isinstance(uts, list) and len(uts) > 0:
                for u in reversed(uts):
                    if not isinstance(u, dict):
                        continue
                    t = u.get("text")
                    d = u.get("definite")
                    if isinstance(t, str) and t.strip() and d is True:
                        k = (t, u.get("end_time"), u.get("start_time"))
                        if k not in seen:
                            seen.add(k)
                            out_q.put(t)
                            break
            else:
                t = res.get("text")
                if isinstance(t, str) and t.strip():
                    k = (t,)
                    if k not in seen:
                        seen.add(k)
                        out_q.put(t)
    th_recv = client.start_receiving_objects(on_obj)
    src = MicrophoneSource(duration_s=None)
    th_stream = threading.Thread(target=lambda: client.stream_audio(src.stream_chunks()), daemon=True)
    th_stream.start()
    llm = LLMClient()
    running = True
    def consume():
        while running:
            try:
                t = out_q.get(timeout=0.5)
            except Exception:
                continue
            try:
                r = llm.chat(t)
            except Exception as e:
                r = str(e)
            print(r)
    th_consume = threading.Thread(target=consume, daemon=True)
    th_consume.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    running = False
    src.stop()
    th_stream.join(timeout=2.0)
    th_recv.join(timeout=2.0)
    th_consume.join(timeout=2.0)
    client.close()

if __name__ == "__main__":
    main()