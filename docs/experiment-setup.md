# Experiment setup

## Required environment

The retained scripts target the environment supplied for EE 597 Lab 2:

- Ubuntu 18.04;
- CORE 7.1.0;
- a running CORE daemon reachable through the configured control network;
- `core-python` for scripts importing the CORE Python API;
- `tcpdump`, `mgen`, `trpr`, `gnuplot`, and `eog` for the original plotting workflow.

The VM image is not included in this repository.

## CORE filesystem setup

The scenario contains fixed references to `/data/uas-core/icons` and `/data/uas-core/move_node_grpc.py`. From the repository root, create the expected links:

```bash
sudo mkdir -p /data/uas-core
sudo ln -s "$(pwd)/scenario/icons" /data/uas-core/icons
sudo ln -s "$(pwd)/scenario/move_node_grpc.py" /data/uas-core/move_node_grpc.py
```

If destinations already exist, inspect them before replacing anything.

## Starting the scenario

```bash
sudo service core-daemon start
core-pygui
```

Open `scenario/uav8-notrack-new-gui.xml` and start the scenario. The legacy GUI can instead use `uav8-notrack-old-gui.xml`.

Start the tracking process in each UAV namespace:

```bash
cd scenario
./start_tracking_grpc.sh udp
```

Per-node movement and tracking output is written under `/tmp`, including `move_n#.log` and `track_n#.log`.

## Running the retained harness

```bash
cd scenario/test
./start_testing_grpc.sh udp
```

The harness exercises:

1. sequential arrival of all eight targets;
2. sequential arrival in shuffled order;
3. partial availability of six targets;
4. simultaneous target arrival;
5. loss of one tracking process; and
6. loss of two tracking processes.

It records latency and attempts to capture multicast throughput from each UAV with `tcpdump`, `trpr`, and `gnuplot`.

## Network profiles

The course workflow configures the `wlan21` network through the CORE GUI:

- ideal: 0% loss and approximately 1 microsecond delay;
- realistic: 20% packet loss and 200 milliseconds transmission delay.

The profile is not selected automatically by the retained scripts. Verify the WLAN configuration before every run and record it with the resulting output.

## Preserved measurements

The `results/` directory contains the console output, latency log, and throughput image retained from each recorded configuration. See `results/README.md` for interpretation notes.

