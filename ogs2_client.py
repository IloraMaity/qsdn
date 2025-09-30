
import socket

LISTEN_PORT = 6000

if __name__ == '__main__':
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('0.0.0.0', LISTEN_PORT))
    print(f"[OGS2] Waiting for key on UDP:{LISTEN_PORT} ...")
    try:
        data, addr = s.recvfrom(65535)
        print(f"[OGS2] Packet received from {addr}")
        msg = data.decode('utf-8').strip()
        print(f"[OGS2] Raw message: {msg}")
        if msg.startswith('KEY:'):
            bits = msg.split(':', 1)[1]
            print(f"[OGS2] Received key ({len(bits)} bits)")
        else:
            print(f"[OGS2] Unexpected: {msg}")
    except Exception as e:
        print(f"[OGS2] Error: {e}")
    finally:
        s.close()
