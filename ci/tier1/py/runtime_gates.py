"""C-4 runtime gates on the in-session link probes (see ci/tier1/session/runtime-probe.sh).

  case <probe>                  -> prints A (the -lc++ probe links: contamination present, provenance + removal needed),
                                   B (the -lc++ probe fails exactly with 'unable to find library -lc++': clean host,
                                   nothing to remove) or INVALID (anything else: fail closed). Exit 0 for A/B, 1 otherwise.
  runpath <probe> <phase> <out> -> appends the non-store RUNPATH entries of the probe binaries (observation only;
                                   resolution through such an entry fails the positive controls)
  gates <probe> <out> <case>    -> negative control (R-3: -lc++ must fail because libc++ is unavailable) and positive
                                   controls (R-4: the default and -lstdc++ probes link and resolve libstdc++ and every
                                   other library from /nix/store). Writes <out>; exit 0 only if both pass.
"""
import os
import sys

STORE = "/nix/store/"
NEG = "unable to find library -lc++"


def _val(lines, key):
    return next((l.split(": ", 1)[1] for l in lines if l.startswith(key + ": ")), "")


def _grab(lines, prefix):
    return [l.split(": ", 1)[1] for l in lines if l.startswith(prefix + ": ")]


def negative_ok(lines):
    rc = _val(lines, "probe libcxx rc")
    return rc not in ("", "0") and any(NEG in t for t in _grab(lines, "probe libcxx trace"))


def classify(lines):
    rc = _val(lines, "probe libcxx rc")
    if rc == "0":
        return "A"
    if negative_ok(lines):
        return "B"
    return "INVALID"


def gates(lines, case):
    out = [f"c4_case: {case}",
           f"negative_libcxx_rc: {_val(lines, 'probe libcxx rc') or 'missing'}",
           f"negative_libcxx_reason: {next((t for t in _grab(lines, 'probe libcxx trace') if 'unable to find library' in t), 'none')}"]
    r3 = negative_ok(lines)
    out.append(f"r3_result: {'PASS' if r3 else 'FAIL'}")
    r4 = True
    for name in ("default", "stdcxx"):
        rc, needed = _val(lines, f"probe {name} rc"), _val(lines, f"probe {name} needed")
        resolved = _grab(lines, f"probe {name} resolved")
        std = next((r.split("=>", 1)[1].split()[0] for r in resolved if r.strip().startswith("libstdc++.so.6 =>")), "")
        unres = [r for r in resolved if "not found" in r or "error" in r]
        nonstore = [r.split("=>", 1)[1].split()[0] for r in resolved
                    if "=>" in r and r.split("=>", 1)[1].split() and not r.split("=>", 1)[1].split()[0].startswith(STORE)]
        cxx = [n for n in needed.split(",") if n.startswith(("libc++.so", "libc++abi.so"))]
        good = (rc == "0" and "libstdc++.so.6" in needed.split(",") and not cxx and not unres
                and std.startswith(STORE) and "-gcc-" in std and not nonstore)
        r4 = r4 and good
        out += [f"positive_{name}_rc: {rc or 'missing'}", f"positive_{name}_needed: {needed or 'none'}",
                f"positive_{name}_libstdcxx: {std or 'none'}", f"positive_{name}_unresolved: {len(unres)}",
                f"positive_{name}_non_store_resolutions: {', '.join(nonstore) or 'none'}",
                f"positive_{name}_result: {'PASS' if good else 'FAIL'}"]
    out.append(f"r4_result: {'PASS' if r4 else 'FAIL'}")
    return r3 and r4, out


def runpath(lines, phase, isdir=os.path.isdir):
    obs = []
    for l in lines:
        if l.startswith("probe ") and " runpath: " in l:
            name = l.split()[1]
            for d in [x for x in l.split(": ", 1)[1].split(":") if x]:
                if not d.startswith(STORE):
                    obs.append(f"{phase} probe {name}: non-store RUNPATH entry {d} exists={'yes' if isdir(d) else 'no'}")
    return obs


def main(argv):
    if len(argv) == 5 and argv[1] == "runpath":
        obs = runpath(open(argv[2]).read().splitlines(), argv[3])
        with open(argv[4], "a") as f:
            f.write("".join(o + "\n" for o in obs))
        print("\n".join(obs))
        return 0
    if len(argv) == 3 and argv[1] == "case":
        c = classify(open(argv[2]).read().splitlines())
        print(c)
        return 0 if c in ("A", "B") else 1
    if len(argv) == 5 and argv[1] == "gates" and argv[4] in ("A", "B"):
        ok, out = gates(open(argv[2]).read().splitlines(), argv[4])
        open(argv[3], "w").write("\n".join(out) + "\n")
        print("\n".join(out))
        return 0 if ok else 1
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
