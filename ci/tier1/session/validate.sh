#!/usr/bin/env bash
# usage: bash validate.sh <evidence dir> <workspace> <repo>. Runs inside the opp_env session.
# Static inspection only (sizes, hashes, ELF metadata, dynamic resolution, symbol versions) plus the approved
# `opp_run -v`. Writes four separate results; every component runs even if another fails.
set -uo pipefail
EVD=$1; WSD=$2; REPO=$3
bin_fail=0; link_fail=0; rt_fail=0; rt_ne=0; v_fail=0
T="$EVD/binaries.tsv"; : > "$EVD/unresolved.txt"; : > "$EVD/runtime-symbols.txt"
RD=$(command -v readelf || command -v llvm-readelf || true)
INTERP=$(patchelf --print-interpreter "$OMNETPP_ROOT/bin/opp_run" 2>/dev/null || true)
CTX="$OMNETPP_ROOT/lib:$INET_ROOT/src:$SIMU5G_ROOT/src"
{
  echo "readelf: ${RD:-<absent>}"
  echo "elf_interpreter_of_opp_run: ${INTERP:-<absent>}"
  echo "resolution_context: LD_LIBRARY_PATH=OMNETPP_ROOT/lib:INET_ROOT/src:SIMU5G_ROOT/src (+ session value); no host directories"
  echo "nix_build_cores: ${NIX_BUILD_CORES:-<unset>}"
  echo "build_modes_session: ${BUILD_MODES:-<unset>}"
  for t in clang++ g++ ld.lld ld make ccache python3; do echo "tool $t: $(command -v "$t") | $("$t" --version 2>&1 | head -1)"; done
} > "$EVD/identity-tools.txt"
if [[ -z "$RD" || ! -x "$INTERP" ]]; then
  printf 'binaries_result: FAIL\noppv_result: FAIL\nlinkage_result: FAIL\nruntime_result: NOT EVALUATED\nvalidate_result: FAIL (readelf or ELF interpreter unavailable)\n' > "$EVD/validate-result.txt"
  exit 1
fi
printf 'project\tkind\tpath\tbytes\tsha256\telf\tcompiler_comment\tneeded\trunpath\tunresolved\tcxx_runtime_violation\tlibunwind\tlibstdcxx_resolved\tunexpected_resolution\n' > "$T"
: > "$EVD/runpath-observation-validate.txt"
rel() { local p=${1#"$WSD"/}; echo "${p/#$REPO\//nascTime/}"; }
check() {  # project kind file
  local proj=$1 kind=$2 f=$3 size sha elf=no comp="" needed="" runpath="" unres="n/a" lst lrc viol="n/a" unw="n/a" std="n/a" unexp="n/a" d cls
  if [[ ! -f "$f" ]]; then
    printf '%s\t%s\t%s\tMISSING\t\t\t\t\t\t\t\t\t\t\n' "$proj" "$kind" "$(rel "$f")" >> "$T"; bin_fail=1; return
  fi
  size=$(stat -c %s "$f"); sha=$(sha256sum "$f" | cut -c1-64)
  if [[ "$(head -c 4 "$f" | od -An -c | tr -d ' \n')" == '177ELF' ]]; then
    elf=yes
    comp=$("$RD" -p .comment "$f" 2>/dev/null | sed -n 's/^ *\[ *[0-9a-f]*\] *//p' | sort -u | paste -sd ';')
    needed=$("$RD" -d "$f" 2>/dev/null | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p' | paste -sd ',')
    runpath=$("$RD" -d "$f" 2>/dev/null | sed -n 's/.*(\(RUNPATH\|RPATH\)).*\[\(.*\)\]/\1=\2/p' | paste -sd ',')
    lst=$(LD_LIBRARY_PATH="$CTX${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$INTERP" --list "$f" 2>&1); lrc=$?
    unres=$(grep -c -E 'not found|cannot open|error while loading' <<< "$lst")
    if (( lrc != 0 && unres == 0 )); then unres="list-failed($lrc)"; fi
    if [[ "$unres" != 0 ]]; then
      link_fail=1
      { grep -E 'not found|cannot open|error while loading' <<< "$lst" || echo "list exit $lrc"; } | sed "s#^#$(rel "$f"): #" >> "$EVD/unresolved.txt"
    fi
    # C++ runtime: direct (NEEDED) or transitive (resolved list) libc++ / libc++abi is a violation.
    viol=$( { tr ',' '\n' <<< "$needed"; sed -n 's/^[[:space:]]*\([^ ]*\) =>.*/\1/p' <<< "$lst"; } | grep -E '^libc\+\+(abi)?\.so' | sort -u | paste -sd ',')
    viol=${viol:-none}
    unw=$( { tr ',' '\n' <<< "$needed"; sed -n 's/^[[:space:]]*\([^ ]*\) =>.*/\1/p' <<< "$lst"; } | grep -E '^libunwind\.so' | sort -u | paste -sd ',')
    unw=${unw:-none}
    std=$(sed -n 's/^[[:space:]]*libstdc++\.so\.6 => \([^ ]*\).*/\1/p' <<< "$lst" | head -1)
    std=${std:-absent}
    [[ "$viol" == none ]] || rt_fail=1
    # Every resolved library must come from /nix/store or the three workspace project library directories.
    unexp=$(sed -n 's/^[[:space:]]*[^ ]* => \(\/[^ ]*\).*/\1/p' <<< "$lst" \
      | grep -v -E "^(/nix/store/|$OMNETPP_ROOT/lib/|$INET_ROOT/src/|$SIMU5G_ROOT/src/)" | paste -sd ',')
    unexp=${unexp:-none}
    [[ "$unexp" == none ]] || rt_fail=1
    # RUNPATH classification (C2/C-12): store | project (the three project library directories) | relative (resolved
    # against the session's working directory, the controlled empty directory) | absent (absolute, does not exist; its
    # continued absence is checked around every session) | UNEXPECTED (absolute, exists, neither store nor project).
    for d in $("$RD" -d "$f" 2>/dev/null | sed -n 's/.*(\(RUNPATH\|RPATH\)).*\[\(.*\)\]/\2/p' | tr ':' ' '); do
      case "$d" in
        /nix/store/*) continue ;;
        "$OMNETPP_ROOT/lib"|"$INET_ROOT/src"|"$SIMU5G_ROOT/src") cls=project ;;
        /*) if [[ -e "$d" ]]; then cls=UNEXPECTED; rt_fail=1; else cls=absent; fi ;;
        *) cls=relative ;;
      esac
      echo "$(rel "$f"): non-store RUNPATH entry $d exists=$([[ -d "$d" ]] && echo yes || echo no) class=$cls" >> "$EVD/runpath-observation-validate.txt"
    done
    if [[ "$unres" != 0 ]]; then rt_ne=1
    elif [[ "$std" != absent && ( "$std" != /nix/store/* || "$std" != *-gcc-* ) ]]; then rt_fail=1; fi
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$proj" "$kind" "$(rel "$f")" "$size" "$sha" "$elf" "$comp" "$needed" "$runpath" "$unres" "$viol" "$unw" "$std" "$unexp" >> "$T"
}
O=$OMNETPP_ROOT
for b in opp_run opp_run_release opp_msgtool opp_nedtool opp_scavetool opp_eventlogtool; do check omnetpp executable "$O/bin/$b"; done
for b in opp_msgc opp_makemake opp_featuretool; do check omnetpp tool "$O/bin/$b"; done
for l in oppcommon opplayout oppeventlog oppscave oppnedxml oppsim oppenvir oppcmdenv oppqtenv; do check omnetpp library "$O/lib/lib$l.so"; done
check omnetpp static-library "$O/lib/liboppmain.a"
check inet library "$INET_ROOT/src/libINET.so"
check simu5g library "$SIMU5G_ROOT/src/libsimu5g.so"
check nascTime library "$REPO/src/nasctime/m2/libnasctime_m2.so"
# Release-only: no debug-mode outputs may exist.
dbg=$(ls "$O"/lib/*_dbg.* "$O"/bin/*_dbg "$INET_ROOT"/src/*_dbg.* "$SIMU5G_ROOT"/src/*_dbg.* "$REPO"/src/nasctime/m2/*_dbg.* 2>/dev/null | wc -l)
echo "debug_outputs_present: $dbg" >> "$EVD/identity-tools.txt"
(( dbg == 0 )) || bin_fail=1
# Symbol-version and C++-runtime symbol evidence for the relevant objects.
for f in "$O/bin/opp_run" "$O/lib/liboppsim.so" "$O/lib/liboppenvir.so" "$INET_ROOT/src/libINET.so" "$SIMU5G_ROOT/src/libsimu5g.so" "$REPO/src/nasctime/m2/libnasctime_m2.so"; do
  [[ -f "$f" ]] || continue
  {
    echo "== $(rel "$f")"
    echo "dynsym_total: $("$RD" --dyn-syms -W "$f" | awk 'NF >= 8 && $1 ~ /:$/' | wc -l)  undefined: $("$RD" --dyn-syms -W "$f" | awk 'NF >= 8 && $7 == "UND"' | wc -l)"
    "$RD" -V -W "$f" | sed -n "/Version needs section/,\$p" | grep -E 'File:|Name:' | sed 's/^ */  /' | head -80
    echo "  undefined C++ runtime / unwinder symbols (with version):"
    "$RD" --dyn-syms -W "$f" | awk 'NF >= 8 && $7 == "UND" {print $8}' \
      | grep -E '^(__cxa_|_Zn[wa]|_Zd[la]|__gxx_personality|_Unwind_|_ZTISt9exception|_ZSt9terminate|__dynamic_cast)' | sort -u | head -60 | sed 's/^/    /'
  } >> "$EVD/runtime-symbols.txt"
done
# Approved identity probe (prints version and build information and exits; no simulation).
opp_run -v > "$EVD/opp_run-version.txt" 2>&1; vrc=$?
echo "opp_run_v_exit: $vrc" >> "$EVD/opp_run-version.txt"
(( vrc == 0 )) || v_fail=1
grep -qE 'Version: 6\.5\.0|Version: 6\.5,|Build: 6\.5\.0' "$EVD/opp_run-version.txt" || v_fail=1
# Effective build options.
{
  echo "# OMNeT++ Makefile.inc (generated by configure)"
  grep -E '^(CC|CXX|CFLAGS_RELEASE|CFLAGS_DEBUG|CFLAGS_EXTRA|CXXFLAGS|LDFLAGS|LDFLAGS_EXTRA|LD|SHLIB_LD|SYS_LIBS|LIBS|AR|AR_CR|RANLIB|SHARED_LIBS|TOOLCHAIN_NAME|PYTHON|QMAKE|OPENMP_FLAGS|DEFINES|LDFLAG_[A-Z]+|AS_NEEDED_[A-Z]+|WITH_[A-Z_]+|PREFER_[A-Z_]+)[[:space:]]*[:+]?=' "$O/Makefile.inc"
  for mk in "$INET_ROOT/src/Makefile" "$SIMU5G_ROOT/src/Makefile" "$REPO/src/nasctime/m2/Makefile"; do
    echo "# $(rel "$mk"): generator invocation"
    sed -n '1,25p' "$mk" | grep -iE 'opp_makemake|invocation|^#  ' | head -12
  done
  echo "# INET enabled features (.oppfeaturestate)"
  grep -oE 'id="[^"]+" enabled="true"' "$INET_ROOT/.oppfeaturestate" | sed 's/ enabled="true"//; s/id=//; s/"//g' | paste -sd ' '
  echo "inet_features_enabled_count: $(grep -c 'enabled="true"' "$INET_ROOT/.oppfeaturestate")"
  echo "inet_features_disabled_count: $(grep -c 'enabled="false"' "$INET_ROOT/.oppfeaturestate")"
  echo "inet_oppfeaturestate_sha256: $(sha256sum "$INET_ROOT/.oppfeaturestate" | cut -c1-64)"
  echo "inet_features_h_sha256: $(sha256sum "$INET_ROOT/src/inet/features.h" 2>/dev/null | cut -c1-64)"
} > "$EVD/build-options.txt" 2>&1
r() { [[ "$1" == 0 ]] && echo PASS || echo FAIL; }
rt=$(r "$rt_fail"); (( rt_fail == 0 && rt_ne == 1 )) && rt="NOT EVALUATED"
{
  echo "binaries_result: $(r "$bin_fail")"
  echo "oppv_result: $(r "$v_fail")"
  echo "linkage_result: $(r "$link_fail")"
  echo "runtime_result: $rt"
  echo "validate_result: $( (( bin_fail + v_fail + link_fail + rt_fail == 0 )) && [[ "$rt" == PASS ]] && echo PASS || echo FAIL)"
} > "$EVD/validate-result.txt"
grep -q '^validate_result: PASS' "$EVD/validate-result.txt"
