#!/usr/bin/env bash
# Screened diagnostic artifact: tier-1's prepared publication plus the tier-2 text records (copied with the experiment prefix);
# every file must be text and pass the screen; any failure suppresses the whole diagnostic publication.
. "$(dirname "$0")/../lib/t2common.sh"
set +e
P="$CI/publish"
[[ -d "$P" ]] || { echo "::error::tier-1 diagnostic publication is not available"; exit 1; }
X=$T2_EXPERIMENT
for f in identity.txt sim-control-preflight.txt sim-control-sim.txt hazards-preflight.txt hazards-sim.txt \
         binary-identity-preflight.tsv binary-identity-sim.tsv watchdog.tsv oracle.txt oracle.json e-rows.json \
         seal.txt seal-verify.txt modified-during-sim.txt opp_env-state-changed.txt git-status-before.txt \
         git-status-after.txt git-status-final.txt argv-preflight.txt argv-sim.txt observed-cmdline.txt \
         observed-cwd.txt cwd-preflight.txt runconfig-stderr.txt; do
  [[ -f "$REC/$f" ]] && cp "$REC/$f" "$P/$X-$f"
done
[[ -f "$E3/raw-manifest.sha256" ]] && cp "$E3/raw-manifest.sha256" "$P/$X-raw-manifest.sha256"
[[ -f "$RAW/effective-config.txt" ]] && cp "$RAW/effective-config.txt" "$P/$X-effective-config.txt"
[[ -f "$RAW/run-$SIM_CONFIG.log" ]] && tail -n 300 "$RAW/run-$SIM_CONFIG.log" > "$P/$X-run-$SIM_CONFIG.tail.txt"
for l in t2-runconfig t2-sim; do
  [[ -f "$EV/$l.log" ]] && tail -n 300 "$EV/$l.log" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\r/\n/g' > "$P/$X-$l.tail.txt"
done
bad=0
while IFS= read -r -d '' f; do
  case "$(file -b --mime-type "$f")" in text/*|application/json|inode/x-empty) ;; *) echo "non-text diagnostic: $(basename "$f")"; bad=1 ;; esac
done < <(find "$P" -type f -print0)
/usr/bin/python3 -I "$T1_LIB/screen.py" "$P"/* || bad=1
total=$(du -sb "$P" | cut -f1); echo "diagnostics_bytes: $total"
(( total <= 20 * 1024 * 1024 )) || { echo "diagnostics exceed 20 MiB"; bad=1; }
if (( bad )); then rm -rf "$P"; echo "::error::diagnostic screening failed; publication suppressed"; exit 1; fi
for f in "$P/$X"-*; do basename "$f"; done
