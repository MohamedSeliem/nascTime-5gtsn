//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
// M2B-4 TEST-ONLY unit driver of TtEgressPairer (src/nasctime/m2/TtEgressPairer.cc), no simulation. Built and run by
// simulations/m2/check/test_m2b4_pairer.py. One line per case: "CASE <PASS|FAIL> <mode> <name> / <outcome>".
// Steps: P push (tree, t, pcp), p raw insertion (bypasses the enqueue check), D dequeue, S start, E end
// (E removes the record at the matched index, as TtTimestampProcessor does), V verifyTransmitted of the record
// about to end (etherType/pcp/vid given in the step).
//

#include <cstdio>
#include <string>
#include <vector>

#include "TtEgressPairer.h"

using namespace nasctime;
using omnetpp::SimTime;

struct Step { char op; long tree; double t; int pcp = -1; int etherType = 0x8100, vid = 42; };
struct Case { const char *mode; const char *name; std::vector<Step> steps; const char *expectedError; };

int main()
{
    SimTime::setScaleExp(-12);
    using E = TtEgressPairer;
    std::vector<Case> cases = {
        // ---- FIFO mode: the accepted M2-S1 self-test cases (TtTimestampProcessor::selfTestPairer), unchanged outcomes
        {"fifo", "idle port: one frame", {{'P', 1, 1}, {'D', 1, 1}, {'S', 1, 1}, {'E', 1, 2}}, nullptr},
        {"fifo", "two frames queued in FIFO order", {{'P', 1, 1}, {'P', 2, 1}, {'D', 1, 1}, {'S', 1, 1}, {'E', 1, 2}, {'D', 2, 2}, {'S', 2, 3}, {'E', 2, 4}}, nullptr},
        {"fifo", "event for an unknown frame", {{'P', 1, 1}, {'D', 9, 1}}, "orphan"},
        {"fifo", "a second frame with a pending tree id enters the queue", {{'P', 5, 1}, {'P', 5, 1}}, "ambiguous enqueue"},
        {"fifo", "two pending records share a tree id (bypassing the enqueue check)", {{'P', 5, 1}, {'p', 5, 1}, {'D', 5, 1}}, "ambiguous MAC dequeue"},
        {"fifo", "second frame dequeued first", {{'P', 1, 1}, {'P', 2, 1}, {'D', 2, 1}}, "out-of-order"},
        {"fifo", "same event twice", {{'P', 1, 1}, {'D', 1, 1}, {'D', 1, 1}}, "duplicate"},
        {"fifo", "start before dequeue", {{'P', 1, 1}, {'S', 1, 1}}, "no MAC dequeue"},
        {"fifo", "end of the second frame before the first", {{'P', 1, 1}, {'P', 2, 1}, {'D', 1, 1}, {'S', 1, 1}, {'D', 2, 1}, {'S', 2, 1}, {'E', 2, 2}}, "out-of-order"},
        {"fifo", "event before the frame entered the queue", {{'P', 1, 2}, {'D', 1, 1}}, "time order"},
        // FIFO mode rejects the valid TAS overtaking (the observed M2B-3 failure)
        {"fifo", "cross-class overtaking (valid under TAS) is refused by the FIFO rule", {{'P', 1, 1, 0}, {'P', 2, 1, 5}, {'D', 2, 2}}, "out-of-order MAC dequeue"},

        // ---- TAS mode: valid sequences
        {"tas", "one frame", {{'P', 1, 1, 5}, {'D', 1, 1}, {'S', 1, 1}, {'E', 1, 2}}, nullptr},
        {"tas", "cross-class overtaking: PCP 5 frame leaves before an older PCP 0 frame", {{'P', 1, 1, 0}, {'P', 2, 1, 5}, {'D', 2, 2}, {'S', 2, 2}, {'E', 2, 3}, {'D', 1, 4}, {'S', 1, 4}, {'E', 1, 5}}, nullptr},
        {"tas", "untagged (gPTP) overtakes held PCP 5 and PCP 0 frames, then they leave in per-class order", {{'P', 1, 1, 5}, {'P', 2, 1, 0}, {'P', 3, 2, 5}, {'P', 4, 2, -1}, {'D', 4, 2}, {'S', 4, 2}, {'E', 4, 3}, {'D', 2, 4}, {'S', 2, 4}, {'E', 2, 5}, {'D', 1, 6}, {'S', 1, 6}, {'E', 1, 7}, {'D', 3, 8}, {'S', 3, 8}, {'E', 3, 9}}, nullptr},
        {"tas", "back-to-back: the next start at the instant the previous transmission ends", {{'P', 1, 1, 5}, {'P', 2, 1, 5}, {'D', 1, 1}, {'S', 1, 1}, {'E', 1, 2}, {'D', 2, 2}, {'S', 2, 2}, {'E', 2, 3}}, nullptr},
        {"tas", "frames in FIFO order (TAS mode accepts the FIFO case)", {{'P', 1, 1, 0}, {'P', 2, 1, 5}, {'D', 1, 1}, {'S', 1, 1}, {'E', 1, 2}, {'D', 2, 2}, {'S', 2, 2}, {'E', 2, 3}}, nullptr},
        {"tas", "transmitted identity equal to the record", {{'P', 1, 1, 5}, {'D', 1, 1}, {'S', 1, 1}, {'V', 1, 0, 5}, {'E', 1, 2}}, nullptr},
        // ---- TAS mode: negative controls (each must fail for the stated reason)
        {"tas", "within-class overtaking (PCP 5 behind PCP 5)", {{'P', 1, 1, 5}, {'P', 2, 1, 5}, {'D', 2, 2}}, "out-of-order MAC dequeue of tree id 2 within PCP 5"},
        {"tas", "orphan dequeue", {{'P', 1, 1, 5}, {'D', 9, 2}}, "orphan MAC dequeue of tree id 9"},
        {"tas", "orphan transmission end", {{'P', 1, 1, 5}, {'E', 9, 2}}, "orphan transmissionEnded of tree id 9"},
        {"tas", "duplicate dequeue", {{'P', 1, 1, 5}, {'D', 1, 2}, {'D', 1, 2}}, "duplicate MAC dequeue of tree id 1"},
        {"tas", "duplicate transmission end", {{'P', 1, 1, 5}, {'P', 2, 1, 5}, {'D', 1, 2}, {'S', 1, 2}, {'E', 1, 3}, {'E', 1, 3}}, "orphan transmissionEnded of tree id 1"},
        {"tas", "duplicate transmission end (record still pending)", {{'P', 1, 1, 5}, {'D', 1, 2}, {'S', 1, 2}, {'e', 1, 3}, {'E', 1, 3}}, "duplicate transmissionEnded of tree id 1"},
        {"tas", "ambiguous tree id at enqueue", {{'P', 5, 1, 5}, {'P', 5, 1, 0}}, "ambiguous enqueue of tree id 5"},
        {"tas", "ambiguous tree id (two pending records)", {{'P', 5, 1, 5}, {'p', 5, 1, 0}, {'D', 5, 2}}, "ambiguous MAC dequeue of tree id 5"},
        {"tas", "start before dequeue (out-of-order events within a frame)", {{'P', 1, 1, 5}, {'S', 1, 2}}, "order violation for transmissionStarted of tree id 1: no MAC dequeue yet"},
        {"tas", "missing transmission start (end after dequeue only)", {{'P', 1, 1, 5}, {'D', 1, 2}, {'E', 1, 3}}, "order violation for transmissionEnded of tree id 1: no transmission start yet"},
        {"tas", "impossible overlapping transmissions", {{'P', 1, 1, 0}, {'P', 2, 1, 5}, {'D', 1, 2}, {'S', 1, 2}, {'D', 2, 2}, {'S', 2, 2}}, "overlapping transmission: transmissionStarted of tree id 2 while tree id 1"},
        {"tas", "start out of the dequeue sequence", {{'P', 1, 1, 0}, {'P', 2, 1, 5}, {'D', 1, 2}, {'D', 2, 2}, {'S', 2, 2}}, "out-of-sequence transmissionStarted of tree id 2: tree id 1 was dequeued earlier"},
        {"tas", "dequeue before the frame entered the queue", {{'P', 1, 2, 5}, {'D', 1, 1}}, "time order violation for MAC dequeue of tree id 1"},
        {"tas", "transmission end before its start", {{'P', 1, 1, 5}, {'D', 1, 2}, {'S', 1, 3}, {'E', 1, 2.5}}, "time order violation for transmissionEnded of tree id 1"},
        {"tas", "incorrect frame identity at the end (PCP 0 twin transmitted for a PCP 5 record)", {{'P', 1, 1, 5}, {'D', 1, 2}, {'S', 1, 2}, {'V', 1, 0, 0}}, "identity of the transmitted frame (EtherType 33024, PCP 0, VID 42) differs from the record of tree id 1"},
        {"tas", "incorrect frame identity at the end (VID)", {{'P', 1, 1, 5}, {'D', 1, 2}, {'S', 1, 2}, {'V', 1, 0, 5, 0x8100, 7}}, "VID 7) differs from the record of tree id 1"},
    };
    int passed = 0;
    for (const auto& c : cases) {
        TtEgressPairer p;
        p.mode = std::string(c.mode) == "tas" ? E::TAS : E::FIFO;
        std::string error;
        for (const auto& s : c.steps) {
            if (s.op == 'P' || s.op == 'p') {
                TtPortRecord r;
                r.treeId = s.tree;
                r.tSlot = s.t;
                r.pcp = s.pcp;
                r.etherType = 0x8100;
                r.vid = 42;
                if (s.op == 'p')
                    p.fifo.push_back(r);
                else
                    error = p.push(r);
            }
            else if (s.op == 'V') {
                size_t i = 0;
                while (i < p.fifo.size() && p.fifo[i].treeId != s.tree)
                    i++;
                error = i < p.fifo.size() ? p.verifyTransmitted(p.fifo[i], s.etherType, s.pcp, s.vid) : "no record";
            }
            else {
                size_t index = 0;
                E::Event e = s.op == 'D' ? E::DEQUEUE : s.op == 'S' ? E::TX_START : E::TX_END;
                error = p.match(e, s.tree, s.t, index);
                if (error.empty() && s.op == 'E')         // as the processor: remove the transmitted record
                    p.fifo.erase(p.fifo.begin() + index);
                // 'e': transmission end recorded but the record kept (to provoke a duplicate on the same record)
            }
            if (!error.empty())
                break;
        }
        bool ok = c.expectedError == nullptr ? error.empty() && p.fifo.empty() : error.find(c.expectedError) != std::string::npos;
        passed += ok;
        printf("CASE %s %s %s / %s\n", ok ? "PASS" : "FAIL", c.mode, c.name, error.empty() ? "accepted" : error.c_str());
    }
    printf("\nM2B-4 pairer unit cases: %d / %zu PASS, %zu FAIL\n", passed, cases.size(), cases.size() - passed);
    return passed == (int)cases.size() ? 0 : 1;
}
