#!/usr/bin/env python3
"""Tests of tools/bridge_delay.py (M2B-2 S-OBS offline observer) on synthetic M2-S1 port logs (no simulation)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "tools", "bridge_delay.py")
spec_ = importlib.util.spec_from_file_location("bridge_delay", TOOL)
BD = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(BD)
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


def row(tt=2, tagged=1, fid=1, t1="0.001", itt=1, et=2048, pcp=5, vid=42, t12="0.006000001", res=None, egress=None, event="tx", role="egress"):
    egress = t12 if egress is None else egress
    if res is None and tagged == 1:
        from decimal import Decimal
        res = str(Decimal(egress) - Decimal(t1))
    return [event, t12, str(tt), role, "17", str(tagged), str(fid) if tagged else "", t1 if tagged else "",
            str(itt) if tagged else "", str(et), str(pcp), str(vid), "100", "h", "h", "", "", "0.0059", "0.00591",
            "0.0059", t12, egress, res or "", ""]


def run(rows_by_file, d):
    paths = []
    for i, rows in enumerate(rows_by_file):
        p = os.path.join(d, f"l{i}.egress.port.csv")
        with open(p, "w") as fh:
            fh.write(",".join(BD.COLUMNS) + "\n")
            for r in rows:
                fh.write(",".join(r) + "\n")
        paths.append(p)
    return paths


with tempfile.TemporaryDirectory() as d:
    rows = [row(fid=1, t1="0.001", t12="0.006000001"), row(fid=2, t1="0.002", t12="0.009"),
            row(fid=3, pcp=0, t1="0.003", t12="0.004"), row(tagged=0, pcp=0), row(et=0x88F7, pcp=-1, vid=-1, tagged=0),
            row(fid=4, itt=2, t1="0.005", t12="0.0051"),
            ["rx", "0.001", "2", "ingress"] + [""] * 20]
    up = [row(tt=1, itt=2, fid=7, t1="0.010", t12="0.0150005", pcp=5)]
    out = BD.observe(run([rows, up], d))
    pairs = {(p["ingressTtId"], p["egressTtId"], p["pcp"], p["vid"]): p for p in out["pairs"]}
    check("BD-1 per port pair and PCP / VID: DL PCP 5 two frames, exact ps min / max / sum",
          pairs[(1, 2, 5, 42)]["count"] == 2 and pairs[(1, 2, 5, 42)]["min_ps"] == 5000001000 and pairs[(1, 2, 5, 42)]["max_ps"] == 7000000000
          and pairs[(1, 2, 5, 42)]["sum_ps"] == 12000001000, str(pairs.get((1, 2, 5, 42))))
    check("BD-2 PCP 0 is its own group", pairs[(1, 2, 0, 42)]["count"] == 1 and pairs[(1, 2, 0, 42)]["min_ps"] == 1000000000)
    check("BD-3 UL direction is its own port pair (2 -> 1)", pairs[(2, 1, 5, 42)]["count"] == 1 and pairs[(2, 1, 5, 42)]["min_ps"] == 5000500000)
    check("BD-4 classes: residence 4, untagged 1, gPTP 1 (never mixed into R), not-bridged 1; rx rows ignored",
          out["classes"] == {"residence": 4, "gptp": 1, "untagged": 1, "not-bridged": 1}, str(out["classes"]))
    check("BD-5 every tx row is in exactly one class", sum(out["classes"].values()) == 7)
    check("BD-6 deterministic output", json.dumps(BD.observe(run([rows, up], d)), sort_keys=True) == json.dumps(out, sort_keys=True))
    NEG = [
        ("residence not egressTime - ingressTime", [row(res="0.004")], "!= egressTime - ingressTime"),
        ("egressTime not tTxEnd (another egress event)", [row(egress="0.0059")], "egressTime is not tTxEnd"),
        ("same frame transmitted twice by one egress translator (double count)", [row(fid=1), row(fid=1)], "double count"),
        ("egress before ingress", [row(t1="0.007", t12="0.006")], "egress before ingress"),
        ("wrong header", None, "header differs"),
        ("short row", [row()[:10]], "fields, expected"),
        ("malformed time", [row(t1="abc", res="0.001")], "not a time"),
        ("tx row in an ingress log", [row(role="ingress")], "expected an egress port log"),
    ]
    for name, rr, want in NEG:
        try:
            if rr is None:
                p = os.path.join(d, "bad.csv")
                open(p, "w").write("event,t\n")
                BD.observe([p])
            else:
                BD.observe(run([rr], d))
            check(f"BD-negative {name}", False, "accepted")
        except BD.LogError as ex:
            check(f"BD-negative {name}", want in str(ex), str(ex))
    check("BD-7 the same frame at two different egress translators (DL flooding) is two observations, not a double count",
          BD.observe(run([[row(tt=2, fid=1)], [row(tt=3, fid=1)]], d))["classes"]["residence"] == 2)
    r = subprocess.run([sys.executable, "-I", "-B", TOOL, os.path.join(d, "bad.csv")], capture_output=True, text=True)
    check("BD-cli invalid log: exit 1, nothing on stdout", r.returncode == 1 and r.stdout == "" and "error:" in r.stderr)
    r = subprocess.run([sys.executable, "-I", "-B", TOOL] + run([rows], d), capture_output=True, text=True)
    check("BD-cli valid logs: exit 0, JSON on stdout", r.returncode == 0 and json.loads(r.stdout)["classes"]["residence"] == 3)

print(f"\nM2B-2 bridge-delay observer tests: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
