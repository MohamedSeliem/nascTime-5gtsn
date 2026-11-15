// S5-2: evaluates OMNeT++'s own PatternMatcher (omnetpp::common, dottedpath = fullstring = casesensitive = true, the
// mode of per-object ini keys) on "pattern<TAB>path" lines from stdin; prints "pattern<TAB>path<TAB>0|1". Used once to
// produce omnetpp-pattern-xcheck.tsv, against which m2s72_rngaudit.match() is tested. Build (OMNeT++ 6.5.0):
//   g++ -std=c++17 -I$OMNETPP_ROOT/src/common -I$OMNETPP_ROOT/include omnetpp_pattern_xcheck.cc \
//       -L$OMNETPP_ROOT/lib -loppcommon -Wl,-rpath,$OMNETPP_ROOT/lib -o xcheck
#include <iostream>
#include <string>
#include "patternmatcher.h"
int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        auto tab = line.find('\t');
        if (tab == std::string::npos) continue;
        std::string pat = line.substr(0, tab), path = line.substr(tab + 1);
        omnetpp::common::PatternMatcher m;
        m.setPattern(pat.c_str(), true, true, true);
        std::cout << pat << '\t' << path << '\t' << (m.matches(path.c_str()) ? 1 : 0) << '\n';
    }
    return 0;
}
