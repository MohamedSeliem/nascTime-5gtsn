# M2B-1 — TSN AF compiler compatibility report

**Status: revised at step 145 (corrections C1 – C3), for independent review.** The baseline is `m2/continuation` at `7bb0e3a7145602ae556239c8667362203d9294b5`, on branch `m2b/tsnaf-compiler`. The interface is `docs/migration/m2b-scfg-interface.md`.

**Level and scope:**
- level 2 only;
- no simulation was run and no private evidence was used;
- the accepted generators and their outputs are unchanged.

## 1. Regression references (committed, accepted, never written)

| File | Generator | sha256 | Generator `check` on this branch |
|---|---|---|---|
| `simulations/m2/m2s72.ini` | `tools/m2s72_gen.py` | `dfc8a7f7bb7cd1632c335c169cdbd3535e4e90a14b0d04882bb07b406aaf5505` | IDENTICAL |
| `simulations/m2/m2s72s5.ini` | `tools/m2s72s5_gen.py` | `e563c489852db4cac7ad8562c97373e2379c8bd4029c7f1ebb9d2ace2ff96903` | IDENTICAL |

## 2. What the compiler must reproduce, and the canonical extraction

In both files the bearer configuration consists of exactly four `BearerConfigurator` keys, and they appear only in two kinds of generated section:

| Section | Keys |
|---|---|
| `M2S72B-<src>`, the source base | `dlQfiRules`, `drbProfiles` (shared), copied from the source |
| `M2S72N<N>-<src>`, the per-N mixin | `staticDrbs`, `ulQfiRules` (per UE): the UE 0 entries replicated for k = 0 … N − 1, UE-major (`per_ue_list`) |

**Why the comparison needs a canonical extraction.** A raw section comparison is not meaningful, for three reasons:
- **Shadowed entries.** A base section lists *every* source entry in OMNeT++ lookup order, shadowed ones included. In the `qdu` bases, the M1 single-rule `dlQfiRules` follows the effective two-rule list.
- **Inherited keys.** `M2S72B-qde-Ca-L` sets no bearer key itself; it `extends = M2S72B-qdu-Ca-L`.
- **Split placement.** The keys are spread over two sections.

**The extraction used by the oracle.** It is implemented independently of the compiler (`check/test_tsnaf_compile.py`, `expected()`). For each (source, N), it takes the **effective** entry of each key by OMNeT++'s first-match rule over the chain `M2S72N<N>-<src>`, `M2S72B-<src>`, then the base's `extends` chain. The result is the exact entry text: the key line plus its continuation lines. The compiler's output must equal the concatenation of those entries **byte for byte**, with no extra key.

**The premises of the extraction are themselves tested (T-premises).**
- `[General]`, in both files and their includes, sets no bearer key.
- The case list equals the set of generated per-N mixins of each file.
- In each of the **829 configurations** built on an S7.2a source:
  - only its N mixin and its base chain set bearer keys;
  - the N mixin comes before the base.

**Sensitivity.** Injecting one bearer key into a load mixin that runnable configurations extend makes that premise check fail (checked on a temporary copy).

## 3. Reproduced configurations (37 cases, 37 byte-identical)

| File | Source | Specification | N reproduced | Effective keys |
|---|---|---|---|---|
| `m2s72.ini` | `q0-idle` | `s72-q0` | 1, 2, 4, 8 | dlQfiRules, staticDrbs, ulQfiRules |
| `m2s72.ini` | `q0-load` | `s72-q0` | 1 | same |
| `m2s72.ini` | `C-a` | `s72-q0` | 1 | same |
| `m2s72.ini` | `E-all` | `s72-q0` | 1 | same |
| `m2s72.ini` | `q0-Ca` | `s72-q0` | 1, 2, 4 | same |
| `m2s72.ini` | `q0-Ca-sus` | `s72-q0` | 2, 4 | same |
| `m2s72.ini` | `q0-Ca-L` | `s72-q0` | 1, 2, 4, 8 | same |
| `m2s72.ini` | `qdu-idle` | `s72-qdu` | 1, 2, 4, 8 | dlQfiRules, drbProfiles, staticDrbs, ulQfiRules |
| `m2s72.ini` | `qdu-Ca` | `s72-qdu` | 1, 2, 4 | same |
| `m2s72.ini` | `qdu-Ca-sus` | `s72-qdu` | 2, 4 | same |
| `m2s72.ini` | `qdu-Ca-L` | `s72-qdu` | 1, 2, 4, 8 | same |
| `m2s72s5.ini` | `q0p-Ca-L` | `s72-q0p` | 1, 2, 4, 8 | dlQfiRules, drbProfiles, staticDrbs, ulQfiRules |
| `m2s72s5.ini` | `qde-Ca-L` | `s72-qde` | 1, 2, 4, 8 | same (dlQfiRules and drbProfiles inherited from `qdu-Ca-L`) |

Every N value that the generators produce is covered; no case is skipped. The N values are those the generators emit, so for example `q0-load`, `C-a` and `E-all` exist only at N = 1.

**The four specifications** (`simulations/m2/scfg/`):

| Specification | Content |
|---|---|
| `s72-q0` | DL and UL PCP 5 (VID 42) → QFI 5 → DRB 2 (LCG 1, UM); default DRB 1 (LCG 3, UM); no profiles |
| `s72-qdu` | as `q0`, plus a DL gPTP-event stream → QFI 10 → DRB 4 (LCG 2, UM). Profiles `nasc-be` (90 / 300) and `nasc-gptp` (10 / 5): DRB 1 and 2 `nasc-be`, DRB 4 `nasc-gptp`. The gPTP rule is first. |
| `s72-q0p` | as `q0` with both profiles defined; DRB 1 and 2 `nasc-be` |
| `s72-qde` | as `qdu` but DRB 4 `nasc-be`. `nasc-gptp` stays defined and unused, as in the accepted configuration (Q-de = Q-d minus its gPTP priority, decision D-1). |

## 4. Tests (`simulations/m2/check/test_tsnaf_compile.py`)

**Final line:** `TSN AF compiler tests: 147 / 147 PASS, 0 FAIL; 37 compatibility cases reproduced`, under `python3 -I -B`, from an unrelated directory, in about 7 s. At step 144 it was 102 / 102.

| Group | Tests |
|---|---|
| T-premises | 8: committed identities; `[General]`; case coverage; chain premises on 829 configurations |
| T-compat | 37 cases, plus "every listed case reproduced" |
| T-determinism | 3: repeated compilation; member, DRB, QoS-flow and profile order independence; stream order sets the rule order |
| T-allowed | 4, none of them conflicts: the same PCP to different QFIs on different UEs (UL); different UL and DL mappings; a QFI reused by every UE; two streams with the same classifier and QFI giving one rule |
| T-negative | 37 (§4a) |
| T-cli | 9: stdout under `-I`; complete `--out`; an existing output refused and unchanged; invalid input gives exit 1, no file, no stdout; duplicate JSON key; malformed JSON; validate; no stray temporary file |
| T-malformed (C1) | 37: each wrong-type case gives `SpecError`, CLI exit 1, empty stdout, no `--out` file and no traceback. Cases: stream `source` / `destination` / `class` / `id` / `direction` as arrays, objects or numbers; QoS-flow `drb_id` as an array, object or string; a DRB `profile` reference as an array, object or number; endpoint definitions as a string, list or null; an endpoint `side` as a list; `endpoints` as a list; `ues` as an object, a non-`all` string, or with string, nested-list or boolean elements; VID as an array or object; PCP as a string; QFI as a float; stream, DRB and QoS-flow entries of the wrong type; `drb_profiles` as a list; a profile as a string; `default` as a string; the specification as a list |
| T-fuzz (C1) | 1: 6 204 replace / add mutations with 22 wrong-type values over every path of the four specifications, each at N = 1 and 2, plus `--ues` of every type: no unhandled exception |
| T-vid (C2) | 7: no notes for the accepted specifications; same PCP / different VID / same QFI is valid, gives an identical output and a note (DL; UL scoped to the UE); different QFIs are refused with the VID statement (DL and UL); same VID gives no note; the CLI note goes to stderr with stdout unchanged |
| T-isolation | 3: both accepted generators' `check` IDENTICAL; committed files unchanged |

### 4a. Negative controls

| Requirement | Controls |
|---|---|
| Out-of-range PCP, VID, QFI | PCP 8; PCP −1; PCP `true`; VID 0; VID 4095; QFI 0 on a stream; QFI 64 on a QoS flow; LCG 8 |
| Unknown endpoint or UE | unknown endpoint `talker2`; UE index 2 at N = 2 |
| Invalid stream direction | `both`; a DL stream from a ue-side endpoint |
| Missing referenced DRB profile | profile `nasc-tsn` |
| Conflicting classification rules in the same scope | DL PCP 5 → QFI 5 and → QFI 10 (shared scope); UL PCP 5 → QFI 5 and → QFI 10 on UE 1 |
| Unsupported input fields | `tas_gate_lists` (top level); `max_latency` (stream); `pdcpDuplication` (DRB); `resourceType` (profile); RLC mode `TM`; unknown class `gptp-general` |
| Duplicate identities | stream id; DRB id; QFI declaration; JSON key |
| Invalid or incomplete configuration | wrong schema; missing `streams`; empty `drbs`; empty UE list; no or two default DRBs; a QoS flow on an undefined or default DRB; a stream QFI without a QoS flow; a PCP stream without a VID; both or no classifiers; `--ues 0`; malformed JSON |

**Sensitivity of the C1 tests.** Run against the step-144 compiler (`cf13cc4`), 15 of the T-malformed cases and T-fuzz fail with unhandled `AttributeError` / `TypeError`, while 22 T-malformed cases already passed. The suite then stops at T-vid, because the original has no `notes`.

## 5. Existing suites on this branch (unmodified)

| Suite | Final line |
|---|---|
| `test_m2s72_a2.py` | `A-2 tests: 18 / 18 PASS` |
| `test_m2s72_a2probe.py` | `A-2 probe tests: 11 / 11 PASS` |
| `test_m2s72_a2v1.py` | `10 / 10 PASS` |
| `test_m2s72_gen.py` | `generator negative tests: 67 PASS, 0 FAIL` |
| `test_m2s72s5.py` | `S5-1 tests: 38 / 38 PASS` |
| `test_m2s72s5_2.py` | `S5-2 tests: 28 / 28 PASS` |
| `test_m2s72s5_n2.py` | `S5 N = 2 tests: 19 / 19 PASS` |
| `test_m2s72s5_smoke.py` | `S5 smoke contract tests: 9 / 9 PASS` |
| `test_m2s72_a21.py` | `A-2.1 tests: 18 / 18 PASS, 0 PENDING, 0 FAIL` |
| `test_m2s72_a21_fixture.py` | `A-2.1 fixture-extractor tests: 14 / 14 PASS, 0 FAIL` |

## 6. Limitations and deferred features

1. **Effective-entry equivalence, not section equivalence.** The compiler reproduces the effective bearer entries of each (source, N). It does not reproduce:
   - the generator's section placement (base versus N mixin);
   - its provenance comments;
   - the shadowed source entries the base sections list.

   Integrating the compiler's output into `.ini` sections is a later increment.
2. **The layout rule matches the generator on every existing configuration, not by construction.** The generator copies the source's line breaks, whereas the compiler applies a declared rule (§4 of the interface). A future source with a single-line multi-element template would differ in layout only, not in content.
3. **The specifications are hand-written descriptions of the accepted designs.** They are validated by the byte-identical oracle. They do not describe the traffic applications (`numApps`, taggers, flow indices), which S-CFG/1 does not emit. PCP 0 traffic uses the default DRB and needs no stream.
4. **The VID is validated but not classified on** (interface §3a). Different QoS flows for the same PCP on different VLANs are refused, and a shared rule across VLANs is reported as a note.
5. **The oracle's chain resolution is first-match over a depth-first `extends` order.** That equals OMNeT++'s C3 linearisation for these files: there is one N mixin and one base per configuration, and only those set bearer keys (tested). It is not a general OMNeT++ resolver.
6. **Not in this increment:** TAS / Qbv, TSCAI, FRER, runtime observation, C++, simulator execution, per-UE DRB templates, and dynamic 5GC configuration. **CI (step 145, C3):** the suite is added to tier-0 as its 11th step, in a separate commit.
