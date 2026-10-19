"""Per-step servo terms for one run: lambda vs the rate-leakage prediction
   Usage: diag_m2s6_lag.py <runs dir> <config> <rep>   (diagnostic, not a check row)
   lambda_k ~= +(eps_{k-1} - eps_{k-2}) / (s2_{k-1} - s2_{k-2}) * lag_k   (gmRR of step k-1 contains the change of eps)."""
import sys, os
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import m2s6_runs as RR, check_m2s6 as CK
R = RR.Run(sys.argv[1], sys.argv[2], int(sys.argv[3]))
E = CK.Eval(R)
fus = {f["seq"]: f for f in E.fus}
st = [f for f in E.fus if "old" in f]
print("seq  cal  eps(ns)  lag(ms)  lambda(ns)  predicted(ns)  e+(ns)  max_between(ns)")
iv = {i["seq"]: i for i in E.iv}
for j, f in enumerate(st):
    i = iv[f["seq"]]; lag = f["sF"] - f["s2"]
    pred = None
    if j >= 2:
        a, b = st[j-2], st[j-1]
        pred = float(b["eps"] - a["eps"]) / float(b["s2"] - a["s2"]) * float(lag)
    print(f'{f["seq"]:3d}  {"y" if f.get("nrr_valid") else "n"}  {float(i["eps"])/1e3:9.3f}  {float(lag)/1e9:7.3f}  {float(i["lam"])/1e3:9.3f}  '
          f'{"" if pred is None else f"{pred/1e3:9.3f}"}  {float(i["e_plus"])/1e3:8.3f}  {"" if i["max_between"] is None else float(i["max_between"])/1e3}')
