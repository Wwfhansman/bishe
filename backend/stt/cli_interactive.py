import sys
import threading
import time
try:
    import msvcrt
except Exception:
    msvcrt = None
from .asr_client import ASRClient
from .audio_source import MicrophoneSource
from ..config import APP_ID, ACCESS_TOKEN

def main():
    if not APP_ID or not ACCESS_TOKEN:
        print("Missing env ASR_APP_ID or ASR_ACCESS_TOKEN")
        sys.exit(1)
    client = None
    th_recv = None
    src = None
    th_stream = None
    print("按 S 开始识别，按 E 结束识别，按 Q 退出")
    try:
        while True:
            key = None
            if msvcrt is not None and msvcrt.kbhit():
                key = msvcrt.getwch().lower()
            else:
                time.sleep(0.1)
                continue
            if key == "s":
                if th_stream is None or not th_stream.is_alive():
                    if client is not None:
                        try:
                            client.close()
                        except Exception:
                            pass
                    client = ASRClient()
                    client.connect()
                    client.send_full_request()
                    th_recv = client.start_receiving(lambda t: print(t))
                    src = MicrophoneSource()
                    th_stream = threading.Thread(target=lambda: client.stream_audio(src.stream_chunks()), daemon=True)
                    th_stream.start()
                    print("开始识别")
            elif key == "e":
                if src is not None:
                    src.stop()
                    if th_stream is not None:
                        th_stream.join(timeout=2.0)
                    if th_recv is not None:
                        th_recv.join(timeout=2.0)
                    if client is not None:
                        try:
                            client.close()
                        except Exception:
                            pass
                        client = None
                    print("结束识别")
            elif key == "q":
                break
    except KeyboardInterrupt:
        pass
    if src is not None:
        src.stop()
    if th_stream is not None:
        th_stream.join(timeout=2.0)
    if th_recv is not None:
        th_recv.join(timeout=2.0)
    if client is not None:
        client.close()

if __name__ == "__main__":
    main()