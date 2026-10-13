# Draft upstream issues for Simu5G 1.8.0 (NOT SUBMITTED)

Three behaviours of Simu5G 1.8.0 that nascTime M1 found and explained. They are prepared as issue drafts with minimal reproductions that use **Simu5G only**: its own `simulations/nr/ethernet` network and `Ethernet-Bridge` config, with no nascTime code or NED. **They have not been submitted.** Submission is a separate decision.

| Draft | Title | M1 record |
|---|---|---|
| `issue-1-harq-discard.md` | MAC deletes MAC PDUs (and the RLC data in them) when no HARQ TX process is free; no statistic records it | `results/O-S3-1.md` |
| `issue-2-dl-tail-lag.md` | NR UM DL grant counts one RLC header per connection: the last of several queued SDUs is cut and its remainder waits for the next SDU | `results/O-tail.md` |
| `issue-3-gtp-region-tags.md` | GtpUser re-creates packets from their data, so INET packet-level region tags (flow measurement) do not cross the 5G system | `results/S5.md` |

## Reproduce

- `issues.ini`: the configs. Drop it into Simu5G's `simulations/nr/ethernet/` next to its `omnetpp.ini`, which it includes.
- `run_issues.sh`: runs all configs, seed 0, in a scratch copy of Simu5G's `simulations/` tree (the upstream tree is not touched). It then calls `check_issues.py`, which prints the evidence (about 3 min). Output goes to `../results/upstream-issues/`.

Stack: OMNeT++ 6.4.0, INET 4.7.0, Simu5G 1.8.0 (tag `v1.8.0`), all unmodified.
