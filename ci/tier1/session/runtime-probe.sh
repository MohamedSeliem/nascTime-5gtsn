#!/usr/bin/env bash
# usage: bash runtime-probe.sh <out> <phase> <workdir>. Runs inside the opp_env session.
# Compiles and links one minimal C++ program three ways with linker tracing (no framework code). The
# resulting probe binaries are never executed; their dependencies are only listed by the ELF loader.
set -u
out=$1; phase=$2; D=$3; mkdir -p "$D"
RD=$(command -v readelf || command -v llvm-readelf || true)
printf '#include <iostream>\nint main() { std::cout << ""; return 0; }\n' > "$D/p.cc"
probe() {
  local name=$1 rc I; shift
  clang++ -fuse-ld=lld "$D/p.cc" "$@" -o "$D/$name" -Wl,--trace > "$D/$name.trace" 2>&1; rc=$?
  echo "probe $name args: ${*:-<none>}"
  echo "probe $name rc: $rc"
  grep -E 'libc\+\+|libunwind|libstdc\+\+|libgcc_s|unable to find library' "$D/$name.trace" | sed "s/^/probe $name trace: /"
  if [ "$rc" = 0 ] && [ -n "$RD" ]; then
    echo "probe $name needed: $("$RD" -d "$D/$name" | sed -n 's/.*(NEEDED).*\[\(.*\)\]/\1/p' | paste -sd,)"
    echo "probe $name runpath: $("$RD" -d "$D/$name" | sed -n 's/.*(\(RUNPATH\|RPATH\)).*\[\(.*\)\]/\2/p' | paste -sd,)"
    I=$(patchelf --print-interpreter "$D/$name" 2>/dev/null)
    echo "probe $name interpreter: $I"
    "$I" --list "$D/$name" 2>&1 | sed "s/^/probe $name resolved: /"
  fi
}
{
  echo "phase: $phase"
  echo "clang++: $(command -v clang++) | $(clang++ --version 2>&1 | head -1)"
  echo "ld.lld: $(command -v ld.lld) | $(ld.lld --version 2>&1 | head -1)"
  clang++ -print-search-dirs 2>&1 | sed 's/^/search-dirs /'
  clang++ -### -fuse-ld=lld "$D/p.cc" -lc++ -o "$D/driver" 2>&1 | tail -n 1 | tr ' ' '\n' | tr -d '"' | grep -E '^-L' | sed 's/^/driver-L /'
  probe libcxx -lc++
  probe default
  probe stdcxx -lstdc++
} > "$out" 2>&1
exit 0
