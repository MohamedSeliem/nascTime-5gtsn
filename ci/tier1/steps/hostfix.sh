#!/usr/bin/env bash
# C-4 case A: controlled removal of the verified host libc++ development packages. The proposed set comes only from
# the provenance gate's removal candidates (plus the installed libc++-dev / libc++abi-dev metapackages); the simulated
# apt transaction is inspected first; no autoremove, no purge; the inventory change must equal the transaction.
. "$(dirname "$0")/../lib/common.sh"
"$T1_LIB/guard-alive.sh" "hostfix"
pat='^libc\+\+(abi)?(-[0-9]+)?-dev(:amd64)?$'
cands=()
while IFS= read -r p; do
  [[ "$p" =~ $pat ]] || { echo "::error::owner '$p' is not a libc++ development package; rejecting"; exit 1; }
  cands+=("${p%:amd64}")
done < <(sed -n 's/^removal_candidate: //p' "$EV/host-libcxx.txt")
for m in libc++-dev libc++abi-dev; do
  if dpkg-query -W -f '${Status}' "$m" 2>/dev/null | grep -qx 'install ok installed'; then cands+=("$m"); fi
done
(( ${#cands[@]} > 0 )) || { echo "::error::no removal candidates"; exit 1; }
mapfile -t cands < <(printf '%s\n' "${cands[@]}" | sort -u)
printf '%s\n' "${cands[@]}" | tee "$EV/apt-remove-proposed.txt"
apt-get -s remove "${cands[@]}" > "$EV/apt-remove-simulation.txt" 2>&1 \
  || { echo "::error::apt-get -s remove failed"; cat "$EV/apt-remove-simulation.txt"; exit 1; }
cat "$EV/apt-remove-simulation.txt"
/usr/bin/python3 -I "$PY/hostfix.py" transaction "$EV" || { echo "::error::proposed apt transaction rejected; nothing removed"; exit 1; }
mapfile -t remv < <(sed -n 's/^removal: //p' "$EV/apt-remove-transaction.txt")
# shellcheck disable=SC2024  # the log is deliberately written as the runner user
sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 remove -y "${remv[@]}" > "$EV/apt-remove.txt" 2>&1 \
  || { echo "::error::apt-get remove failed"; cat "$EV/apt-remove.txt"; exit 1; }
dpkg-query -W -f '${Package}\t${Version}\t${Status}\n' | sort > "$EV/host-packages-after.tsv"
grep -E '^(libc\+\+|libunwind|clang|lld|llvm)' "$EV/host-packages-after.tsv" > "$EV/host-cxx-packages-after.tsv" || true
cat "$EV/host-cxx-packages-after.tsv"
/usr/bin/python3 -I "$PY/hostfix.py" inventory "$EV" || { echo "::error::host package change differs from the approved transaction"; exit 1; }
