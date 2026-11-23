#!/usr/bin/env python3
"""M2B-2 S-OBS offline bridge-delay observer (docs/migration/m2b-2-clock-and-observation.md section 3).

Reads the M2-S1 port logs ("<logFile>.egress.port.csv") written by TtTimestampLayer with observePort at the bridge
EGRESS translators' TSN ports (eth[1]) and reports the complete observed bridge residence interval of M2-S1,
R = t12 - t1 (t1: last bit received at the ingress translator's TSN port, carried by TtTimestampTag.ingressTime;
t12: last bit sent at the egress translator's TSN port, transmissionEnded), per port pair and per PCP / VID.

It is passive: it only reads logs after a run; it never changes forwarding, timing or any configuration.

    python3 -I -B bridge_delay.py <egress TSN-port log> [<egress TSN-port log> ...]

Classification of every "tx" row (every row is counted in exactly one class; nothing is double counted):
    residence      tagged, ingress translator != egress translator, not gPTP: one observation of R
    gptp           EtherType 0x88F7: gPTP event / general messages; their residence is handled by the translator's
                   transparent-clock path (correctionField), never mixed into the data-plane R
    untagged       no TtTimestampTag at egress (no ingress metadata): counted, no R (no value is inferred)
    not-bridged    tagged by the same translator that transmits it: not a 5G-system bridge crossing
Errors (exit 1, nothing printed on stdout): a malformed log; a time that is not an exact, finite number of
picoseconds (no rounding; NaN / Infinity rejected); egressTime not the M2-S1 t12 (transmissionEnded); a
residence that is not egressTime - ingressTime; the same (ingress translator, frame id) transmitted twice by one
egress translator (double counting); an egress before its ingress.
Output (stdout, JSON, deterministic): per (ingressTtId, egressTtId, pcp, vid): count, min / max / sum in integer ps
and mean as a decimal string; the class counts. Statistics only - no claim beyond the logged runs.
"""
import csv
import json
import re
import sys
from decimal import Decimal, InvalidOperation

GPTP = 0x88F7
COLUMNS = ["event", "t", "ttId", "role", "treeId", "tagged", "frameId", "ingressTime", "ingressTtId", "etherType",
           "pcp", "vid", "payloadLen", "hash", "txHash", "tRxStart", "tRxEnd", "tSlot", "tDequeue", "tTxStart",
           "tTxEnd", "egressTime", "residence", "note"]


class LogError(Exception):
    pass


TIME = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")
MAX_PS = 2 ** 63 - 1                                     # the OMNeT++ simtime_t range (int64 raw at ps resolution)


def ps(text, what):
    """an exact integer number of picoseconds; anything else is a LogError: a fractional picosecond, NaN or
    Infinity, a non-decimal spelling (whitespace, '_', '+', hex), or a value outside the simtime_t range.
    No rounding: the value must be exactly representable at ps resolution."""
    if not isinstance(text, str) or TIME.fullmatch(text) is None:
        raise LogError(f"{what}: {text!r} is not a time (not a finite decimal)")
    try:
        d = Decimal(text)
    except (InvalidOperation, ArithmeticError):
        raise LogError(f"{what}: {text!r} is not a time (not a finite decimal)")
    if not d.is_finite():
        raise LogError(f"{what}: {text!r} is not a time (not a finite decimal)")
    sign, digits, exp = d.as_tuple()
    e = exp + 12                                         # value in ps = coefficient * 10**e
    coeff = int("".join(map(str, digits))) if digits else 0
    if coeff == 0:
        return 0
    if e > 19:
        raise LogError(f"{what}: {text!r} is outside the simtime_t range")
    if -e > len(digits):                                 # 0 < coeff < 10**-e: a fraction of a picosecond remains
        raise LogError(f"{what}: {text!r} is not an exact number of picoseconds")
    if e >= 0:
        value = coeff * 10 ** e
    else:
        q, r = divmod(coeff, 10 ** -e)
        if r != 0:
            raise LogError(f"{what}: {text!r} is not an exact number of picoseconds")
        value = q
    value = -value if sign else value
    if abs(value) > MAX_PS:
        raise LogError(f"{what}: {text!r} is outside the simtime_t range")
    return value


def integer(text, what):
    try:
        return int(text)
    except ValueError:
        raise LogError(f"{what}: {text!r} is not an integer")


def observe(paths):
    groups, classes, seen = {}, {"residence": 0, "gptp": 0, "untagged": 0, "not-bridged": 0}, set()
    for path in paths:
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh))
        except (csv.Error, UnicodeDecodeError) as ex:
            raise LogError(f"{path}: not a readable CSV log ({ex.__class__.__name__})")
        if not rows or rows[0] != COLUMNS:
            raise LogError(f"{path}: not an M2-S1 port log (header differs)")
        for n, row in enumerate(rows[1:], 2):
            where = f"{path}:{n}"
            if len(row) != len(COLUMNS):
                raise LogError(f"{where}: {len(row)} fields, expected {len(COLUMNS)}")
            r = dict(zip(COLUMNS, row))
            if r["event"] != "tx":
                continue
            if r["role"] != "egress":
                raise LogError(f"{where}: a tx row of role {r['role']!r} (expected an egress port log)")
            egress_tt = integer(r["ttId"], f"{where} ttId")
            if integer(r["etherType"], f"{where} etherType") == GPTP:
                classes["gptp"] += 1
                continue
            if r["tagged"] != "1":
                classes["untagged"] += 1
                continue
            ingress_tt = integer(r["ingressTtId"], f"{where} ingressTtId")
            if ingress_tt == egress_tt:
                classes["not-bridged"] += 1
                continue
            t1, t12 = ps(r["ingressTime"], f"{where} ingressTime"), ps(r["egressTime"], f"{where} egressTime")
            if t12 != ps(r["tTxEnd"], f"{where} tTxEnd"):
                raise LogError(f"{where}: egressTime is not tTxEnd (the log was not written with the M2-S1 t12 definition)")
            rr = ps(r["residence"], f"{where} residence")
            if rr != t12 - t1:
                raise LogError(f"{where}: residence {rr} ps != egressTime - ingressTime {t12 - t1} ps")
            if rr < 0:
                raise LogError(f"{where}: egress before ingress")
            ident = (ingress_tt, integer(r["frameId"], f"{where} frameId"), egress_tt)
            if ident in seen:
                raise LogError(f"{where}: frame {ident[1]} of translator {ident[0]} transmitted twice by translator {egress_tt} (double count)")
            seen.add(ident)
            key = (ingress_tt, egress_tt, integer(r["pcp"], f"{where} pcp"), integer(r["vid"], f"{where} vid"))
            g = groups.setdefault(key, [0, None, None, 0])
            g[0] += 1
            g[1] = rr if g[1] is None else min(g[1], rr)
            g[2] = rr if g[2] is None else max(g[2], rr)
            g[3] += rr
            classes["residence"] += 1
    pairs = [{"ingressTtId": k[0], "egressTtId": k[1], "pcp": k[2], "vid": k[3], "count": g[0], "min_ps": g[1],
              "max_ps": g[2], "sum_ps": g[3], "mean_ps": str(Decimal(g[3]) / Decimal(g[0]))}
             for k, g in sorted(groups.items())]
    return {"definition": "R = t12 - t1 (M2-S1): last bit received at the ingress TT's TSN port to last bit sent at the "
                          "egress TT's TSN port", "classes": classes, "pairs": pairs}


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        out = observe(argv[1:])
    except (LogError, OSError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
