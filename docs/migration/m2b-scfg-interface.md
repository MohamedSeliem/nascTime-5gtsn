# M2-B S-CFG interface, version 1 (`nasctime-scfg/1`)

**Status: M2B-1, for independent review (step 144).** This is the B2 interface definition of the S-CFG seam (`travel-development-plan.md` §1) for the TSN AF offline compiler `simulations/m2/tools/tsnaf_compile.py` (B3).

It translates a static TSN stream specification into the existing Simu5G 1.8.1 bearer configuration mechanism, the `BearerConfigurator` parameters. It is **not** a CNC protocol and does **not** configure a 5G core dynamically.

## 1. Three distinct objects

| Object | Meaning | Where it appears in the output |
|---|---|---|
| **TSN stream** | A flow of Ethernet frames between two TSN endpoints, identified by its stream identity, direction, endpoints, UEs and its classifier: VLAN ID and PCP, or a frame class | Only through the classification rule it produces |
| **QoS flow** | A 5G QoS flow, identified by its QFI. Several streams may share one QoS flow. | A classification rule's `qfi`; a DRB's `mappedQfis` |
| **DRB** | A data radio bearer of a UE, identified by its DRB id, carrying zero or more QoS flows. The default DRB carries everything that matches no rule. | `staticDrbs` |

The chain is: stream → (classification rule) → QFI → (QoS flow declaration) → DRB → (optional) DRB profile.

## 2. Input: a JSON file (`schema: "nasctime-scfg/1"`)

| Field | Required | Content |
|---|---|---|
| `schema` | yes | `"nasctime-scfg/1"` |
| `endpoints` | yes | `{name: {"side": "network" \| "ue"}}`. A **network-side** endpoint is behind the NW-TT (e.g. `listener`, the S7.2a gPTP grandmaster). A **ue-side** endpoint is one module per UE, behind DS-TT k (e.g. `talker`, i.e. `talker[k]`). Names are NED module names. |
| `drb_profiles` | no | `{name: {"qosPriorityLevel": 1…127, "packetDelayBudget": 1…100000}}`. The values and units are Simu5G's. Names match `[a-z][a-z0-9-]*`. |
| `drbs` | yes | The **per-UE DRB template**, applied identically to every UE: `[{"drb_id": 1…32, "default": true (exactly one DRB), "lcg": 0…7, "rlc_mode": "UM" \| "AM", "profile": <defined profile>}]`. `default` and `profile` are optional. |
| `qos_flows` | yes | `[{"qfi": 1…63, "drb_id": <a non-default DRB of the template>}]`. Each QFI is declared once. |
| `streams` | yes | `[{"id", "direction": "dl" \| "ul", "source", "destination", "ues", <classifier>, "qfi"}]`, where:<br>• `id` is unique and matches `[a-z][a-z0-9-]*`;<br>• `ues` is `"all"` or a list of UE indices below N;<br>• the classifier is **either** `"pcp": 0…7` with `"vid": 1…4094` **or** `"class": "gptp-event"` (untagged gPTP Sync / Follow_Up). |

**Direction and endpoints.** A DL stream runs from a network-side endpoint to a ue-side endpoint; an UL stream runs the other way.

**Compiler parameter.** `--ues N` (1…64) is the number of UEs, `numUe`.

**Any field not listed above is refused**, at every level. That includes TAS, TSCAI and FRER fields.

## 3. Output: the four `BearerConfigurator` entries

| Key | Scope | Built from |
|---|---|---|
| `*.bearerConfigurator.dlQfiRules` | **shared** (Simu5G DL rules carry no UE) | one rule `{filter, qfi}` per distinct DL classifier |
| `*.bearerConfigurator.drbProfiles` | **shared** | the profile catalogue, if any profile is defined |
| `*.bearerConfigurator.staticDrbs` | **per UE** | the DRB template for each UE k: `{coreNetwork: "5gc", ue: "ue[k]", drbId, isDefault: true \| mappedQfis: [...], lcg, rlcMode[, profile]}` |
| `*.bearerConfigurator.ulQfiRules` | **per UE** | one rule `{ue: "ue[k]", filter, qfi}` per distinct UL classifier of each UE |

**Classifier filters** (Simu5G / INET packet-filter expressions):
- PCP p: `expr(has(ieee8021qctag) && ieee8021qctag.pcp == p)`;
- `gptp-event`: `expr(has(GptpSync) || has(GptpFollowUp))`.

The VID is part of the stream identity and is validated, but S-CFG/1 does not classify on it (§6).

## 4. Deterministic ordering and serialisation

| Item | Order |
|---|---|
| Output keys | `dlQfiRules`, `drbProfiles`, `staticDrbs`, `ulQfiRules`. A key with no content is omitted. |
| DL rules | Order of the first appearance of each classifier in `streams`. Simu5G evaluates a rule list in order (first match), so the order is part of the semantics and is taken from the input explicitly. |
| UL rules | UE-major (k = 0 … N − 1); within a UE, the order of first appearance in `streams` |
| DRBs | UE-major; within a UE, ascending `drb_id`. `mappedQfis` ascending. |
| Profiles | Ascending name |
| Fields | The fixed order shown in §3 |
| Layout | A list (or the profile map) is written on one line when its **template** has one element: the per-UE DRB or UL template, or the shared list. Otherwise it is written one element per line, indented 4 spaces, with the closing bracket indented 4 spaces. Each entry ends with a newline. |

The output does not depend on the order of JSON object members, DRBs, QoS flows or profiles. It depends on the order of `streams` only through the rule order.

## 5. Validation and failure behaviour

The whole specification is validated before anything is written, and **every** problem is reported, one `error:` line each, exit 1. Errors include:
- **out-of-range values:** PCP, VID, QFI, LCG, DRB id, profile values;
- **unknown references:** an unknown endpoint or UE index, a profile that is not defined, a QoS flow on an undefined or default DRB, a stream QFI with no QoS flow;
- **invalid structure:** an invalid direction, a direction / endpoint-side mismatch, zero or several classifiers;
- **duplicates:** a duplicate stream identity, DRB id, QFI declaration or JSON key;
- **unsupported fields** and malformed JSON.

**Conflicts.**
- A conflict is the **same classifier mapped to different QFIs within the same scope**:
  - the DL scope is shared by every UE;
  - the UL scope is one UE.
- **Not conflicts:**
  - the same classifier mapped to the same QFI by several streams (one rule is emitted);
  - a QFI reused across UEs;
  - the same PCP mapped differently in UL and DL, or on different UEs in UL.

**No partial output.** On failure:
- nothing is printed on standard output;
- `--out` creates no file (it is written to a temporary file and then linked into place);
- an existing `--out` file is refused and never overwritten;
- the compiler never reads or writes any simulation configuration.

## 6. Scope of S-CFG/1 and deferred items

**In scope:** the bearer and QoS configuration exercised by S7.2a. That is:
- DL and UL PCP classification;
- the DL gPTP-event classification;
- a per-UE DRB template with LCG, RLC mode and an optional profile;
- the DRB profile catalogue.

**Deferred:**

| Item | Reason |
|---|---|
| VID-based classification | Not exercised by any accepted configuration; the INET filter field name would be unvalidated |
| Per-UE DRB templates, and DRBs that are both default and mapped | Not exercised |
| Other `drbProfiles` fields and other RLC modes | Not exercised |
| TAS gate lists, TSCAI, FRER / S-PATH member streams | M2B-3 and later; M3 |
| Traffic-application emission (`numApps`, `tagger.pcp` / `vlanId`, flow indices) | That is traffic configuration, not S-CFG bearer emission |
| Placement of the output into `.ini` sections and the runtime observer | Later increments |
| A CNC protocol, and dynamic 5G core configuration | Out of scope by design |
