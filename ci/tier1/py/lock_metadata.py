"""C-2: `nix flake metadata` of the workspace 26.05 flake (lock update forbidden) must report the approved revisions.
usage: lock_metadata.py <metadata json> <out>"""
import json
import sys

nodes = json.load(open(sys.argv[1]))["locks"]["nodes"]
got = {k: nodes[k]["locked"]["rev"] for k in ("nixpkgs", "flake-utils", "systems")}
want = {"nixpkgs": "8c50a710ddca43d7a530fb805ad55bde8d0141c5",
        "flake-utils": "b7a79d3fea1e214f6d668d521cecec0c01e26544",
        "systems": "da67096a3b9bf56a91d16901293e51ba5b49a27e"}
with open(sys.argv[2], "w") as f:
    for k in want:
        f.write(f"locked_rev {k}: {got[k]}\n")
    f.write(f"flake_metadata_no_update_check: {'PASS' if got == want else 'FAIL'}\n")
assert got == want, got
print("flake metadata (lock update forbidden): locked revisions equal the approved lock")
