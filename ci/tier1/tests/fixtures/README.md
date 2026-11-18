# Tier-1 test fixtures

`e2b3-runtime-probe-before.txt` is **real hosted evidence**, not synthetic data. It is the unmodified
`runtime-probe-before.txt` produced in E2b.3 by the in-session link probe (`ci/tier1/session/runtime-probe.sh`, identical
logic) on a GitHub-hosted `ubuntu-22.04` runner. It was printed to the public log of job 134465683528 (workflow run of
commit `a24d797` on branch `wp-e2/e2b3-runtime-consistency`).

- sha256: `b45f58810ef7cd64749cd7d1b69971723a8e0255a6ca8e47e5ad6943db3265f2` (checked by the self-tests)
- content: the clang/lld search directories, the driver's `-L` order, and the linker traces, NEEDED/RUNPATH entries and
  loader resolutions of three minimal probe programs. It contains only public runner paths (`/home/runner/...`) and
  `/nix/store` paths: no credentials, no private data, no project results.
- use: replayed against mocked filesystem trees and dpkg databases by the C-4 provenance regression tests. What is mocked
  is stated in each test.
