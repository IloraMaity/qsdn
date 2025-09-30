#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import threading
import pandas as pd
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import Link
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.node import Node

# --- Simulation Parameters ---
SIM_START_TIME_SEC = 0
TIME_SCALE_FACTOR = 60 #1 sec of simulation time equal to 60 sec of real time

class LinuxRouter(Node):
    """A Node with IP forwarding enabled."""
    def config(self, **params):
        super(LinuxRouter, self).config(**params)
        self.cmd('sysctl net.ipv4.ip_forward=1')

    def terminate(self):
        self.cmd('sysctl net.ipv4.ip_forward=0')
        super(LinuxRouter, self).terminate()

class SatelliteNetwork:
    """
    Manages the dynamic satellite network topology in Mininet.
    """
    def __init__(self):
        self.nodes_df = pd.read_csv('mininet_nodes.csv')
        self.intervals_df = pd.read_csv('mininet_access_intervals.csv')
        self.intervals_df.columns = self.intervals_df.columns.str.strip()

        self.net = Mininet(controller=None, switch=OVSKernelSwitch, build=False, link=Link) 
        
        self.net.addController('c0',
                               controller=RemoteController,
                               ip='127.0.0.1', # Ryu VM's IP
                               port=6633)
        
        self.switches = {}
        self.name_map = {}
        self.active_links = set()
        self.current_sim_time = SIM_START_TIME_SEC
        self.hosts = {}

    def _link_manager(self):
        """
        The core loop that manages link state. It only toggles link status up/down.
        """
        print(f"[*] Link manager started. Timescale: {TIME_SCALE_FACTOR}x")
        
        while True:
            should_be_active = set()
            for index, row in self.intervals_df.iterrows():
                start_sec = row['StartTime']
                end_sec = row['EndTime']
                
                if start_sec <= self.current_sim_time < end_sec:
                    orig_name1 = str(row['Source']).strip()
                    orig_name2 = str(row['Target']).strip()
                    
                    if orig_name1 in self.name_map and orig_name2 in self.name_map:
                        canon_name1 = self.name_map[orig_name1]
                        canon_name2 = self.name_map[orig_name2]
                        if canon_name1 != canon_name2:
                            node_pair = frozenset([canon_name1, canon_name2])
                            should_be_active.add(node_pair)

            links_to_bring_up = should_be_active - self.active_links
            links_to_bring_down = self.active_links - should_be_active

            for link_pair in links_to_bring_up:
                node1, node2 = list(link_pair)
                print(f"[*] SIM_TIME: {self.current_sim_time}s | LINK UP: {node1}-{node2}")
                self.net.configLinkStatus(node1, node2, 'up')
                self.active_links.add(link_pair)

            for link_pair in links_to_bring_down:
                node1, node2 = list(link_pair)
                print(f"[*] SIM_TIME: {self.current_sim_time}s | LINK DOWN: {node1}-{node2}")
                self.net.configLinkStatus(node1, node2, 'down')
                self.active_links.remove(link_pair)
            
            time.sleep(1)
            self.current_sim_time += TIME_SCALE_FACTOR

    def run(self):
        """
        Builds the network, pre-creates all links in a "down" state, and runs the simulation.
        """
        print("[*] Building network with nodes as switches...")
        
        ip_counter = 1
        for index, row in self.nodes_df.iterrows():
            raw_node_name = str(row['NodeName']).strip()
            canonical_name = f's{ip_counter}'
            self.name_map[raw_node_name] = canonical_name

            switch = self.net.addSwitch(canonical_name)
            self.switches[canonical_name] = switch
            
            host_name = f'h_{canonical_name}'
            ip_address = f'10.0.0.{ip_counter}'
            host = self.net.addHost(host_name, ip=ip_address, prefixLen=24)
            self.net.addLink(host, switch)
            self.hosts[host_name] = host
            
            print(f"    - Added switch: {canonical_name} (from '{raw_node_name}') with test host: {host_name}")
            ip_counter += 1

        print("\n[*] Pre-creating all possible links in 'down' state...")
        all_link_pairs = set()
        for index, row in self.intervals_df.iterrows():
            orig_name1 = str(row['Source']).strip()
            orig_name2 = str(row['Target']).strip()

            if orig_name1 in self.name_map and orig_name2 in self.name_map:
                canon_name1 = self.name_map[orig_name1]
                canon_name2 = self.name_map[orig_name2]
                if canon_name1 != canon_name2:
                    all_link_pairs.add(frozenset([canon_name1, canon_name2]))
        
        for link_pair in all_link_pairs:
            node1, node2 = list(link_pair)
            self.net.addLink(self.switches[node1], self.switches[node2])
            time.sleep(0.01)
        
        print(f"[*] Total of {len(all_link_pairs)} inter-switch links pre-created.")

        print("\n[*] Starting network...")
        self.net.start()

        print("\n[*] Setting all inter-switch links to DOWN state initially...")
        for link_pair in all_link_pairs:
            node1, node2 = list(link_pair)
            self.net.configLinkStatus(node1, node2, 'down')

        manager_thread = threading.Thread(target=self._link_manager)
        manager_thread.daemon = True
        manager_thread.start()

        print("\n[*] Network is running. All links are initially down.")
        print("[*] The network is for internal testing only. Hosts cannot reach the internet.\n")

        CLI(self.net)

        print("[*] Stopping network...")
        self.net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    sat_net = SatelliteNetwork()
    sat_net.run()