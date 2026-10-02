# Protocol design

## Objective

The scenario contains eight UAVs and eight targets. Each active UAV may track at most one target, and two UAVs should not settle on the same target. UAVs communicate through unreliable UDP multicast and do not have a central coordinator.

## Local states

```text
IDLE --select target / CLAIM--> CLAIM
CLAIM --wait expires / LOCK--> LOCK
CLAIM --out-ranked or unavailable--> IDLE
LOCK --target leaves range / FREE--> IDLE
```

Each process stores its own state and a table containing the most recently received state for every observed peer.

## Messages

Messages use a four-field UTF-8 representation:

```text
<message-type> <uav-id> <target-id> <random-token>
```

The message types are:

- `CLAIM`: tentative request for a target;
- `LOCK`: notification that the sender committed to a target; and
- `FREE`: explicit release when a locked target leaves range.

The multicast destination is `235.1.1.1:9100`.

## Timing profile

| Parameter | Value | Purpose |
|---|---:|---|
| `CLAIM_RETX` | 0.5 s | Claim retransmission interval in the retained implementation |
| `CLAIM_WAIT` | 1.5 s | Conflict-observation period before locking |
| `HEARTBEAT_INTERVAL` | 1.0 s | Lock advertisement interval |
| `PEER_TIMEOUT` | 4.0 s | Time after which an unheard peer is removed |
| Main update interval | 0.5 s | Tracking-loop interval selected by the launcher |

The report also records a realistic V1 experiment with `CLAIM_RETX = 1.0 s`; the retained source contains the later V2 value of `0.5 s`.

## Conflict resolution

When several UAVs claim the same target, the greatest random token observed during the waiting period wins. Lower-token claimants return to `IDLE` and try another available target. Random tokens are used instead of a fixed priority derived from UAV identifiers or positions.

## Failure handling

Locked UAVs periodically repeat their `LOCK` message. If a peer has not been heard from for `PEER_TIMEOUT`, its table entry is removed. An explicit `FREE` message releases a target sooner when a UAV remains operational but its target moves out of range.

This mechanism improves availability, but it does not guarantee consensus under arbitrary message loss. The retained implementation and its measured failures are described in [limitations.md](limitations.md).

