"""Analysis of the minimal upstream-example reproduction (repro.ini): UL offered vs achieved (UDP app scalars) and the
gNB UL scheduling cycle (BSR reports, candidate TTIs, grants) from the MAC log (prefix %t|%M|). Window [0.5 s, 3 s)."""
import gzip, re, sys
from collections import Counter
GNB = "SingleCell_Standalone.gnb.cellularNic.mac"
def sca(path):
    v = {}
    for line in open(path):
        p = line.split()
        if line.startswith("scalar ") and len(p) >= 4:
            v[(p[1], p[2])] = p[3]
    return v
def ul(path):
    ev, sec = {}, None
    with gzip.open(path, "rt", errors="replace") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|", 2)
            if len(p) < 3 or p[1] != GNB or not p[0][:1].isdigit():
                continue
            t, msg = round(float(p[0]) * 1000), p[2]
            if "AmcPilotAuto" in msg or "LteAllocator" in msg or "pushFeedback" in msg:
                continue
            if "= UPLINK =" in msg: sec = "UL"
            elif "= DOWNLINK =" in msg: sec = "DL"
            elif "END UPLINK" in msg or "END DOWNLINK" in msg: sec = None
            e = ev.setdefault(t, {"cand": 0, "grant": 0, "bytes": 0, "bsr": 0})
            if re.search(r"UlBacklogRegistry: MacCid\(.*\) reports \d+ bytes", msg): e["bsr"] += 1
            if sec != "UL": continue
            if "QoSAwareScheduler::CID--->" in msg or "LteMaxCI::schedule computed for cid" in msg: e["cand"] += 1
            m = re.search(r"QoSAwareScheduler::Grant .* granted=(\d+)B", msg) or re.search(r"LteMaxCI::schedule granted (\d+) bytes", msg)
            if m and int(m.group(1)) > 0: e["grant"] += 1; e["bytes"] += int(m.group(1))
    w = [t for t in ev if 500 <= t < 3000]
    return {k: sum(1 for t in w if ev[t][k]) if k != "bytes" else sum(ev[t]["bytes"] for t in w) for k in ("bsr", "cand", "grant", "bytes")}
for b in ("simu5g-1.8.1",):
    for c in ("Repro-UL-QOSPF", "Repro-UL-MAXCI"):
        v = sca(f"results/{b}/{c}/0.sca")
        sent = int(float(v.get(("SingleCell_Standalone.ue[0].app[0]", "packetSent:count"), "nan")))
        rcvd = int(float(v.get(("SingleCell_Standalone.server.app[0]", "packetReceived:count"), "nan")))
        u = ul(f"results-{b}-{c}.log.gz")
        print(f"{b:9s} {c:15s} UDP sent {sent} received {rcvd} ({rcvd / sent:.3f}) | [0.5 s, 3 s): BSR TTIs {u['bsr']}, candidate TTIs {u['cand']}, grant TTIs {u['grant']}, granted {u['bytes']} B")
