# Preserved experiment results

Each result directory contains:

- `output.txt`: captured terminal output and per-test outcomes;
- `latency.log`: the test harness's latency summary; and
- `throughput.png`: the corresponding retained throughput plot.

## Summary

| Directory | Loss | Delay | Claim retransmission | Passes | Mean latency |
|---|---:|---:|---:|---:|---:|
| `ideal/` | 0% | approximately 1 us | 1.0 s | 8/8 | 8.9884 s |
| `realistic-v1/` | 20% | 200 ms | 1.0 s | 4/8 | 10.4218 s |
| `realistic-v2/` | 20% | 200 ms | 0.5 s | 5/8 | 10.7159 s |

These are individual recorded runs rather than repeated statistical experiments. The console captures for the realistic runs also include throughput-tool parsing warnings. Consult `docs/limitations.md` before drawing conclusions from the plots.

