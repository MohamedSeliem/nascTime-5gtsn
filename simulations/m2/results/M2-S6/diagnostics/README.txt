M2-S6 diagnostics (results doc section 8, findings 1 and 6). These are not checker rows.

Inputs: the configs below were regenerated (rep 0) in the fresh-clone rehearsal at cdae12a with the
same opp_run command line as m2s6.sh. Their PCAP and per-frame/engine/TT-clock logs are hash-identical
to results/M2-S6/raw-outputs.sha256:
  M2S6-B-m100-0      33/33
  M2S6U-Q10-0        10/10
  M2S6-E-all-load-0  35/35

Commands (from simulations/m2; <runs> = the --result-dir parent):
  python3 check/diag_m2s6_lag.py <runs> M2S6-B-m100 0      > lag-M2S6-B-m100-0.txt
  python3 check/diag_m2s6_lag.py <runs> M2S6-E-all-load 0  > lag-M2S6-E-all-load-0.txt
  python3 check/diag_m2s6_h8.py  <runs> M2S6U-Q10 0        > h8-M2S6U-Q10-0.txt

lag-*.txt: per step, lambda from the O3/O5 decomposition (the check rows' oracle) next to the
  rate-leakage prediction (eps_{k-1} - eps_{k-2}) / (s2_{k-1} - s2_{k-2}) * lag_k.
  Units: ns, ms. The cal column is y for calibrated and n for uncalibrated.
h8-*.txt: O5 replayed on the recorded inputs with and without the K7 tick resets.
  Caveat: without resets the slave's own Pdelay timers would fire slightly differently.
