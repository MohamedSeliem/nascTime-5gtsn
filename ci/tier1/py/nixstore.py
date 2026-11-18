import json, re, sys
src, dst, status = sys.argv[1:4]
try:
    if status != "ok":
        raise RuntimeError("nix path-info failed")
    data = json.load(open(src))
    items = list(data.items()) if isinstance(data, dict) else [(d.get("path"), d) for d in data]
    if not items:
        raise RuntimeError("empty path-info")
except Exception as e:
    open(dst, "w").write(f"path_info: NOT AVAILABLE ({type(e).__name__})\n"); sys.exit(0)
n = nar = 0; local = []
for path, info in items:
    info = info or {}
    n += 1; nar += info.get("narSize", 0) or 0
    if info.get("ultimate"):
        local.append(path)
with open(dst, "w") as f:
    f.write(f"path_info: AVAILABLE\nstore_paths: {n}\nstore_nar_bytes: {nar}\nlocally_built_or_added: {len(local)}\n")
    for p in sorted(local):
        name = p.split("-", 1)[1] if "-" in p else p
        if name == "user-environment":
            tag = "expected-profile"     # Nix profile generation (installer / nix profile), not a package build
        elif name.endswith("-env"):
            tag = "expected-devshell"    # nix develop environment capture
        elif name.endswith("-source") or name == "source":
            tag = "expected-source"      # fetched flake inputs
        elif re.search(r"(omnetpp|inet|simu5g|nasctime)", name, re.I):
            tag = "FRAMEWORK-BUILD"
        else:
            tag = "LOCAL-PACKAGE-BUILD"  # a dependency package compiled locally (binary-cache miss)
        f.write(f"local {tag}: {name}\n")
