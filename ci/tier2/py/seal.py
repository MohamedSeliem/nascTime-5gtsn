"""Raw-evidence sealing (E-8). `create` writes a SHA-256 manifest (sha256, size in bytes, path) of every file under the
raw directory and makes the tree read-only, BEFORE any evaluation; `verify` recomputes it afterwards and fails on any
changed, added or removed file. Symbolic links and special files are refused.
usage: seal.py create <dir> <manifest> <out kv>   |   seal.py verify <dir> <manifest> <out kv>"""
import hashlib
import os
import stat
import sys


def listing(root):
    entries, bad = [], []
    for d, dirs, files in os.walk(root):
        dirs.sort()
        for n in sorted(dirs + files):
            p = os.path.join(d, n)
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                bad.append(os.path.relpath(p, root))
        for n in sorted(files):
            p = os.path.join(d, n)
            if stat.S_ISREG(os.lstat(p).st_mode):
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    for b in iter(lambda: f.read(1 << 20), b""):
                        h.update(b)
                entries.append((h.hexdigest(), os.path.getsize(p), "./" + os.path.relpath(p, root)))
    return sorted(entries, key=lambda e: e[2]), bad


def fmt(entries):
    return "".join(f"{h}  {s}  {p}\n" for h, s, p in entries)


def create(root, manifest, out):
    if not os.path.isdir(root):
        open(out, "w").write("seal_result: FAIL\nproblem: raw directory missing\n")
        return 1
    entries, bad = listing(root)
    text = fmt(entries)
    open(manifest, "w").write(text)
    for d, dirs, files in os.walk(root, topdown=False):
        for n in files:
            os.chmod(os.path.join(d, n), 0o444)
        os.chmod(d, 0o555)
    ok = bool(entries) and not bad
    open(out, "w").write(f"manifest_sha256: {hashlib.sha256(text.encode()).hexdigest()}\nfiles: {len(entries)}\n"
                         f"total_bytes: {sum(s for _, s, _ in entries)}\nspecial_or_symlink: {bad or 'none'}\n"
                         f"read_only: yes\nseal_result: {'PASS' if ok else 'FAIL'}\n")
    return 0 if ok else 1


def verify(root, manifest, out):
    try:
        want = open(manifest).read()
    except OSError:
        open(out, "w").write("verify_result: FAIL\nproblem: manifest missing\n")
        return 1
    entries, bad = listing(root) if os.path.isdir(root) else ([], ["<raw directory missing>"])
    got = fmt(entries)
    w = {l.split("  ", 2)[2]: l for l in want.splitlines() if l}
    g = {l.split("  ", 2)[2]: l for l in got.splitlines() if l}
    changed = sorted(p for p in w if p in g and w[p] != g[p])
    removed, added = sorted(set(w) - set(g)), sorted(set(g) - set(w))
    ok = got == want and not bad
    open(out, "w").write(f"manifest_sha256: {hashlib.sha256(want.encode()).hexdigest()}\nchanged: {changed or 'none'}\n"
                         f"removed: {removed or 'none'}\nadded: {added or 'none'}\nspecial_or_symlink: {bad or 'none'}\n"
                         f"verify_result: {'PASS' if ok else 'FAIL'}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] not in ("create", "verify"):
        raise SystemExit(__doc__)
    sys.exit((create if sys.argv[1] == "create" else verify)(*sys.argv[2:]))
