"""C-2: opp_env workspace administration files before/after realisation. Nothing may change or disappear; only the two
generated flake.nix files may be added. usage: admin_diff.py <before.sha256> <after.sha256> <out>"""
import sys


def load(p):
    return {l.split(maxsplit=1)[1].strip(): l.split()[0] for l in open(p) if l.strip()}


before, after = load(sys.argv[1]), load(sys.argv[2])
changed = sorted(p for p in before if p in after and before[p] != after[p])
removed = sorted(p for p in before if p not in after)
added = sorted(p for p in after if p not in before)
ok = not changed and not removed and set(added) <= {"./22.11/flake.nix", "./26.05/flake.nix"}
with open(sys.argv[3], "w") as f:
    f.write(f"admin_files_added: {', '.join(added) or 'none'}\nadmin_files_changed: {', '.join(changed) or 'none'}\n"
            f"admin_files_removed: {', '.join(removed) or 'none'}\nadmin_check: {'PASS' if ok else 'FAIL'}\n")
print(open(sys.argv[3]).read())
sys.exit(0 if ok else 1)
