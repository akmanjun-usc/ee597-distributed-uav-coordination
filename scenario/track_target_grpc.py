#!/usr/bin/python

# Set target (waypoint) positions for UAVs
#
# Agreement protocol (UDP multicast):
#
#   Each UAV maintains a table of {uav_id -> (state, target_id, token, last_seen)}.
#   States: CLAIM (proposing a target) and LOCK (committed).
#
#   On every TrackTargets() tick, a UAV that is not locked picks an in-range
#   target that no peer has LOCKed. If multiple peers are CLAIMing the same
#   target, the one with the highest random token wins; the others back off
#   to a different target on the next tick. After a CLAIM_WAIT period with no
#   higher-token contender, the UAV upgrades CLAIM -> LOCK and rebroadcasts.
#
#   Locked UAVs send periodic HEARTBEATs so newly started or restarted peers
#   learn the current state. Entries with no heartbeat in PEER_TIMEOUT seconds
#   age out, which is how the protocol releases targets held by crashed UAVs.
#
#   Tiebreaking is done with a random token (not node id), per the assignment.

import sys
import struct
import socket
import math
import time
import argparse
import glob
import subprocess
import threading
import datetime
import random

from core.api.grpc import client
from core.api.grpc import core_pb2
import xmlrpc.client

# ---- agreement protocol tunables (balanced profile) ----
HEARTBEAT_INTERVAL = 1.0   # seconds between rebroadcasts of LOCK state
CLAIM_RETX         = 0.5   # seconds between rebroadcasts of CLAIM state (faster than LOCK
                           # so a contested claim is heard reliably under loss)
CLAIM_WAIT         = 1.5   # seconds a CLAIM must stand before becoming LOCK
PEER_TIMEOUT       = 4.0   # seconds; entries older than this are considered crashed
# ---------------------------------------------------------

# Message types
MSG_CLAIM = "CLAIM"
MSG_LOCK  = "LOCK"
MSG_FREE  = "FREE"   # explicit release (target out of range)

# Peer states
ST_IDLE  = "IDLE"
ST_CLAIM = "CLAIM"
ST_LOCK  = "LOCK"

mynodeseq = 0
nodecnt = 0
protocol = 'none'
mcastaddr = '235.1.1.1'
port = 9100
ttl = 64
core = None
session_id = None

filepath = '/tmp'
nodepath = ''

# Lock guarding peer_table and my_state
thrdlock = threading.Lock()
xmlproxy = xmlrpc.client.ServerProxy("http://localhost:8000", allow_none=True)

# My own state
my_id          = -1
my_state       = ST_IDLE     # IDLE | CLAIM | LOCK
my_target      = -1          # target currently claimed/locked (-1 if none)
my_token       = 0           # random tiebreak token for current claim
my_claim_start = 0.0         # timestamp when current CLAIM was issued
last_heartbeat = 0.0         # timestamp of last advertisement we sent

# Peer table: peer_id -> dict(state, target, token, ts)
peer_table = {}


# ---------------
# Calculate the distance between two points on a map
# ---------------
def Distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


# ---------------
# Redeploy a UAV back to its original position
# ---------------
def RedeployUAV():
    print("Redeploy UAV")
    position = xmlproxy.getOriginalWypt()
    xmlproxy.setWypt(position[0], position[1])


# ---------------
# Tell move_node_grpc.py which target we are tracking (-1 == none)
# ---------------
def RecordTarget(target_id):
    print("RecordTarget %d" % target_id)
    xmlproxy.setTarget(target_id)


# ---------------
# Build and send a multicast advertisement
# Wire format: "<msg_type> <uav_id> <target_id> <token>"
# ---------------
def AdvertiseUDP(msg_type, uav_id, target_id, token):
    addrinfo = socket.getaddrinfo(mcastaddr, None)[0]
    sk = socket.socket(addrinfo[0], socket.SOCK_DGRAM)
    ttl_bin = struct.pack('@i', ttl)
    sk.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl_bin)
    buf = "%s %d %d %d" % (msg_type, uav_id, target_id, token)
    sk.sendto(buf.encode('utf-8'), (addrinfo[4][0], port))
    sk.close()
    print("AdvertiseUDP -> %s" % buf)


# ---------------
# Background thread: receive and parse UDP advertisements
# ---------------
class ReceiveUDPThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True

    def run(self):
        ReceiveUDP()


def ReceiveUDP():
    addrinfo = socket.getaddrinfo(mcastaddr, None)[0]
    sk = socket.socket(addrinfo[0], socket.SOCK_DGRAM)
    sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sk.bind(('', port))

    group_bin = socket.inet_pton(addrinfo[0], addrinfo[4][0])
    mreq = group_bin + struct.pack('=I', socket.INADDR_ANY)
    sk.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    while True:
        try:
            buf, _ = sk.recvfrom(1500)
        except Exception as e:
            print("ReceiveUDP error:", e)
            continue

        try:
            parts = buf.decode('utf-8').strip().split(' ')
            if len(parts) != 4:
                continue
            msg_type = parts[0]
            uav_id   = int(parts[1])
            trgt_id  = int(parts[2])
            token    = int(parts[3])
        except Exception:
            continue

        # Ignore our own broadcasts
        if uav_id == my_id:
            continue

        UpdateTracking(msg_type, uav_id, trgt_id, token)


# ---------------
# Update peer table from a received advertisement
# ---------------
def UpdateTracking(msg_type, uav_id, trgt_id, token):
    now = time.time()

    with thrdlock:
        if msg_type == MSG_FREE:
            # Peer explicitly released its target -> drop it from the table
            if uav_id in peer_table:
                del peer_table[uav_id]
            return

        if msg_type not in (MSG_CLAIM, MSG_LOCK):
            return

        # Map message type to peer state
        new_state = ST_LOCK if msg_type == MSG_LOCK else ST_CLAIM

        peer_table[uav_id] = {
            "state":  new_state,
            "target": trgt_id,
            "token":  token,
            "ts":     now,
        }


# ---------------
# Helpers operating on the peer table (caller holds thrdlock)
# ---------------
def _prune_stale(now):
    """Remove peer entries that haven't been heard from in PEER_TIMEOUT."""
    stale = [pid for pid, p in peer_table.items() if now - p["ts"] > PEER_TIMEOUT]
    for pid in stale:
        print("Peer %d aged out" % pid)
        del peer_table[pid]


def _target_locked_by_peer(target_id):
    """Return True if some peer holds a LOCK on target_id."""
    for p in peer_table.values():
        if p["state"] == ST_LOCK and p["target"] == target_id:
            return True
    return False


def _highest_claim_token_for(target_id):
    """Highest claim token currently advertised by peers for target_id, or None."""
    best = None
    for p in peer_table.values():
        if p["state"] == ST_CLAIM and p["target"] == target_id:
            if best is None or p["token"] > best:
                best = p["token"]
    return best


# ---------------
# Main per-tick logic: pick a target and run the agreement protocol
# ---------------
def TrackTargets(covered_zone, track_range):
    global my_state, my_target, my_token, my_claim_start, last_heartbeat

    now = time.time()
    potential_targets = xmlproxy.getPotentialTargets(covered_zone, track_range)

    print("My state: %s, my target: %d, peers: %s"
          % (my_state, my_target, list(peer_table.keys())))
    print("Potential targets: %s" % potential_targets)

    with thrdlock:
        _prune_stale(now)

        # ---- Case 1: already LOCKed ----
        if my_state == ST_LOCK:
            if my_target in potential_targets:
                # Still in range -> refresh waypoint, periodic heartbeat
                _update_waypoint_to(my_target)
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    AdvertiseUDP(MSG_LOCK, my_id, my_target, my_token)
                    last_heartbeat = now
                return
            else:
                # Target left our range -> release and go idle
                print("Locked target %d left range; releasing" % my_target)
                AdvertiseUDP(MSG_FREE, my_id, my_target, my_token)
                my_state = ST_IDLE
                my_target = -1
                my_token = 0
                RecordTarget(-1)
                RedeployUAV()
                last_heartbeat = now
                return

        # ---- Case 2: currently in CLAIM phase ----
        if my_state == ST_CLAIM:
            # Check if a peer outranks us on the same target
            best_peer_tok = _highest_claim_token_for(my_target)
            outranked = best_peer_tok is not None and best_peer_tok > my_token
            locked_away = _target_locked_by_peer(my_target)

            if locked_away or outranked:
                # Back off: drop the claim, fall through to fresh selection
                print("Backing off claim on target %d (locked_away=%s, outranked=%s)"
                      % (my_target, locked_away, outranked))
                my_state = ST_IDLE
                my_target = -1
                my_token = 0
            elif my_target not in potential_targets:
                # Target moved out of range during the wait -> drop claim
                print("Claimed target %d no longer in range" % my_target)
                my_state = ST_IDLE
                my_target = -1
                my_token = 0
            elif now - my_claim_start >= CLAIM_WAIT:
                # Wait satisfied with no higher contender -> commit to LOCK
                print("Promoting CLAIM -> LOCK on target %d" % my_target)
                my_state = ST_LOCK
                _update_waypoint_to(my_target)
                RecordTarget(my_target)
                AdvertiseUDP(MSG_LOCK, my_id, my_target, my_token)
                last_heartbeat = now
                return
            else:
                # Still waiting; rebroadcast claim so peers don't drop us.
                # Use the faster CLAIM_RETX cadence (not HEARTBEAT_INTERVAL) so that
                # under packet loss a contested claim is still heard before the
                # 1.5s wait expires. Three transmissions across the wait window
                # drive the joint-loss probability to ~0.8% at 20% loss.
                if now - last_heartbeat >= CLAIM_RETX:
                    AdvertiseUDP(MSG_CLAIM, my_id, my_target, my_token)
                    last_heartbeat = now
                return

        # ---- Case 3: IDLE -> try to claim something ----
        # Pick the first in-range target that is neither LOCKed by a peer
        # nor CLAIMed by a peer with a higher token than the one we'd issue.
        candidate = None
        new_token = random.randint(1, 2 ** 31 - 1)

        for tgt in potential_targets:
            if _target_locked_by_peer(tgt):
                continue
            best = _highest_claim_token_for(tgt)
            if best is not None and best >= new_token:
                # A peer's existing claim outranks the token we'd issue;
                # let them have it, look at the next target.
                continue
            candidate = tgt
            break

        if candidate is None:
            # Nothing to claim this tick. Stay idle, no broadcast.
            return

        my_state = ST_CLAIM
        my_target = candidate
        my_token = new_token
        my_claim_start = now

        print("Issuing CLAIM on target %d with token %d" % (my_target, my_token))
        AdvertiseUDP(MSG_CLAIM, my_id, my_target, my_token)
        last_heartbeat = now


def _update_waypoint_to(target_id):
    """Push the target's current position as our waypoint via XML-RPC."""
    try:
        response = core.get_node(session_id, target_id)
        node = response.node
        xmlproxy.setWypt(int(node.position.x), int(node.position.y))
    except Exception as e:
        print("_update_waypoint_to(%d) failed: %s" % (target_id, e))


# ---------------
# main
# ---------------
def main():
    global protocol
    global nodepath
    global mynodeseq
    global nodecnt
    global core
    global session_id
    global my_id

    parser = argparse.ArgumentParser()
    parser.add_argument('-my', '--my-id', dest='uav_id', metavar='my id',
                        type=int, default=1, help='My Node ID')
    parser.add_argument('-c', '--covered-zone', dest='covered_zone', metavar='covered zone',
                        type=int, default=1200, help='UAV covered zone limit on X axis')
    parser.add_argument('-r', '--track_range', dest='track_range', metavar='track range',
                        type=int, default=600, help='UAV tracking range')
    parser.add_argument('-i', '--update_interval', dest='interval', metavar='update interval',
                        type=int, default=1, help='Update Interval (msec)')
    parser.add_argument('-p', '--protocol', dest='protocol', metavar='comms protocol',
                        type=str, default='none', help='Comms Protocol')
    args = parser.parse_args()

    protocol = args.protocol
    my_id = args.uav_id

    # Seed RNG per-process so each UAV picks different tokens even if started
    # at the same wall-clock instant.
    random.seed((int(time.time() * 1e9) ^ (my_id * 2654435761)) & 0xFFFFFFFF)

    # Create grpc client
    core = client.CoreGrpcClient("172.16.0.254:50051")
    core.connect()
    response = core.get_sessions()
    if not response.sessions:
        raise ValueError("no current core sessions")
    session_summary = response.sessions[0]
    session_id = int(session_summary.id)
    core.get_session(session_id)

    # Reset XML-RPC state and waypoint
    RedeployUAV()
    RecordTarget(-1)

    nodecnt += 1
    mynodeseq = 0  # only one UAV's state lives in this process

    corepath = "/tmp/pycore.*/"
    nodepath = glob.glob(corepath)[0]
    msecinterval = float(args.interval)
    secinterval = msecinterval / 1000.0

    if protocol == "udp":
        recvthrd = ReceiveUDPThread()
        recvthrd.start()

    # Main tracking loop
    while True:
        time.sleep(secinterval)
        if protocol == "udp":
            TrackTargets(args.covered_zone, args.track_range)
        else:
            # No-comms baseline: greedy, no agreement
            _track_no_comms(args.covered_zone, args.track_range)


# ---------------
# Fallback "no comms" mode (kept for parity with the original baseline)
# ---------------
def _track_no_comms(covered_zone, track_range):
    global my_state, my_target

    potential_targets = xmlproxy.getPotentialTargets(covered_zone, track_range)

    # Already locked: just keep the waypoint fresh, or release if out of range
    if my_state == ST_LOCK:
        if my_target in potential_targets:
            _update_waypoint_to(my_target)
            return
        my_state = ST_IDLE
        my_target = -1
        RecordTarget(-1)
        RedeployUAV()
        return

    # Not locked: take the first available target
    if potential_targets:
        my_target = potential_targets[0]
        my_state = ST_LOCK
        _update_waypoint_to(my_target)
        RecordTarget(my_target)


if __name__ == '__main__':
    main()
