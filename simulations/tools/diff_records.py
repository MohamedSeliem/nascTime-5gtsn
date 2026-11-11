#!/usr/bin/env python3
"""M2-R181 plan §3.3: list every verdict change and every changed number between two record trees.

    diff_records.py <old root> <new root> <relative path> [<relative path> ...]   -> stdout

Lines are aligned by their text with every number replaced by '#' and the verdict words PASS / FAIL normalised
(difflib on the line sequence), so a row whose numbers or verdict changed is still matched to its old version.
For every matched line: the verdict words (old -> new) and each number that changed (old -> new). Unmatched lines
are listed as removed / added. Files missing on either side are reported. Nothing is interpreted.
"""
import difflib
import os
import re
import sys

NUM = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
VERD = re.compile(r"\b(PASS|FAIL)\b")


def key(line):
    return re.sub(r"\s+", " ", VERD.sub("V", NUM.sub("#", line))).strip()


def diff_file(old, new, rel):
    out = []
    a = open(old, errors="replace").read().split("\n") if os.path.exists(old) else None
    b = open(new, errors="replace").read().split("\n") if os.path.exists(new) else None
    if a is None or b is None:
        return [f"## {rel}: {'missing in old' if a is None else ''}{' ' if a is None and b is None else ''}{'missing in new' if b is None else ''}"], 0, 0
    ka, kb = [key(x) for x in a], [key(x) for x in b]
    sm = difflib.SequenceMatcher(None, ka, kb, autojunk=False)
    vchg = nchg = 0
    body = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                if a[i] == b[j]:
                    continue
                va, vb = VERD.findall(a[i]), VERD.findall(b[j])
                na, nb = NUM.findall(a[i]), NUM.findall(b[j])
                label = re.sub(r"\s+", " ", a[i]).strip()[:110]
                parts = []
                if va != vb:
                    vchg += 1
                    parts.append(f"VERDICT {'/'.join(va) or '-'} -> {'/'.join(vb) or '-'}")
                ch = [f"{x} -> {y}" for x, y in zip(na, nb) if x != y]
                if ch:
                    nchg += 1
                    parts.append("numbers: " + "; ".join(ch[:40]) + (f"; ... ({len(ch)} changed)" if len(ch) > 40 else ""))
                body.append(f"- line {i + 1}/{j + 1} `{label}`: " + " | ".join(parts))
        else:
            for i in range(i1, i2):
                body.append(f"- removed line {i + 1}: `{re.sub(r'[ ]+', ' ', a[i])[:160]}`")
            for j in range(j1, j2):
                body.append(f"- added line {j + 1}: `{re.sub(r'[ ]+', ' ', b[j])[:160]}`")
            vchg += sum(1 for j in range(j1, j2) if VERD.search(b[j]))
    out.append(f"## {rel}: {vchg} verdict-bearing changes, {nchg} lines with changed numbers")
    return out + body, vchg, nchg


def main():
    old, new, rels = sys.argv[1], sys.argv[2], sys.argv[3:]
    print(f"# Record diff\n\nold: {old}\nnew: {new}\n")
    tv = tn = 0
    for rel in rels:
        lines, v, n = diff_file(os.path.join(old, rel), os.path.join(new, rel), rel)
        tv += v
        tn += n
        print("\n".join(lines) + "\n")
    print(f"TOTAL: {tv} verdict-bearing changes, {tn} lines with changed numbers, {len(rels)} files")


if __name__ == "__main__":
    main()
