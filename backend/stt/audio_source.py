import queue
import numpy as np
import sounddevice as sd
from ..config import RATE, CHANNELS, INPUT_DEVICE, CHUNK_MS

class MicrophoneSource:
    def __init__(self, chunk_ms=None, duration_s=None):
        self.chunk_ms = chunk_ms or CHUNK_MS
        self.duration_s = duration_s
        self.stopped = False

    def stop(self):
        self.stopped = True

    def stream_chunks(self):
        q = queue.Queue()
        frames_per_chunk = int(RATE * self.chunk_ms / 1000)
        def cb(indata, frames, time, status):
            try:
                q.put_nowait(indata.copy())
            except Exception:
                pass
        with sd.InputStream(device=INPUT_DEVICE, samplerate=RATE, channels=CHANNELS, dtype="int16", blocksize=frames_per_chunk, callback=cb):
            elapsed = 0.0
            while not self.stopped:
                arr = q.get()
                b = arr.astype(np.int16).tobytes()
                yield b
                if self.duration_s is not None:
                    elapsed += self.chunk_ms / 1000.0
                    if elapsed >= self.duration_s:
                        self.stopped = True