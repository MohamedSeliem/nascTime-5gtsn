#!/usr/bin/env bash
# extract_checked.py on crafted archives (runbook rev. 4, 5 and 14). TEST ONLY: dummy archives; no evidence.
set -u -o pipefail
T_DIR=$(cd "$(dirname "$0")" && pwd); EX="$T_DIR/../extract_checked.py"
PASSED=0; FAILED=0
check() { if eval "$2"; then echo "PASS  $1"; PASSED=$((PASSED + 1)); else echo "FAIL  $1  [$2]"; FAILED=$((FAILED + 1)); fi; }
B=$(mktemp -d "${TMPDIR:-/tmp}/wpa1-ext.XXXXXX"); cd "$B" || exit 2
python3 -I - <<'EOF'
import tarfile, zipfile, io
def tar(name, members, mode="w"):
    with tarfile.open(name, mode) as t:
        for n, kind, data in members:
            i = tarfile.TarInfo(n); i.mtime = 1700000000
            if kind == "f": i.size = len(data); t.addfile(i, io.BytesIO(data))
            elif kind == "d": i.type = tarfile.DIRTYPE; t.addfile(i)
            elif kind == "l": i.type = tarfile.SYMTYPE; i.linkname = data; t.addfile(i)
            elif kind == "h": i.type = tarfile.LNKTYPE; i.linkname = data; t.addfile(i)
tar("ok-plain.tar.gz", [("s5-smoke-1", "d", b""), ("s5-smoke-1/m2/a.txt", "f", b"A"), ("s5-smoke-1-evidence.sha256", "f", b"S")], "w:gz")
tar("ok-prefixed.tar", [("mnt", "d", b""), ("mnt/nasctime-results", "d", b""), ("mnt/nasctime-results/a2-nack-1/runs/x.log.gz", "f", b"L"),
                        ("mnt/nasctime-results/a2-nack-1-evidence.sha256", "f", b"E")])
tar("bad-traversal.tar", [("s5-n2-1/../../etc/x", "f", b"x")])
tar("bad-abs.tar", [("/mnt/nasctime-results/s5-n2-1/x", "f", b"x")])
tar("bad-symlink.tar", [("s5-n2-1/l", "l", "/etc/passwd")])
tar("bad-hardlink.tar", [("s5-n2-1/h", "h", "s5-n2-1/x")])
tar("bad-outside.tar", [("other/x", "f", b"x")])
tar("bad-mixed.tar", [("mnt/nasctime-results/s5-n2-1/a", "f", b"a"), ("s5-n2-1/b", "f", b"b")])
tar("bad-dup.tar", [("s5-n2-1/d", "f", b"1"), ("s5-n2-1/d", "f", b"2")])
tar("overwrite.tar", [("s5-smoke-1/m2/a.txt", "f", b"DIFFERENT")])
with zipfile.ZipFile("ok.zip", "w") as z: z.writestr("s5-n2-1/m2/r/0.sca", b"SCA"); z.writestr("s5-n2-1-evidence.sha256", b"E2")
with zipfile.ZipFile("bad-zip-link.zip", "w") as z:
    i = zipfile.ZipInfo("s5-n2-1/link"); i.external_attr = (0o120777 << 16); z.writestr(i, "/etc/passwd")
open("x.rar", "wb").write(b"r")
EOF
mkdir X
x() { python3 -I -B "$EX" "$B/$1" "$B/X" "$B/rec-$1.txt" > "$B/out-$1.txt" 2>&1; echo $?; }
check "EX-1 tar.gz extracted"                  '[ "$(x ok-plain.tar.gz)" = 0 ] && [ "$(cat X/s5-smoke-1/m2/a.txt)" = A ]'
check "EX-2 stored prefix stripped"            '[ "$(x ok-prefixed.tar)" = 0 ] && [ -f X/a2-nack-1/runs/x.log.gz ] && [ ! -e X/mnt ]'
check "EX-3 zip extracted"                     '[ "$(x ok.zip)" = 0 ] && [ "$(cat X/s5-n2-1/m2/r/0.sca)" = SCA ]'
check "EX-4 member record has sha256 and size" 'grep -q "^$(printf A | sha256sum | cut -d" " -f1)  1  s5-smoke-1/m2/a.txt$" rec-ok-plain.tar.gz.txt'
check "EX-5 mtime kept"                        '[ "$(stat -c %Y X/s5-smoke-1/m2/a.txt)" = 1700000000 ]'
for a in bad-traversal.tar bad-abs.tar bad-symlink.tar bad-hardlink.tar bad-outside.tar bad-mixed.tar bad-dup.tar bad-zip-link.zip; do
  check "EX-r refused: $a" '[ "$(x '"$a"')" = 1 ]'
done
check "EX-6 a member never overwrites an existing file" '[ "$(x overwrite.tar)" = 1 ] && [ "$(cat X/s5-smoke-1/m2/a.txt)" = A ]'
check "EX-7 unknown format refused (exit 2)"  '[ "$(x x.rar)" = 2 ]'
check "EX-8 nothing escaped X"                '[ ! -e "$B/etc" ] && [ -z "$(find X -type l)" ]'
cd /; rm -rf "$B"
echo "test-extract: $PASSED PASS, $FAILED FAIL"; [ "$FAILED" -eq 0 ]
