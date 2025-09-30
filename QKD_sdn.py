import numpy as np
import random
import time
import socket
import threading
from qunetsim.components import Host, Network
from qunetsim.objects import Qubit, Logger

Logger.DISABLED = True
wait_time = 2

# ... (Encryption/Decryption functions - unchanged)
def encrypt(key, text):
    return ''.join([chr(ord(k) ^ ord(c)) for k, c in zip(key, text)])

def decrypt(key, encrypted_text):
    return encrypt(key, encrypted_text)

def key_array_to_key_string(key_array):
    key_string_binary = ''.join(str(x) for x in key_array)
    padding_needed = 8 - (len(key_string_binary) % 8)
    if padding_needed != 8:
        key_string_binary += '0' * padding_needed
    return ''.join(chr(int(key_string_binary[i:i+8], 2)) for i in range(0, len(key_string_binary), 8))

def key_array_to_key_string_full(key_array, length):
    key_chars = key_array_to_key_string(key_array)
    repeat_count = (length // len(key_chars)) + 1
    return (key_chars * repeat_count)[:length]

def key_string_to_bitstring(key_string):
    return ''.join(f'{ord(c):08b}' for c in key_string)

# ... (QKD Functions - unchanged)
def alice_qkd(alice, secret_key, receiver):
    sequence_nr = 0
    bits_sent = 0
    sifted_key = []
    for bit in secret_key:
        ack = False
        base = random.randint(0, 1)
        while not ack:
            q_bit = Qubit(alice)
            if bit == 1:
                q_bit.X()
            if base == 1:
                q_bit.H()
            alice.send_qubit(receiver, q_bit, await_ack=False)
            messages = alice.get_classical(receiver, wait=wait_time)
            if isinstance(messages, list) and messages:
                message = messages[0]
            elif messages:
                message = messages
            else:
                message = None
            if message is not None:
                msg_parts = message.content.split(':')
                if len(msg_parts) == 2 and msg_parts[0] == str(sequence_nr) and msg_parts[1] == str(base):
                    ack = True
                    alice.send_classical(receiver, f"{sequence_nr}:0:{bit}", await_ack=False)
                    bits_sent += 1
                    sifted_key.append(bit)
                    print(f"Alice sent {bits_sent} key bits successfully")
                    sequence_nr += 1
                else:
                    alice.send_classical(receiver, f"{sequence_nr}:1", await_ack=False)
            time.sleep(0.05)
    return sifted_key

def eve_qkd(eve, key_size, sender):
    sequence_nr = 0
    kept_counter = 0
    key_array = []
    while kept_counter < key_size:
        while True:
            measurement_base = random.randint(0, 1)
            q_bit = eve.get_qubit(sender, wait=wait_time)
            while q_bit is None:
                q_bit = eve.get_qubit(sender, wait=wait_time)
            if measurement_base == 1:
                q_bit.H()
            bit = q_bit.measure()
            eve.send_classical(sender, f"{sequence_nr}:{measurement_base}", await_ack=False)
            confirm_msg = eve.get_classical(sender, wait=wait_time)
            if isinstance(confirm_msg, list) and confirm_msg:
                confirm_msg = confirm_msg[0]
            elif confirm_msg:
                confirm_msg = confirm_msg
            else:
                confirm_msg = None
            if confirm_msg is not None:
                parts = confirm_msg.content.split(':')
                if (len(parts) == 3 and parts[0] == str(sequence_nr)) or (len(parts) == 2 and parts[0] == str(sequence_nr)):
                    if parts[1] == '0':
                        kept_bit = int(parts[2]) if len(parts) == 3 else bit
                        key_array.append(kept_bit)
                        kept_counter += 1
                        print(f"Eve kept bit {bit} for seq {sequence_nr} (base matched)")
                        sequence_nr += 1
                        break
                    else:
                        print(f"Eve discarded bit for seq {sequence_nr} (base mismatch)")
                else:
                    print("Eve received out-of-sync confirmation; ignoring")
            else:
                print(f"Eve discarded bit for seq {sequence_nr} (no confirmation)")
            time.sleep(0.05)
    return key_array

def eve_receive_message(eve, eve_key, sender):
    payload = None
    while payload is None:
        msg = eve.get_classical(sender, wait=wait_time)
        if isinstance(msg, list) and msg:
            msg = msg[0]
        elif not msg:
            msg = None
        if msg is not None and isinstance(msg.content, str) and msg.content.startswith('-1:'):
            payload = msg.content.split(':', 1)[1]
    secret_key_string = key_array_to_key_string_full(eve_key, len(payload))
    decrypted_msg_from_alice = decrypt(secret_key_string, payload)
    print("Eve received decoded message: %s" % decrypted_msg_from_alice)

def alice_send_message(alice, secret_key, receiver):
    msg_to_eve = "Hi Eve, how are you???"
    secret_key_string = key_array_to_key_string_full(secret_key, len(msg_to_eve))
    encrypted_msg_to_eve = encrypt(secret_key_string, msg_to_eve)
    print("Alice sends encrypted message")
    alice.send_classical(receiver, "-1:" + encrypted_msg_to_eve, await_ack=False)


def _send_key_to_controller(key: str):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10.0)
    try:
        s.connect(('127.0.0.1', 7001))
        s.sendall(f"KEY:{key}".encode('utf-8'))
        resp = s.recv(1024).decode('utf-8').strip()
        print(f"Received acknowledgment from SDN Controller: {resp}")
    except Exception as e:
        print(f"Failed to push key to SDN Controller: {e}")
    finally:
        s.close()

def main():
    network = Network.get_instance()
    nodes = ['Alice', 'Bob', 'Eve', 'SDN_Controller']
    network.delay = 0.0
    network.start(nodes)

    host_alice = Host('Alice')
    host_alice.add_connection('Bob')
    host_alice.start()

    host_bob = Host('Bob')
    host_bob.add_connection('Alice')
    host_bob.add_connection('Eve')
    host_bob.start()

    host_eve = Host('Eve')
    host_eve.add_connection('Bob')
    host_eve.start()

    host_controller = Host('SDN_Controller')
    host_controller.add_connection('Alice')
    host_controller.start()

    network.add_host(host_alice)
    network.add_host(host_bob)
    network.add_host(host_eve)
    network.add_host(host_controller)

    key_size = 16
    secret_key = np.random.randint(2, size=key_size)
    key_string = key_array_to_key_string(np.random.randint(2, size=key_size))

    def alice_func(alice):
        sifted_key = alice_qkd(alice, secret_key, host_eve.host_id)
        key_string = key_array_to_key_string(sifted_key)
        print(f"Alice sifted key: {sifted_key}")
        _send_key_to_controller(key_string)
        alice_send_message(alice, sifted_key, host_eve.host_id)

    def eve_func(eve):
        eve_key = eve_qkd(eve, key_size, host_alice.host_id)
        print(f"Eve sifted key:   {eve_key}")
        eve_receive_message(eve, eve_key, host_alice.host_id)

    
    
    t1 = host_alice.run_protocol(alice_func, ())
    t2 = host_eve.run_protocol(eve_func, ())

    t1.join()
    t2.join()
    
    # Clean shutdown
    host_alice.stop()
    host_bob.stop()
    host_eve.stop()
    host_controller.stop()
    network.stop(True)

if __name__ == '__main__':
    main()