"""C-4 case A provenance (the corrected E2b.3-R1 R-1 gate), as an importable module.

Establishes, fail-closed, that the libc++ actually selected by the in-session `-lc++` probe is a host library outside
/nix/store; identifies the unversioned linker entry that selected it by replaying the linker's -L search order recorded
from the driver; verifies the entry -> runtime-library relationship (symlink chain or linker-script INPUT); and records
runtime and development package ownership separately (merged-/usr aliases). Removal candidates come only from verified
development-package ownership.

Dependency injection (C5): `analyse()` takes a filesystem view and a dpkg lookup. Production (`main`) always passes the
real filesystem and the real `dpkg -S`; there is no environment variable or other override. The offline tests import this
module and pass a mocked tree and a mocked dpkg database.
"""
import os
import re
import subprocess
import sys

STORE = "/nix/store/"
DEV = re.compile(r"^libc\+\+(abi)?(-[0-9]+)?-dev(:amd64)?$")


class FS:
    """Filesystem view. root="" is the real filesystem; a non-empty root is a mocked tree (tests only)."""

    def __init__(self, root=""):
        self.root = root.rstrip("/")

    def p(self, path):
        return self.root + path

    def exists(self, path):
        return os.path.lexists(self.p(path))

    def isdir(self, path):
        return os.path.isdir(self.p(path))

    def islink(self, path):
        return os.path.islink(self.p(path))

    def readlink(self, path):
        return os.readlink(self.p(path))

    def canon(self, path):
        r = os.path.realpath(self.p(path))
        if self.root:
            rr = os.path.realpath(self.root)
            if not (r == rr or r.startswith(rr + "/")):
                raise SystemExit("mocked filesystem escape")
            r = r[len(rr):] or "/"
        return r

    def read(self, path, n):
        with open(self.p(path), "rb") as f:
            return f.read(n)


def dpkg_search(path):
    """Real dpkg ownership lookup: returns (hit, stdout)."""
    r = subprocess.run(["dpkg", "-S", path], capture_output=True, text=True)
    return r.returncode == 0, r.stdout


def base_kind(p):
    b = os.path.basename(p)
    for k, rx in (("libc++", r"^libc\+\+\.so(\.[0-9][0-9.]*)?$"), ("libc++abi", r"^libc\+\+abi\.so(\.[0-9][0-9.]*)?$"),
                  ("libunwind", r"^libunwind\.so(\.[0-9][0-9.]*)?$")):
        if re.match(rx, b):
            return k
    return None


def analyse(lines, fs, dpkg):
    """Returns (ok, out_lines, problems, candidates)."""
    queries = []

    def val(key):
        return next((l.split(": ", 1)[1] for l in lines if l.startswith(key + ": ")), "")

    def chain(p):
        hops, cur, seen = [p], p, set()
        while fs.islink(cur) and cur not in seen:
            seen.add(cur)
            t = fs.readlink(cur)
            cur = os.path.normpath(t if t.startswith("/") else os.path.join(os.path.dirname(cur), t))
            hops.append(cur)
        return hops

    def aliases(p, follow=True):
        if follow:
            out = [p] + ([fs.canon(p)] if fs.exists(p) else [])
        else:
            d = os.path.dirname(p)
            out = [p] + ([os.path.join(fs.canon(d), os.path.basename(p))] if fs.exists(d) else [])
        for x in list(out):
            for a, b in (("/lib/", "/usr/lib/"), ("/lib64/", "/usr/lib64/"), ("/bin/", "/usr/bin/"), ("/sbin/", "/usr/sbin/")):
                if x.startswith(a):
                    out.append(b + x[len(a):])
                elif x.startswith(b):
                    out.append(a + x[len(b):])
        return list(dict.fromkeys(out))

    def owners_of(p, follow=True):
        found = set()
        for a in aliases(p, follow):
            hit, stdout = dpkg(a)
            queries.append(f"{a} -> {'hit' if hit else 'miss'}")
            if hit:
                for line in stdout.splitlines():
                    if line.startswith("diversion ") or ": " not in line:
                        continue
                    found.update(x.strip() for x in line.rsplit(": ", 1)[0].split(","))
        return sorted(found)

    def kind(p):
        try:
            head = fs.read(fs.canon(p), 4096)
        except OSError:
            return "missing", []
        if head.startswith(b"\x7fELF"):
            return "elf", []
        text = head.decode("utf-8", "replace")
        refs = []
        for m in re.finditer(r"\b(?:INPUT|GROUP)\s*\(([^)]*(?:\([^)]*\)[^)]*)*)\)", text):
            refs += [t for t in re.split(r"[\s,()]+", m.group(1)) if t and t != "AS_NEEDED"]
        return ("linker-script" if refs else "other"), refs

    rc = val("probe libcxx rc")
    driver_dirs = [l.split(" -L", 1)[1].strip() for l in lines if l.startswith("driver-L -L")]
    trace_paths = []
    for l in lines:
        if l.startswith("probe libcxx trace: "):
            trace_paths += re.findall(r"(/[^\s:()'\"]+)", l.split("trace: ", 1)[1])
    trace_paths = list(dict.fromkeys(trace_paths))
    traced = {k: [p for p in trace_paths if base_kind(p) == k] for k in ("libc++", "libc++abi", "libunwind")}
    unrelated_host = [p for p in trace_paths if base_kind(p) is None and not p.startswith(STORE)]

    def linker_entry(name):
        for d in driver_dirs:
            p = os.path.join(d, f"lib{name}.so")
            if fs.exists(p):
                return p
        return ""

    def resolve_ref(ref, entry, final):
        if ref.startswith("/"):
            return ref if fs.exists(ref) else ""
        if ref.startswith("-l"):
            return linker_entry(ref[2:])
        for d in [os.path.dirname(entry), os.path.dirname(final)] + driver_dirs:
            p = os.path.join(d, ref)
            if fs.exists(p):
                return p
        return ""

    problems = []
    selected = traced["libc++"][0] if traced["libc++"] else ""
    if rc != "0":
        problems.append(f"libc++ probe did not link (rc={rc or 'missing'})")
    if not selected:
        problems.append("no libc++ library in the linker trace")
    sel_canon = fs.canon(selected) if selected and fs.exists(selected) else ""
    if selected and not sel_canon:
        problems.append("traced libc++ library not present on this filesystem")
    outside = bool(selected) and not selected.startswith(STORE) and bool(sel_canon) and not sel_canon.startswith(STORE)
    if selected and not outside:
        problems.append("selected libc++ is not outside /nix/store")

    entry = selected if selected and os.path.basename(selected) == "libc++.so" else (linker_entry("c++") if selected else "")
    hops = chain(entry) if entry else []
    final = fs.canon(entry) if entry and fs.exists(entry) else ""
    ekind, refs = kind(entry) if entry else ("missing", [])
    related, via = False, ""
    if entry and sel_canon:
        if ekind == "elf":
            related, via = final == sel_canon, "symlink chain to the selected ELF"
        elif ekind == "linker-script":
            for ref in refs:
                r = resolve_ref(ref, entry, final)
                if r and base_kind(r) == "libc++" and fs.canon(r) == sel_canon:
                    related, via = True, f"linker-script INPUT '{ref}' -> {r}"
                    break
    if selected and not entry:
        problems.append("no unversioned libc++.so linker entry found along the driver -L search path")
    if entry and (entry.startswith(STORE) or final.startswith(STORE)):
        problems.append("unversioned linker entry is inside /nix/store")
    if entry and not related:
        problems.append("unversioned linker entry does not lead to the traced libc++ library")

    runtime_query = sel_canon if selected and os.path.basename(selected) == "libc++.so" else selected
    runtime_owners = owners_of(runtime_query) if sel_canon else []
    dev_paths = list(dict.fromkeys([h for h in hops if os.path.basename(h) == "libc++.so"] + ([final] if ekind == "linker-script" else [])))
    dev_owners = sorted({o for h in dev_paths for o in owners_of(h, follow=False)}) if entry else []
    if sel_canon and not runtime_owners:
        problems.append("runtime library ownership not established")
    if entry and not dev_owners:
        problems.append("development (linker-entry) ownership not established")
    bad_dev = [o for o in dev_owners if not DEV.match(o)]
    if bad_dev:
        problems.append(f"unexpected development owners: {bad_dev}")
    overlap = sorted(set(dev_owners) & set(runtime_owners))
    if overlap:
        problems.append(f"development owners also own the runtime library: {overlap}")

    abi_entry, abi_dev, abi_related = "", [], False
    if related and any(r in ("-lc++abi",) or os.path.basename(r).startswith("libc++abi") for r in refs) and traced["libc++abi"]:
        t = traced["libc++abi"][0]
        abi_entry = t if os.path.basename(t) == "libc++abi.so" else linker_entry("c++abi")
        if abi_entry and not abi_entry.startswith(STORE) and fs.exists(abi_entry) and not fs.canon(abi_entry).startswith(STORE):
            abi_related = True
            ah = chain(abi_entry)
            ak, _ = kind(abi_entry)
            apaths = [h for h in ah if os.path.basename(h) == "libc++abi.so"] + ([fs.canon(abi_entry)] if ak == "linker-script" else [])
            abi_dev = sorted({o for h in dict.fromkeys(apaths) for o in owners_of(h, follow=False)})
    unw = traced["libunwind"][0] if traced["libunwind"] else ""
    unw_owners = owners_of(unw, follow=False) if unw and fs.exists(unw) else []

    candidates = list(dev_owners) + [o for o in abi_dev if DEV.match(o) and o not in runtime_owners]
    ok = not problems
    out = [f"libcxx_probe_rc: {rc or 'missing'}",
           f"trace_paths: {', '.join(trace_paths) or 'none'}",
           f"selected_libcxx_runtime: {selected or 'none'}",
           f"selected_libcxx_canonical: {sel_canon or 'none'}",
           f"selected_outside_nix_store: {'yes' if outside else 'no'}",
           f"driver_search_dirs: {len(driver_dirs)}",
           f"unversioned_linker_entry: {entry or 'none'}",
           f"unversioned_entry_chain: {' -> '.join(hops) or 'none'}",
           f"unversioned_entry_final: {final or 'none'}",
           f"unversioned_entry_kind: {ekind}",
           f"development_paths: {', '.join(dev_paths) if entry else 'none'}",
           f"unversioned_entry_inputs: {' '.join(refs) or 'none'}",
           f"entry_relationship: {'verified (' + via + ')' if related else 'NOT verified'}",
           f"runtime_owners: {', '.join(runtime_owners) or 'none'}",
           f"development_owners: {', '.join(dev_owners) or 'none'}",
           f"libcxxabi_traced: {', '.join(traced['libc++abi']) or 'none'}",
           f"libcxxabi_dev_entry: {abi_entry or 'none'}",
           f"libcxxabi_associated: {'yes' if abi_related else 'no'}",
           f"libcxxabi_development_owners: {', '.join(abi_dev) or 'none'}",
           f"libunwind_traced: {unw or 'none'} (recorded only; not a removal candidate)",
           f"libunwind_owners: {', '.join(unw_owners) or 'none'}",
           f"unrelated_host_paths_in_trace: {', '.join(unrelated_host) or 'none'}"]
    if ekind == "linker-script":
        try:
            out.append("linker_script: " + fs.read(final, 2048).decode("utf-8").strip().replace("\n", " | "))
        except (OSError, UnicodeDecodeError):
            out.append("linker_script: <unreadable>")
    out += [f"dpkg_query: {q}" for q in queries]
    out += [f"problem: {p}" for p in problems]
    cands = list(dict.fromkeys(candidates)) if ok else []
    out += [f"removal_candidate: {c}" for c in cands]
    out.append(f"r1_result: {'PASS' if ok else 'FAIL'}")
    return ok, out, problems, cands


def main(argv):
    """usage: provenance.py <runtime-probe-before.txt> <host-libcxx.txt out>. Real filesystem and dpkg only."""
    if len(argv) != 3:
        raise SystemExit("usage: provenance.py <probe> <out>")
    lines = open(argv[1]).read().splitlines()
    ok, out, problems, _ = analyse(lines, FS(""), dpkg_search)
    open(argv[2], "w").write("\n".join(out) + "\n")
    print("\n".join(out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
