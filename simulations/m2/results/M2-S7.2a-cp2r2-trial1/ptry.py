import sys, os; sys.argv=["x"]
sys.path.insert(0,"/root/inv/nascTime-5gtsn/simulations/m2/check")
import check_m2s72_b as B, m2s72_s6 as V
runs="/root/inv/nascTime-5gtsn/simulations/m2/results/M2-S7.2a-cp2r2-trial1/runs"
cfg=os.environ["CFG"]; base=os.environ["BASE"]
B.BN_BASE[cfg]=base
ev=B.RunEval(runs,cfg,0,conf_fn=lambda k: V.CONF(base,k,12*B.S))
B.f0_rows(ev); B.i_rows(ev); B.m2_rows(ev); stats=B.m3_rows(ev); B.m4_rows(ev,"Ca")
fails={r[0] for r in B.rows if r[2]=="FAIL"}
B.h_cov(ev,stats)
for r in B.rows:
    if r[0] in ("F0-1","I-2","M2","M3","M3d","M4","H-cov") : print(" | ".join(r)[:330])
print("fails",fails)
