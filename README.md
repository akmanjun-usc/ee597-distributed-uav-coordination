# Distributed UAV Coordination over Lossy UDP Multicast

This repository contains an academic implementation and experimental evaluation of a distributed agreement protocol for assigning UAVs to targets. Eight UAV processes communicate over UDP multicast inside the [CORE](https://coreemu.github.io/core/) network emulator. Each live UAV attempts to select a target that is not held by another UAV, without using a fixed UAV-to-target mapping or a central coordinator.

The project studies three metrics:

- correctness: whether active UAVs finish with distinct targets;
- latency: time until the required UAVs have selected targets; and
- control-plane throughput: bandwidth consumed by coordination messages.

The implementation is preserved as evaluated for the course project. Its known limitations and unsuccessful trials are intentionally documented rather than hidden.

## Protocol summary

Each UAV runs an `IDLE -> CLAIM -> LOCK` state machine and exchanges `CLAIM`, `LOCK`, and `FREE` messages on multicast group `235.1.1.1:9100`.

- An idle UAV selects an available in-range target and advertises a claim with a random token.
- Competing claims are resolved in favor of the largest observed random token.
- A claim becomes a lock after a conflict-free waiting period.
- Locked UAVs advertise periodic heartbeats.
- Peer entries expire after a timeout so assignments belonging to crashed tracking processes can eventually be released.

See [docs/protocol.md](docs/protocol.md) for the state machine, timing values, and message format.

## Recorded results

These are the single recorded runs included in the repository:

| Configuration | Network condition | Tests passed | Mean measured latency |
|---|---|---:|---:|
| Ideal | No induced loss or delay | 8/8 | 8.99 s |
| Realistic V1 | 20% loss, 200 ms delay, 1.0 s claim retransmission | 4/8 | 10.42 s |
| Realistic V2 | 20% loss, 200 ms delay, 0.5 s claim retransmission | 5/8 | 10.72 s |

Raw console output, latency logs, and throughput plots are retained under [`results/`](results/). These measurements are course-project observations, not statistically representative benchmarks.

## Repository layout

```text
scenario/     Runnable CORE scenario, existing protocol, launchers, and harness
results/      Preserved outputs for ideal and realistic network profiles
report/       Submitted report source, figures, and PDF
docs/         Protocol, setup, experiment, and limitation notes
upstream/     Original framework instructions and assignment prompt supplied with the lab
```

The submitted `track_target_grpc.py` is placed directly beside `start_tracking_grpc.sh`, and the submitted test harness is under `scenario/test/`. This resolves the duplicate-directory ambiguity in the original coursework folder without changing the Python or shell implementation.

## Environment

The project was developed for the supplied Linux VM and is not expected to run natively on macOS or Windows.

- Ubuntu 18.04 VM
- CORE 7.1.0
- Python through CORE's `core-python` command
- `mgen`, `trpr`, `gnuplot`, `tcpdump`, and `eog` for the original throughput workflow

The 3 GB course VM is deliberately not included. See [docs/experiment-setup.md](docs/experiment-setup.md) for the original setup and execution procedure.

## Running in the supplied VM

From the repository root, expose the files expected by the scenario's fixed `/data/uas-core` paths:

```bash
sudo mkdir -p /data/uas-core
sudo ln -s "$(pwd)/scenario/icons" /data/uas-core/icons
sudo ln -s "$(pwd)/scenario/move_node_grpc.py" /data/uas-core/move_node_grpc.py
```

Start CORE and open the scenario:

```bash
sudo service core-daemon start
core-pygui
```

Open `scenario/uav8-notrack-new-gui.xml`, start the scenario, and then run:

```bash
cd scenario
./start_tracking_grpc.sh udp
```

In another terminal:

```bash
cd scenario/test
./start_testing_grpc.sh udp
```

The scenario and network impairment settings still require the supplied CORE/Linux environment. They have not been revalidated after this repository-only reorganization.

## Important limitations

- Under the recorded realistic network settings, the protocol did not always prevent duplicate assignments.
- The implementation is coupled to CORE 7.1.0, fixed node identifiers, `/tmp/pycore.*`, `/data/uas-core`, and the supplied control network.
- The recorded experiment contains one run per configuration.
- Sequential-arrival tests include the harness's target-movement interval in their latency.
- Saved test output contains `trpr` parsing warnings, so throughput plots should be treated as coursework artifacts rather than independently validated measurements.
- No unit or continuous-integration test suite is included; testing requires CORE and Linux.

The complete list is in [docs/limitations.md](docs/limitations.md).

This repository must not be interpreted as flight-control software or as a safety-certified distributed system.
