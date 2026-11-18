#!/usr/bin/env bash
# Allow-listed, screened, text-only diagnostics (C-15). Any screening failure suppresses publication and fails.
. "$(dirname "$0")/../lib/common.sh"
set +e
if grep -qx 'guard_terminated: yes' "$EV/guard.txt" 2>/dev/null; then
  rm -f "$EV/guard.target" "$EV/guard.off" "$EV/guard.pid" "$EV/guard.heartbeat"
else
  echo "::error::guard termination not confirmed; diagnostics not published"; exit 1
fi
P="$CI/publish"; rm -rf "$P"; mkdir -p "$P"
ALLOW="identity.txt runner.txt df-start.txt df-end.txt timings.tsv disk.tsv disk-gates.txt guard.txt guard-checks.txt
       guard-actions.txt exec-checks.txt lock.txt lock-enforcement.txt flake-lock-check.txt workspace-admin-check.txt nix.txt
       opp_env.txt release-assets.txt probe.txt adaptations.tsv adaptations-summary.txt postdownload-verify.txt
       source-identity.txt sizes.txt nix-store-summary.txt capacity.txt stage-resources.tsv c-rows.json STOP GUARD_FAILURE
       host-cxx-packages-before.tsv host-cxx-packages-after.tsv host-packages.diff host-libcxx.txt c4-case.txt
       apt-remove-proposed.txt apt-remove-simulation.txt apt-remove-transaction.txt apt-remove.txt
       runtime-probe-before.txt runtime-probe-after.txt runtime-gates.txt runpath-observation.txt HYPOTHESIS_NOT_CONFIRMED
       sys-libs.txt binaries.tsv unresolved.txt identity-tools.txt build-options.txt opp_run-version.txt runtime-symbols.txt
       validate-result.txt runpath-observation-validate.txt source-changes.tsv source-changes-summary.txt
       wrapper-setup.txt wrapper-result.txt wrapper-results.tsv opp_run-audit.tsv wrapper-git-status-before.txt
       wrapper-git-status-after.txt"
for f in $ALLOW; do [[ -f "$EV/$f" ]] && cp "$EV/$f" "$P/$f"; done
[[ -f "$EV/wrapper-suite.txt" ]] && tail -n 3000 "$EV/wrapper-suite.txt" > "$P/wrapper-suite.txt"
# Tool logs are published only as screened tails.
for l in realise probe probe-runtime-before probe-runtime-after build-omnetpp build-inet build-simu5g build-nasctime validate wrapper-suite; do
  [[ -f "$EV/$l.log" ]] && tail -n 300 "$EV/$l.log" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\r/\n/g' > "$P/$l.tail.txt"
done
bad=0
while IFS= read -r -d '' f; do
  case "$(file -b --mime-type "$f")" in
    text/*|application/json|inode/x-empty) ;;
    *) echo "non-text diagnostic: $(basename "$f")"; bad=1 ;;
  esac
done < <(find "$P" -type f -print0)
/usr/bin/python3 -I "$T1_LIB/screen.py" "$P"/* || bad=1
total=$(du -sb "$P" | cut -f1); echo "diagnostics_bytes: $total"
(( total <= 20 * 1024 * 1024 )) || { echo "diagnostics exceed 20 MiB"; bad=1; }
if (( bad )); then
  rm -rf "$P"
  echo "::error::diagnostic screening failed; publication suppressed (reasons above name files and patterns only)"
  exit 1
fi
ls -1 "$P"
