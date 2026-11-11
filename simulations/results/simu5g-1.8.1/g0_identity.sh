#!/bin/bash
# M2-R181 R-4: legacy-identity proof. Every tracked record file of M1 and M2-S0..S6 in the legacy-mode worktree
# against the commit it was checked out at. Rule (the established G0 rule of M2-S5/S6/S7.1): checker outputs and
# documents byte-identical; env*.txt may differ only in run metadata (date_utc, nascTime_commit, os (host kernel),
# libnasctime_m2_sha256, m2s1_runs start time); in raw-outputs.sha256 / vec.sha256 only the lines of files that embed
# the run id or date (.sca, .vec, opp_scavetool .csv exports, M2-S3's per-run vec hashes) may differ.
WT=${1:?worktree}
cd "$WT"
P="simulations/m1/results simulations/m2/results/M2-S0 simulations/m2/results/M2-S1 simulations/m2/results/M2-S3 simulations/m2/results/M2-S4 simulations/m2/results/M2-S5 simulations/m2/results/M2-S6"
echo "worktree $WT at $(git rev-parse --short HEAD)"
bad=0
for f in $(git ls-files $P); do
  if [ ! -f "$f" ]; then echo "MISSING    $f"; bad=$((bad+1)); continue; fi
  if git diff --quiet HEAD -- "$f"; then echo "IDENTICAL  $(sha256sum "$f" | cut -c1-16)  $f"; continue; fi
  case "$f" in
    */env*.txt)
      other=$(git diff -U0 HEAD -- "$f" | grep -E '^[-+][^-+]' | grep -vE '^[-+](date_utc|nascTime_commit|libnasctime_m2_sha256|m2s1_runs|os):' )
      if [ -z "$other" ]; then echo "METADATA   $f"; else echo "DIFFERS    $f: $other"; bad=$((bad+1)); fi ;;
    *raw-outputs.sha256)
      dif=$(diff <(git show HEAD:"$f" | sort -k2) <(sort -k2 "$f") | grep '^[<>]' | awk '{print $3}' | grep -vE '\.(sca|vec|csv)$' | sort -u)
      ext=$(diff <(git show HEAD:"$f" | sort -k2) <(sort -k2 "$f") | grep '^>' | awk '{print $3}' | sed 's/.*\.//' | sort | uniq -c | awk '{printf "%s %s, ", $1, $2}')
      if [ -z "$dif" ]; then echo "RUNHEADER  $f: differing lines only for run-id/date files [${ext}]"; else echo "DIFFERS    $f: $(echo $dif | head -c 300)"; bad=$((bad+1)); fi ;;
    */M2-S3/vec.sha256)
      echo "RUNHEADER  $f: per-run .vec hashes (run id / date in the vector header)" ;;
    *) echo "DIFFERS    $f: $(git diff HEAD -- "$f" | grep -E '^[-+][^-+]' | head -4 | tr '\n' ' ' | cut -c1-300)"; bad=$((bad+1)) ;;
  esac
done
echo "R-4 verdict: $([ $bad = 0 ] && echo PASS || echo "FAIL ($bad files)")"
