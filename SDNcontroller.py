# controller_fixed.py
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet
from ryu.topology import event
import networkx as nx
import socket
import threading
import re
import time

QKD_LISTEN_HOST = '127.0.0.1'
QKD_LISTEN_PORT = 7001
QKD_ETHER_TYPE = 0x88B5

class SatelliteController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SatelliteController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.net = nx.DiGraph()
        self.switches = {}
        # qkd_keys will hold {'packed': <str or None>, 'bits': <'0101...' or None>, 'n_bits': <int or None>}
        self.qkd_keys = {}

        # Start key listener thread
        key_listener_thread = threading.Thread(target=self._key_listener_worker, daemon=True)
        key_listener_thread.start()

    # ---------- Helper: convert packed string to bitstring ----------
    def _packed_to_bitstring(self, packed: str) -> str:
        """Convert packed string (bytes/chars where each char contains 8 bits) to bitstring '0101...'."""
        return ''.join(f'{ord(c):08b}' for c in packed)

    def _parse_incoming_key_payload(self, data: str):
        """
        Handle incoming TCP payloads. Accepts:
         - KEY:<bitstring>
         - KEY:<packed_string>   (packed chars)
         - KEYLEN:<n>:<data>     (data either packed or bits)
        Returns tuple (packed_or_raw, bits_string, n_bits_or_none)
        """
        # Normalize
        data = data.strip()
        # KEYLEN:<n>:<data>
        if data.startswith('KEYLEN:'):
            parts = data.split(':', 2)
            if len(parts) == 3:
                try:
                    n_bits = int(parts[1])
                except ValueError:
                    n_bits = None
                payload = parts[2]
                # If payload looks like only 0/1 then treat as bitstring
                if re.fullmatch(r'[01]+', payload):
                    bits = payload
                    packed = None
                else:
                    packed = payload
                    bits = self._packed_to_bitstring(packed)
                # Trim to n_bits if given
                if n_bits is not None:
                    bits = bits[:n_bits]
                return packed, bits, n_bits
        # KEY:<data>
        if data.startswith('KEY:'):
            payload = data.split(':', 1)[1]
            # If payload looks like bits only -> it's already a bitstring
            if re.fullmatch(r'[01]+', payload):
                return None, payload, len(payload)
            else:
                # packed chars -> convert
                packed = payload
                bits = self._packed_to_bitstring(packed)
                return packed, bits, len(bits)
        # Unknown format
        return None, None, None

    # ---------- TCP listener for pushed QKD keys ----------
    def _key_listener_worker(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((QKD_LISTEN_HOST, QKD_LISTEN_PORT))
        s.listen(5)
        self.logger.info("SDN Controller listening for QKD keys on %s:%s", QKD_LISTEN_HOST, QKD_LISTEN_PORT)
        while True:
            conn, addr = s.accept()
            # handle each connection in worker thread to avoid blocking listener
            threading.Thread(target=self._handle_qkd_key_push, args=(conn,), daemon=True).start()

    def _handle_qkd_key_push(self, conn):
        """Handles an incoming key and sends an acknowledgment including parsed bit length."""
        try:
            data = conn.recv(65535).decode('utf-8', errors='ignore').strip()
            packed, bits, n_bits = self._parse_incoming_key_payload(data)
            if bits is not None:
                # store both representations
                self.qkd_keys['packed'] = packed
                self.qkd_keys['bits'] = bits
                self.qkd_keys['n_bits'] = n_bits if n_bits is not None else len(bits)
                nbits_val = self.qkd_keys['n_bits']
                self.logger.info("Received QKD key: stored %d bits (packed len=%s)", nbits_val, None if packed is None else len(packed))
                # ACK with explicit bit length so client can confirm
                ack = f"ACK:OK:bits={nbits_val}".encode('utf-8')
                conn.sendall(ack)
            else:
                self.logger.warning("Rejected QKD push (bad format): %s", data[:120])
                conn.sendall(b"ERR:BAD_FORMAT")
        except Exception as e:
            self.logger.exception("Failed to handle QKD key push: %s", e)
            try:
                conn.sendall(b"ERR:EXCEPTION")
            except Exception:
                pass
        finally:
            conn.close()

    # ---------- Ryu lifecycle / flow helpers ----------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        self.switches[datapath.id] = datapath
        self.net.add_node(datapath.id)
        self.logger.info("Switch %s connected", datapath.id)

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        src = ev.link.src
        dst = ev.link.dst
        self.net.add_edge(src.dpid, dst.dpid, port=src.port_no)
        self.net.add_edge(dst.dpid, src.dpid, port=dst.port_no)
        self.logger.info("Link added: %s <-> %s", src.dpid, dst.dpid)

    @set_ev_cls(event.EventLinkDelete)
    def link_del_handler(self, ev):
        src = ev.link.src
        dst = ev.link.dst
        if self.net.has_edge(src.dpid, dst.dpid):
            self.net.remove_edge(src.dpid, dst.dpid)
        if self.net.has_edge(dst.dpid, src.dpid):
            self.net.remove_edge(dst.dpid, src.dpid)
        self.logger.info("Link removed: %s <-> %s", src.dpid, dst.dpid)

    # ---------- Packet-in handler (handles REQ_KEY via ethertype) ----------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Try to decode textual payload safely
        try:
            payload = msg.data[14:].decode('utf-8', errors='ignore').strip()
        except Exception:
            payload = None

        # safeguard: drop reflected KEY payloads to avoid loops
        if payload:
            if payload.startswith('KEY:') or payload.startswith('KEYLEN:'):
                self.logger.debug("Dropping potential reflected/looped QKD payload: %s", payload[:120])
                return
                # don't return here; we still want to handle ethertype packets further down if needed
                # but if ethertype is QKD_ETHER_TYPE we will handle below.

        # Handle QKD control EtherType packets
        if eth.ethertype == QKD_ETHER_TYPE:
            try:
                payload = msg.data[14:].decode('utf-8', errors='ignore').strip()
                parts = payload.split(':')
                if len(parts) >= 1 and parts[0] == 'REQ_KEY':
                    self.logger.info("Received QKD REQ_KEY on dpid=%s port=%s from %s", dpid, in_port, eth.src)
                    if 'bits' in self.qkd_keys and self.qkd_keys['bits']:
                        bits = self.qkd_keys['bits']
                        reply = f"KEY:{bits}".encode('utf-8')
                        self.logger.info("Serving QKD key (%d bits) to requester (dpid=%s).", len(bits), dpid)
                    else:
                        reply = b"ERR:NO_KEY_AVAILABLE"
                        self.logger.warning("No QKD key available to serve request.")
                    # Flood the reply so it reaches the host
                    actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
                    out = parser.OFPPacketOut(
                        datapath=datapath,
                        buffer_id=ofproto.OFP_NO_BUFFER,
                        in_port=ofproto.OFPP_CONTROLLER,
                        actions=actions,
                        data=self._craft_eth(eth.src, eth.dst, QKD_ETHER_TYPE, reply)
                    )
                    time.sleep(0.5)
                    datapath.send_msg(out)
                else:
                    self.logger.warning("Bad QKD payload or unexpected format: %s", payload)
            except Exception as e:
                self.logger.exception("QKD handling failed: %s", e)
            return

        # ---------------- Standard forwarding (ARP/IP) ----------------
        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        # ARP handling
        if eth.ethertype == 0x0806:
            self.logger.debug("ARP packet on dpid=%s, port=%s", dpid, in_port)
            out_port = ofproto.OFPP_FLOOD
            actions = [parser.OFPActionOutput(out_port)]
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=msg.data)
            datapath.send_msg(out)
            return

        # IPv4 handling
        if eth.ethertype == 0x0800:
            out_port = None
            if dst in self.mac_to_port.get(dpid, {}):
                out_port = self.mac_to_port[dpid][dst]
            else:
                out_port = ofproto.OFPP_FLOOD
            actions = [parser.OFPActionOutput(out_port)]
            match = parser.OFPMatch(eth_dst=dst)
            self.add_flow(datapath, 1, match, actions)
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=msg.data)
            datapath.send_msg(out)
            return

    def _craft_eth(self, dst_mac: str, src_mac: str, eth_type: int, payload: bytes) -> bytes:
        def mac_to_bytes(mac: str) -> bytes:
            return bytes(int(x, 16) for x in mac.split(':'))
        eth_hdr = mac_to_bytes(dst_mac) + mac_to_bytes(src_mac) + eth_type.to_bytes(2, 'big')
        return eth_hdr + payload
