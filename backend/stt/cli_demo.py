import argparse
import sys
from .asr_client import ASRClient
from .audio_source import MicrophoneSource
from ..config import APP_ID, ACCESS_TOKEN

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=10.0)
    args = parser.parse_args()
    if not APP_ID or not ACCESS_TOKEN:
        print("Missing env ASR_APP_ID or ASR_ACCESS_TOKEN")
        sys.exit(1)
    client = ASRClient()
    client.connect()
    client.send_full_request()
    first = client.receive_once(timeout=2.0)
    if first is not None:
        print(first)
    def on_text(t):
        print(t)
    th = client.start_receiving(on_text)
    src = MicrophoneSource(duration_s=args.duration)
    client.stream_audio(src.stream_chunks())
    th.join(timeout=3.0)
    client.close()

if __name__ == "__main__":
    main()