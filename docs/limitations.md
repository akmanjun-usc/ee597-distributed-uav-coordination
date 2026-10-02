# Known limitations

This repository intentionally preserves the evaluated course-project implementation. The following limitations have not been corrected.

## Protocol limitations

- A UAV in `LOCK` does not reconcile a conflicting `LOCK` received from another UAV. If two claimants miss one another's messages, duplicate assignments can persist.
- UDP provides no delivery, ordering, or duplication guarantees. Messages do not include epochs or sequence numbers, so delayed state can replace newer peer state.
- Peer membership is learned opportunistically; there is no explicit membership or quorum protocol.
- Every idle UAV examines potential targets in the order returned by the movement service, which can concentrate contention on the same target.
- Protocol timers are wall-clock based and fixed in the source.

## Evaluation limitations

- The realistic V1 run passed 4 of 8 cases, while V2 passed 5 of 8. The protocol therefore did not demonstrate reliable one-to-one assignment under the tested impairment profile.
- Only one retained run exists for each configuration, so success rates and latency values do not include confidence intervals or run-to-run variance.
- The test harness stops when enough UAVs report some assignment, before requiring that the final assignments are unique and stable.
- The uniqueness check records assignment history, not exclusively the final assignment snapshot.
- Sequential tests include deliberate two-second gaps between target movements, imposing a substantial lower bound on measured end-to-end latency.
- The retained console output includes `trpr` warnings about invalid `tcpdump` output. Throughput images are preserved as submitted artifacts, not independently validated measurements.

## Portability limitations

- The code requires Linux, CORE 7.1.0, its Python environment, virtual node commands, and XML-RPC movement services.
- It contains fixed addresses, ports, node IDs, paths, and assumptions specific to the supplied scenario.
- The scenario expects resources under `/data/uas-core` and CORE runtime directories matching `/tmp/pycore.*`.
- No automated unit tests or CI workflow are included because execution depends on the external emulator environment.

## Scope

This is an educational distributed-systems and network-emulation artifact. It is not suitable for controlling physical aircraft or for safety-critical deployment.

