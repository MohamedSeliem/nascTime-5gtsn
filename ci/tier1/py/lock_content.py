import json, sys
n = json.load(open(sys.argv[1]))["nodes"]
want = {
    "nixpkgs": ("NixOS", "nixpkgs", "8c50a710ddca43d7a530fb805ad55bde8d0141c5",
                "sha256-md0zn0RnwNvPyASas1yG5YUuwQ4ALA6ucL50l0DvqCo="),
    "flake-utils": ("numtide", "flake-utils", "b7a79d3fea1e214f6d668d521cecec0c01e26544",
                    "sha256-Zf/xfQEAasnwnmEfHqW/4hjDE/s44yn2hD4RuVIZRjA="),
    "systems": ("nix-systems", "default", "da67096a3b9bf56a91d16901293e51ba5b49a27e",
                "sha256-Vy1rq5AaRuLzOxct8nz4T6wlgyUR7zLU309k9mBC768="),
}
for k, (owner, repo, rev, nar) in want.items():
    l = n[k]["locked"]
    assert (l["owner"], l["repo"], l["rev"], l["narHash"]) == (owner, repo, rev, nar), k
assert n["nixpkgs"]["original"] == {"id": "nixpkgs", "ref": "26.05", "type": "indirect"}
print("lock content: nixpkgs, flake-utils and systems as approved")
