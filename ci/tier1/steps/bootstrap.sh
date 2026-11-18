#!/usr/bin/env bash
# Checked Nix and opp_env installation, workspace with the approved lock (both locks write-protected), release-asset
# identity gate, realisation of the pinned development shell (no build), and the lock gates after realisation.
. "$(dirname "$0")/../lib/common.sh"
export STAGE_CAP_S=$CAP_BOOTSTRAP_S
"$T1_LIB/guard-alive.sh" "bootstrap"
# Nix (installer pinned by sha256; the installer verifies the tarball against its embedded hash).
curl --fail -sSL --proto '=https' --tlsv1.2 -o "$DL/nix-install" "$NIX_INSTALLER_URL"
echo "$NIX_INSTALLER_SHA256  $DL/nix-install" | sha256sum -c -
grep -A2 -F "hash=$NIX_TARBALL_SHA256" "$DL/nix-install" | grep -qx '[[:space:]]*system=x86_64-linux'
"$T1_LIB/guarded.sh" nix-install sh "$DL/nix-install" --daemon --yes --no-channel-add --no-modify-profile
v=$(nix --version)
echo "nix_version: $v" | tee "$EV/nix.txt"
[[ "$v" == "nix (Nix) $NIX_VERSION" ]] || { echo "::error::unexpected Nix version: $v"; exit 1; }
# shellcheck disable=SC2086
nix $NIX_X config show > "$UNPUB/nix-config.txt"
grep -E '^(substituters|trusted-public-keys|require-sigs|sandbox|max-jobs|cores|experimental-features|accept-flake-config) ' \
  "$UNPUB/nix-config.txt" | tee -a "$EV/nix.txt"
grep -qx 'require-sigs = true' "$UNPUB/nix-config.txt" || { echo "::error::require-sigs is not true"; exit 1; }
echo "nix_store_bytes_after_nix_install: $(du -sb /nix/store | cut -f1)" | tee -a "$EV/nix.txt"
# opp_env (PyPI wheel pinned by sha256, no dependencies, private virtual environment).
W="$DL/opp_env-${OPP_ENV_PIN}-py3-none-any.whl"
curl --fail -sSL --proto '=https' --tlsv1.2 -o "$W" "$OPP_ENV_WHEEL_URL"
echo "$OPP_ENV_WHEEL_SHA256  $W" | sha256sum -c -
if /usr/bin/python3 -I -c 'import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
m = [n for n in z.namelist() if n.endswith(".dist-info/METADATA")][0]
print(z.read(m).decode())' "$W" | grep -q '^Requires-Dist:'; then
  echo "::error::wheel declares dependencies"; exit 1
fi
/usr/bin/python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --no-index --no-deps --only-binary :all: "$W" > "$UNPUB/pip.log" 2>&1
[[ "$("$OE" --version)" == "$OPP_ENV_PIN" ]] || { echo "::error::opp_env version mismatch"; exit 1; }
mod=$("$VENV/bin/python" -I -c 'import opp_env, os; print(os.path.dirname(os.path.realpath(opp_env.__file__)))')
[[ "$mod" == "$(realpath "$VENV")"/* ]] || { echo "::error::opp_env module outside the venv"; exit 1; }
echo "$OPP_ENV_MAIN_SHA256  $mod/opp_env.py" | sha256sum -c -
{
  echo "opp_env_version: $("$OE" --version)"
  echo "opp_env_module: $mod"
  echo "opp_env_main_sha256: $(sha256sum "$mod/opp_env.py" | cut -c1-64)"
  echo "opp_env_on_PATH: $(type -P opp_env || echo none)"
  echo "venv_python: $("$VENV/bin/python" -V 2>&1)"
} | tee "$EV/opp_env.txt"
# Workspace (outside the git tree) with the approved lock; both locks immutable.
(cd "$EXEC" && "$OE" init -w "$WS")
A="$WS/.opp_env_workspace"
[[ ! -e "$A/26.05" ]] || { echo "::error::$A/26.05 already exists"; exit 1; }
echo "$HELPER_LOCK_SHA256  $A/22.11/flake.lock" | sha256sum -c -
mkdir "$A/26.05"
install -m 0444 "$REPO/$LOCK_FILE" "$A/26.05/flake.lock"
echo "$LOCK_SHA256  $A/26.05/flake.lock" | sha256sum -c -
sudo chattr +i "$A/26.05/flake.lock" "$A/22.11/flake.lock"
{
  for f in "$A/26.05/flake.lock" "$A/22.11/flake.lock"; do
    attrs=$(lsattr "$f" | cut -d' ' -f1)
    [[ "$attrs" == *i* ]] || { echo "::error::immutable attribute not set on $(basename "$(dirname "$f")")"; exit 1; }
    echo "write_protection $(basename "$(dirname "$f")"): immutable ($attrs)"
  done
  echo "limitation: opp_env's nix develop invocation cannot be given --no-update-lock-file; an in-process lock update is detected and its write is blocked, but is not proven impossible"
} | tee "$EV/lock-enforcement.txt"
(cd "$A" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$EV/workspace-admin-before.sha256"
"$T1_LIB/lockcheck.sh" before-realisation
exec_check "after init"
# Release-asset identity gate (C-1/C4): opp_env must use the pinned URLs, and a separate streamed fetch must return
# the bytes measured in E2b. LIMITATION: this does not prove the bytes opp_env itself consumed (curl | tar).
"$OE" info --raw $PROJECTS > "$UNPUB/opp_env-info.json" 2>&1
: > "$EV/release-assets.txt"
arc=0
for p in OMNETPP INET SIMU5G; do
  u_var="ASSET_${p}_URL"; s_var="ASSET_${p}_SHA256"; u=${!u_var}; want=${!s_var}
  grep -qF "$u" "$UNPUB/opp_env-info.json" || { echo "::error::opp_env does not use $u"; exit 1; }
  got=$(curl --fail -sSL --proto '=https' --tlsv1.2 "$u" | sha256sum | cut -c1-64)
  echo "$p sha256: $got expected: $want match: $([[ "$got" == "$want" ]] && echo yes || echo NO)" | tee -a "$EV/release-assets.txt"
  [[ "$got" == "$want" ]] || arc=1
done
echo "scope: separate streamed fetch; not proof of the bytes opp_env consumed" >> "$EV/release-assets.txt"
echo "assets_check: $([[ $arc == 0 ]] && echo PASS || echo FAIL)" | tee -a "$EV/release-assets.txt"
(( arc == 0 )) || { echo "::error::release asset differs from the pinned checksum (upstream re-upload?)"; exit 1; }
# Realise the pinned development shell; --no-build: nothing is configured or compiled.
oe_session realise install -w "$WS" --no-pause --no-build $PROJECTS
echo "root_avail_after_realise_B: $(df -B1 --output=avail / | tail -1 | tr -d ' ')" | tee -a "$EV/sizes.txt"
"$T1_LIB/lockcheck.sh" after-realisation "$EV/realise.log"
# shellcheck disable=SC2086
nix $NIX_X flake metadata --json --no-update-lock-file --no-write-lock-file "path:$A/26.05" > "$UNPUB/flake-metadata-26.05.json"
/usr/bin/python3 -I "$PY/lock_metadata.py" "$UNPUB/flake-metadata-26.05.json" "$EV/flake-lock-check.txt"
echo "generated_flake_26.05_sha256: $(sha256sum "$A/26.05/flake.nix" | cut -c1-64)" | tee -a "$EV/flake-lock-check.txt"
echo "generated_flake_22.11_sha256: $(sha256sum "$A/22.11/flake.nix" | cut -c1-64)" | tee -a "$EV/flake-lock-check.txt"
(cd "$A" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$EV/workspace-admin-after.sha256"
/usr/bin/python3 -I "$PY/admin_diff.py" "$EV/workspace-admin-before.sha256" "$EV/workspace-admin-after.sha256" "$EV/workspace-admin-check.txt"
