from .asr_client import ASRClient

def run():
    c = ASRClient()
    h1 = c._build_header(msg_type=1, flags=0, serialization=1, compression=0)
    h2 = c._build_header(header_size_units=2, msg_type=2, flags=1, serialization=0, compression=0)
    print(h1.hex())
    print(h2.hex())

if __name__ == "__main__":
    run()