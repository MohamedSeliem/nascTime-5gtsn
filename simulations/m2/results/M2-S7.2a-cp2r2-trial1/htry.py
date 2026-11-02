import sys; sys.argv=["x"]
sys.path.insert(0,"/root/inv/nascTime-5gtsn/simulations/m2/check")
import check_m2s72_b as B
runs="/root/inv/nascTime-5gtsn/simulations/m2/results/M2-S7.2a-cp2r2-trial1/runs"
cfg=sys.argv_cfg if hasattr(sys,"argv_cfg") else "M2S72-H-q0-Ca-n2"
import os
cfg=os.environ.get("CFG",cfg); rep=int(os.environ.get("REP","0"))
ref,_,_=B.evaluate(runs,"M2S72-B-q0-Ca-n1" if "-q0-" in cfg else "M2S72-B-qdu-Ca-n1",rep)
del B.rows[:]
ev,stats,fails=B.evaluate(runs,cfg,rep,ref=ref)
cov=B.h_cov(ev,stats)
for r in B.rows: print(" | ".join(r)[:700])
print("fails",fails)
