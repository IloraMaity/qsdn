
import socket
import struct
import sys
import time
import select

QKD_ETHER_TYPE = 0x88B5
UDP_PORT_OGS2 = 6000
ETH_P_ALL = 0x0003
ETH_HDR_LEN = 14

def mac_to_bytes(mac_str: str) -> bytes:
    return bytes(int(x, 16) for x in mac_str.split(':'))

def craft_eth_frame(dst_mac_bytes: bytes, src_mac_bytes: bytes, eth_type: int, payload: bytes) -> bytes:
    eth_header = dst_mac_bytes + src_mac_bytes + eth_type.to_bytes(2, 'big')
    return eth_header + payload

def send_req(iface: str, requester: str, peer: str, size: int):
    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
        s.bind((iface, 0))
        payload = f"REQ_KEY:{requester}:{peer}:{size}".encode('utf-8')
        src_mac_bytes = s.getsockname()[4]
        dst_mac_bytes = mac_to_bytes("ff:ff:ff:ff:ff:ff")
        frame = craft_eth_frame(dst_mac_bytes, src_mac_bytes, QKD_ETHER_TYPE, payload)
        print(f"[OGS1] Sending key request from {':'.join(f'{b:02x}' for b in src_mac_bytes)}...")
        s.send(frame)
        s.close()
    except socket.error as e:
        print(f"[OGS1] Failed to send packet: {e}")
        sys.exit(1)




def wait_key(iface: str):
    s = None
    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
        s.bind((iface, 0))
        print("[OGS1] Waiting for reply on interface:", iface)
        start_time = time.time()
        while time.time() - start_time < 20.0:
            ready_to_read, _, _ = select.select([s], [], [], 1.0)
            if not ready_to_read:
                continue
            raw_packet = s.recv(2048)
            eth_header = raw_packet[:ETH_HDR_LEN]
            dst_mac_bytes, src_mac_bytes, eth_type_bytes = struct.unpack('!6s6sH', eth_header)
            print(f"[OGS1] Packet received: EtherType={hex(eth_type_bytes)} From={':'.join(f'{b:02x}' for b in src_mac_bytes)}")
            if eth_type_bytes == QKD_ETHER_TYPE:
                try:
                    payload = raw_packet[ETH_HDR_LEN:].decode('utf-8', errors='ignore').strip()
                    print(f"[OGS1] Decoded payload: {payload}")
                    return payload
                except Exception as e:
                    print(f"[OGS1] Failed to decode payload: {e}")
        print("[OGS1] Timed out waiting for QKD reply.")
    except Exception as e:
        print(f"[OGS1] Error receiving packet: {e}")
    finally:
        if s:
            s.close()
    return ""




def forward_to_ogs2(ogs2_ip: str, key_bits: str):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(f"KEY:{key_bits}".encode('utf-8'), (ogs2_ip, UDP_PORT_OGS2))
    s.close()

if __name__ == '__main__':
    if len(sys.argv) != 6:
        print("usage: python3 ogs1_client.py <iface> <OGS2_IP> <REQ_NAME> <PEER_NAME> <SIZE>")
        sys.exit(1)

    iface, ogs2_ip, req_name, peer_name, size = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])

    temp_sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    temp_sock.bind((iface, 0))
    my_mac_bytes = temp_sock.getsockname()[4]
    temp_sock.close()

    print(f"[OGS1] My MAC is {':'.join(f'{b:02x}' for b in my_mac_bytes)}. Requesting key from controller...")
    send_req(iface, req_name, peer_name, size)

    resp = wait_key(iface)

    if not resp.startswith('KEY:'):
        print(f"[OGS1] Bad reply from controller: {resp}")
        sys.exit(2)

    bits = resp.split(':', 1)[1]
    print(f"[OGS1] Got key ({len(bits)} bits) from controller.")
    forward_to_ogs2(ogs2_ip, bits)
    print("[OGS1] Forwarded key to OGS2 (UDP:6000).")
