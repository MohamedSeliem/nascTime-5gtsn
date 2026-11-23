"""WP-A1 validation (runbook revision 3, phase H-3): fail-closed extraction of ONE release archive into the extraction
root X, retaining every member byte for byte.

usage: python3 -I -B extract_checked.py <archive> <X> <members record (must not exist)>

Accepted formats, decided by the file name: .tar, .tar.gz / .tgz, .tar.xz, .tar.bz2 (tarfile) and .zip (zipfile). Any
other name is refused (exit 2).

Layout rule. Every member path, after removing one optional leading "mnt/nasctime-results/" (the original prefix stored
relatively), must be one of the evidence seals (s5-smoke-1-evidence.sha256, s5-n2-1-evidence.sha256,
a2-nack-1-evidence.sha256) or lie under s5-smoke-1/, s5-n2-1/ or a2-nack-1/. The optional prefix must be used by all
members of the archive or by none. X/<rel> then holds what was /mnt/nasctime-results/<rel>.

Refused (exit 1, the archive is not extracted further; partial output is left as found for the record):
absolute names, "..", empty or "." components, backslashes, NUL, duplicate members, symbolic or hard links, devices,
FIFOs, members outside the layout, a destination that already exists (members of different archives never overwrite
each other), a size or zip CRC mismatch, and a member whose written bytes do not hash to what was read.
Nothing is modified in the archive; extracted files keep the member's bytes and modification time; X is made
read-only by the caller after all archives are extracted.
"""
import calendar
import hashlib
import os
import stat
import sys
import tarfile
import zipfile

PREFIX = "mnt/nasctime-results/"
TOPS = ("s5-smoke-1/", "s5-n2-1/", "a2-nack-1/")
SEALS = ("s5-smoke-1-evidence.sha256", "s5-n2-1-evidence.sha256", "a2-nack-1-evidence.sha256")


class Refused(Exception):
    pass


def clean(name):
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        raise Refused(f"member name {name!r} is absolute, empty or contains NUL / backslash")
    parts = name.rstrip("/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise Refused(f"member name {name!r} has an empty, '.' or '..' component")
    return "/".join(parts)


def layout(names):
    """the stripped relative paths; all members use the optional prefix or none do"""
    with_p = [n.startswith(PREFIX) for n in names]
    if any(with_p) and not all(with_p):
        raise Refused("some members carry 'mnt/nasctime-results/' and some do not")
    out = []
    for n in names:
        rel = n[len(PREFIX):] if all(with_p) and with_p else n
        out.append(rel)
    return out


def allowed(rel, is_dir):
    if rel in SEALS and not is_dir:
        return True
    if any(rel.startswith(t) for t in TOPS):
        return True
    return is_dir and (rel + "/") in TOPS


def members(archive):
    """(name, kind, size, mtime, opener) for every member; kind is 'f' or 'd'; anything else is refused"""
    a = os.path.basename(archive)
    if a.endswith(".zip"):
        z = zipfile.ZipFile(archive)
        out = []
        for i in z.infolist():
            mode = (i.external_attr >> 16) & 0o170000
            if mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise Refused(f"{i.filename!r}: not a regular file or directory (mode {oct(mode)})")
            kind = "d" if i.is_dir() else "f"
            mt = calendar.timegm(i.date_time + (0, 0, -1))
            out.append((i.filename, kind, i.file_size, mt, (lambda i=i: z.open(i))))
        return out
    if a.endswith((".tar", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2")):
        t = tarfile.open(archive, "r:*")
        out = []
        for m in t.getmembers():
            if m.isreg():
                out.append((m.name, "f", m.size, int(m.mtime), (lambda m=m: t.extractfile(m))))
            elif m.isdir():
                out.append((m.name, "d", 0, int(m.mtime), None))
            else:
                raise Refused(f"{m.name!r}: not a regular file or directory (tar type {m.type!r})")
        return out
    raise Refused(f"unknown archive format: {a}")


def main(argv):
    if len(argv) != 4:
        print(__doc__)
        return 2
    archive, X, rec = argv[1], argv[2], argv[3]
    if os.path.lexists(rec):
        print(f"REFUSED: members record {rec} exists")
        return 1
    if not os.path.isdir(X) or os.path.islink(X):
        print(f"REFUSED: X {X} is not an existing directory")
        return 1
    try:
        ms = members(archive)
    except Refused as ex:
        print(f"REFUSED: {ex}")
        return 2 if str(ex).startswith("unknown archive format") else 1
    try:
        names = [clean(m[0]) for m in ms]
        # the directory entries of the stored prefix itself carry no evidence: dropped before the layout rule
        keep = [i for i, (n, m) in enumerate(zip(names, ms)) if not (m[1] == "d" and n in ("mnt", PREFIX.rstrip("/")))]
        ms, names = [ms[i] for i in keep], [names[i] for i in keep]
        if len(set(names)) != len(names):
            raise Refused("duplicate member names")
        rels = layout(names)
        for (name, kind, *_), rel in zip(ms, rels):
            if not allowed(rel, kind == "d"):
                raise Refused(f"member {name!r} is outside the evidence layout")
    except Refused as ex:
        print(f"REFUSED (nothing extracted): {ex}")
        return 1
    with open(rec, "x", encoding="utf-8") as out:
        out.write(f"# archive {os.path.basename(archive)}; members {len(ms)}\n")
        for (name, kind, size, mtime, opener), rel in zip(ms, rels):
            dest = os.path.join(X, rel)
            if kind == "d":
                os.makedirs(dest, exist_ok=True)
                if os.path.islink(dest):
                    print(f"REFUSED: {dest} is a symbolic link")
                    return 1
                continue
            parent = os.path.dirname(dest)
            os.makedirs(parent, exist_ok=True)
            if os.path.realpath(parent) != os.path.join(os.path.realpath(X), os.path.dirname(rel)).rstrip("/"):
                print(f"REFUSED: {rel}: its directory resolves outside X")
                return 1
            h, n = hashlib.sha256(), 0
            try:
                with opener() as src, open(dest, "xb") as dst:      # 'x': an existing file is never overwritten
                    for b in iter(lambda: src.read(1 << 20), b""):
                        h.update(b)
                        n += len(b)
                        dst.write(b)
            except FileExistsError:
                print(f"REFUSED: {rel} already exists in X (member of an earlier archive?)")
                return 1
            except zipfile.BadZipFile as ex:
                print(f"REFUSED: {rel}: {ex}")
                return 1
            if n != size:
                print(f"REFUSED: {rel}: {n} bytes read, member size {size}")
                return 1
            w = hashlib.sha256()
            with open(dest, "rb") as fh:
                for b in iter(lambda: fh.read(1 << 20), b""):
                    w.update(b)
            if w.hexdigest() != h.hexdigest():
                print(f"REFUSED: {rel}: written bytes differ from the member")
                return 1
            os.utime(dest, (mtime, mtime))
            out.write(f"{h.hexdigest()}  {n}  {rel}\n")
    print(f"extracted {sum(1 for m in ms if m[1] == 'f')} files of {os.path.basename(archive)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
