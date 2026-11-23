#!/usr/bin/env bash
# WP-A1 validation (runbook revision 3): run ONE stage script in a fresh network-less container with exactly the mounts
# of its profile, under a transcript, and return the stage's own exit code (script -e; a plain 'script' returns 0).
# usage: host-stage.sh <stage script name> <profile> <transcript file> [stage arguments]
#   profiles: p0       $Z read-write only (no evidence, no release)
#             release  + REL read-only, the parent of X read-write (X itself must not exist)
#             mapped   + X read-only at X (no mount at R)
#             mounted  + X read-only at X and at R=/mnt/nasctime-results
#             final    $Z read-write only
# Environment: Z (work dir), IMG (container image pinned by digest: <name>@sha256:<64 hex>).
set -u -o pipefail
stop() { echo "STOP [host-stage]: $*" >&2; exit 1; }
[ $# -ge 3 ] || stop "usage: host-stage.sh <stage script> <profile> <transcript> [stage arguments]"
s=$1 profile=$2 tr=$3; shift 3
[ -n "${Z:-}" ] && [ -d "$Z" ] || stop "Z is not a directory"
[ -f "$Z/scripts/$s" ] || stop "$Z/scripts/$s missing"
[[ ${IMG:-} =~ @sha256:([0-9a-f]{64})$ ]] || stop "IMG must be pinned by digest (<name>@sha256:<64 hex>)"
dig=${BASH_REMATCH[1]}
docker image inspect --format '{{join .RepoDigests "\n"}}' "$IMG" 2>/dev/null | grep -q "@sha256:$dig$" \
  || stop "image $IMG is not present locally with that digest"
. "$Z/vars.env" || stop "vars.env"
case "$tr" in /*) ;; *) stop "transcript path must be absolute";; esac
bind() { echo "type=bind,source=$1,target=$2${3:+,$3}"; }
need_dir() { [ -d "$1" ] && [ ! -L "$1" ] || stop "mount source $1 is not an existing directory"; }   # checked BEFORE any mount is built
need_dir "$Z"
case "$profile" in release) need_dir "$REL"; need_dir "$(dirname "$X")" ;; mapped|mounted) need_dir "$X" ;; esac
M=(--mount "$(bind "$Z" "$Z")")
case "$profile" in
  p0|final) ;;
  release) [ ! -e "$X" ] || stop "X $X exists before H-3"
           M+=(--mount "$(bind "$REL" "$REL" readonly)" --mount "$(bind "$(dirname "$X")" "$(dirname "$X")")") ;;
  mapped)  M+=(--mount "$(bind "$X" "$X" readonly)") ;;
  mounted) M+=(--mount "$(bind "$X" "$X" readonly)" --mount "$(bind "$X" "$R" readonly)") ;;
  *) stop "unknown profile $profile" ;;
esac
cmd=(docker run --rm --network none --user "$(id -u):$(id -g)" -e Z="$Z" -e HOME=/tmp -e IMG_DIGEST="$dig"
     "${M[@]}" -w "$Z" "$IMG" bash "$Z/scripts/$s" "$@")
echo "host-stage: $s $* profile $profile image $IMG" >> "$tr"
script -e -q -a -c "$(printf '%q ' "${cmd[@]}")" "$tr"
rc=$?
echo "host-stage: $s exit $rc" | tee -a "$tr"
exit "$rc"
