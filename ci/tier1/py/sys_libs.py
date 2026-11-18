"""C-5 SYS_LIBS gate (D-3): the hosted OMNeT++ Makefile.inc SYS_LIBS must contain the exact token -lstdc++, must not
contain -lc++, and its ordered token sequence (whitespace collapsed) must equal the recovered VM reference.

usage: sys_libs.py <Makefile.inc> <VM SYS_LIBS> <out>; exit 0 only on PASS."""
import re
import sys


def field(text, name):
    m = re.search(rf"^{name}[ \t]*=[ \t]*(.*)$", text, re.M)
    return m.group(1).strip() if m else None


def evaluate(hosted, vm):
    ht, vt = (hosted or "").split(), vm.split()
    has_std, has_cxx = "-lstdc++" in ht, "-lc++" in ht
    ordered = hosted is not None and ht == vt
    ok = hosted is not None and has_std and not has_cxx and ordered
    first = next((i for i, (a, b) in enumerate(zip(ht, vt)) if a != b), min(len(ht), len(vt)) if len(ht) != len(vt) else None)
    out = [f"hosted_SYS_LIBS: {hosted if hosted is not None else '<absent>'}",
           f"vm_SYS_LIBS: {vm}",
           f"hosted_tokens: {len(ht)}",
           f"vm_tokens: {len(vt)}",
           f"has_lstdcxx_token: {'yes' if has_std else 'no'}",
           f"has_lcxx_token: {'yes' if has_cxx else 'no'}",
           f"ordered_token_match_vm: {'yes' if ordered else 'no'}",
           f"exact_string_match_vm: {'yes' if hosted == vm else 'no'}",
           f"first_differing_token_index: {first if first is not None else 'none'}",
           f"tokens_only_hosted: {' '.join(t for t in dict.fromkeys(ht) if t not in vt) or 'none'}",
           f"tokens_only_vm: {' '.join(t for t in dict.fromkeys(vt) if t not in ht) or 'none'}",
           f"r5_result: {'PASS' if ok else 'FAIL'}"]
    return ok, out


def main(argv):
    if len(argv) != 4:
        raise SystemExit(__doc__)
    text = open(argv[1]).read()
    ok, out = evaluate(field(text, "SYS_LIBS"), argv[2])
    li = field(text, "LIBS")
    out.insert(1, f"hosted_LIBS: {li if li is not None else '<absent>'}")
    open(argv[3], "w").write("\n".join(out) + "\n")
    print("\n".join(out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
