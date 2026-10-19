"""M2-S6 oracle O5 (migration/m2-s6-design.md rev. 2, section 5): the INET 4.7.0 gPTP SLAVE_NODE path
(linklayer/ieee8021as/Gptp.cc; the M2-S3 model rules of inet_model.SlaveModel) running on O1 clocks:
a drifting raw clock U_S and a tick-quantized settable clock C_S on one oscillator, StepClockServo
steps with round-up and tick-phase resets (clock/servo/StepClockServo.cc, clock/model/SettableClock.cc).

Readings are taken at the first bit of the frame (receptionStarted / transmissionStarted, Gptp.cc:531-
634); messages are processed when their reception ends (handleMessage). Inputs are the slave's own PCAP
and the values the slave read from the frames' chunks: DS-TT t2/t3 (ps), POT (ps) and cf (ps)."""
import clock_model as K
import inet_model as M
import m2s6_clocks as MC

SYNC, FU, REQ, RESP, RFU = 0, 8, 2, 3, 10


class SlaveO5:
    def __init__(self, nconf, end, drift_vec=None, name="slave", smoothing=0.1):
        self.nc = MC.NodeClocks(nconf, end, drift_vec, name)
        self.servo = nconf["servo"]
        self.smoothing = smoothing
        self.pdelay = -1 * 10 ** 12          # Gptp.h:184
        self.nrr_e = 0
        self.gm_e = 0
        self.prev_resp = None
        self.prev_src = self.prev_loc = None
        self.req = self.resp = self.sync = None
        self.own_spi = None
        self.out = {"pdelay": [], "nrr": [], "gm": [], "fu": [], "ignored": [], "exchanges": [], "sync_overwritten": 0}

    def run(self, sl_frames, t2_of, t3_of, pot_of, cf_of, sample_ms=True):
        """sl_frames: slave eth[0] PCAP frames (check_m2s5.frames); t2_of/t3_of(seq) -> the DS-TT's
        Pdelay_Resp requestReceiptTimestamp / Resp_FU responseOriginTimestamp in ps (what the slave read);
        pot_of(seq), cf_of(seq) -> Follow_Up POT and correctionField in ps."""
        ev = []
        for f in sl_frames:
            g = f["g"]
            if g is None:
                continue
            if f["dir"] == 2 and g["type"] == REQ:
                ev.append((f["start"], 0, "reqtx", g["seq"], g["spi"]))
            elif f["dir"] == 1 and f["f"]["fcs_ok"] and g["domain"] == 0:
                s = g["seq"]
                if g["type"] == RESP:
                    ev.append((f["start"], 0, "resp_start", s))
                    ev.append((f["end"], 1, "resp", s, g["reqPort"]))
                elif g["type"] == RFU:
                    ev.append((f["end"], 1, "rfu", s, g["reqPort"]))
                elif g["type"] == SYNC:
                    ev.append((f["start"], 0, "sync_start", s))
                    ev.append((f["end"], 1, "sync", s))
                elif g["type"] == FU:
                    ev.append((f["end"], 1, "fu", s))
        if sample_ms:
            t = 0
            while t <= self.nc.end:
                ev.append((t, 2, "ms", None))
                t += MC.MS
        ev.sort(key=lambda e: (e[0], e[1]))
        nc = self.nc
        for c in (nc.C, nc.U):
            c.samples_init = c.at(0)
            c.ms_values = []
        pend_resp_t4 = {}
        sync_read = {}
        for e in ev:
            t, kind = e[0], e[2]
            if kind == "ms":
                nc.advance(t, inclusive=True)
                nc.C.ms_values.append((t, nc.C.at(t)))
                nc.U.ms_values.append((t, nc.U.at(t)))
            elif kind == "reqtx":                       # transmissionStarted (:607-614): t1 = localClock
                self.req = {"seq": e[3], "t1": nc.read_U(t), "s1": t, "g1": nc.U.gamma(t)}
                self.own_spi = e[4]
                self.resp = None
            elif kind == "resp_start":                  # receptionStarted (:541-547): t4 = localClock
                pend_resp_t4[e[3]] = (nc.read_U(t), t, nc.U.gamma(t))
            elif kind == "resp":                        # processPdelayResp (:386-399)
                s, rp = e[3], e[4]
                if self.req is None or rp != self.own_spi or s != self.req["seq"]:
                    self.out["ignored"].append(("resp", t, s))
                    continue
                t4, s4, g4 = pend_resp_t4[s]
                self.resp = {"seq": s, "t4": t4, "s4": s4, "g4": g4, "t2": t2_of(s)}
            elif kind == "rfu":                         # processPdelayRespFollowUp (:401-417)
                s, rp = e[3], e[4]
                if self.req is None or self.resp is None or rp != self.own_spi or s != self.req["seq"]:
                    self.out["ignored"].append(("rfu", t, s))
                    continue
                t3, t4 = t3_of(s), self.resp["t4"]
                valid_before = self.prev_resp is not None
                if self.prev_resp is not None:          # computeNeighborRateRatio (:439-458)
                    self.nrr_e = K.from_integer_ratio(t3 - self.prev_resp[0], t4 - self.prev_resp[1])
                    self.out["nrr"].append((t, K.to_double(self.nrr_e)))
                self.prev_resp = (t3, t4)
                T = t4 - self.req["t1"]                 # computePropTime (:461-484)
                cur = M.trunc_div2(K.mul_round(T, self.nrr_e) - (t3 - self.resp["t2"]))
                prev = self.pdelay
                if self.pdelay == -1 * 10 ** 12:
                    self.pdelay = cur
                else:
                    self.pdelay = M.simtime_times_double(cur, self.smoothing) + M.simtime_times_double(self.pdelay, 1 - self.smoothing)
                self.out["pdelay"].append((t, self.pdelay))
                self.out["exchanges"].append({"seq": s, "t": t, "t1": self.req["t1"], "t2": self.resp["t2"], "t3": t3, "t4": t4,
                                              "s1": self.req["s1"], "s4": self.resp["s4"], "g1": self.req["g1"], "g4": self.resp["g4"],
                                              "nrr_e": self.nrr_e,
                                              "nrr_valid": valid_before, "d": cur, "pd_prev": prev, "pd": self.pdelay})
            elif kind == "sync_start":                  # receptionStarted (:554-560)
                sync_read[e[3]] = (nc.read_C(t), nc.read_U(t), t)
            elif kind == "sync":                        # processSync (:353-359)
                if self.sync is not None:
                    self.out["sync_overwritten"] += 1
                t2, loc, s2 = sync_read[e[3]]
                self.sync = {"seq": e[3], "t2": t2, "loc": loc, "s2": s2}
            elif kind == "fu":                          # processFollowUp (:361-374)
                s = e[3]
                if self.sync is None or s != self.sync["seq"]:
                    self.out["ignored"].append(("fu", t, s))
                    self.sync = None
                    continue
                pot, cf = pot_of(s), cf_of(s)
                pd = self.pdelay
                src = pot + cf + pd                     # computeGmRateRatio (:419-437)
                loc = self.sync["loc"]
                gm_prev = self.gm_e
                if self.prev_src is not None:
                    self.gm_e = K.from_integer_ratio(src - self.prev_src, loc - self.prev_loc)
                    self.out["gm"].append((t, K.to_double(self.gm_e)))
                prev_src, prev_loc = self.prev_src, self.prev_loc
                self.prev_src, self.prev_loc = src, loc
                diff = self.sync["t2"] - src            # synchronize (:196-226)
                rec = {"seq": s, "s2": self.sync["s2"], "sF": t, "t2": self.sync["t2"], "loc": loc, "pot": pot, "cf": cf,
                       "pd": pd, "src": src, "o": diff, "gm_e": self.gm_e, "gm_e_prev": gm_prev,
                       "prev_src": prev_src, "prev_loc": prev_loc}
                if self.servo == "step":                # StepClockServo::adjustClockForDifference
                    ppm = K.to_ppm(self.gm_e)
                    now = nc.read_C(t)
                    old, new, r = nc.step(t, now - diff, ppm, True)
                    rec.update(old=old, new=new, reset=r, ppm=ppm)
                elif self.servo in ("testNoRate", "testNegRate"):   # nascTime TestClockServo (TEST ONLY)
                    ppm = 0.0 if self.servo == "testNoRate" else -K.to_ppm(self.gm_e)
                    now = nc.read_C(t)
                    old, new, r = nc.step(t, now - diff, ppm, True)
                    rec.update(old=old, new=new, reset=r, ppm=ppm)
                self.out["fu"].append(rec)
                self.sync = None
        nc.finish()
        nc.C.value_end, nc.U.value_end = nc.C.at(nc.end), nc.U.at(nc.end)
        return self


def compare(m, R, sln):
    """S rows: every recorded slave value = O5. Returns {name: (ok, n, detail)}."""
    out = {}
    v = lambda mod, name: R.vecv(f"{sln}.{mod}", name)  # noqa: E731
    rec_pd = [(t, float(x)) for t, x in v("gptp", "pdelay:vector")]
    mod_pd = [(t, MC.dbl(p)) for t, p in m.out["pdelay"]]
    out["pdelay"] = (rec_pd == mod_pd, len(rec_pd), "" if rec_pd == mod_pd else f"{len(rec_pd)} vs {len(mod_pd)}")
    for key, name in (("nrr", "neighborRateRatio:vector"), ("gm", "gmRateRatio:vector")):
        rec = [(t, float(x)) for t, x in v("gptp", name)]
        out[key] = (rec == m.out[key], len(rec), "" if rec == m.out[key] else
                    str([(a, b) for a, b in zip(rec, m.out[key]) if a != b][:2]) + f" {len(rec)} vs {len(m.out[key])}")
    rec_comp = [(t, float(x)) for t, x in v("clock", "oscillatorCompensationChanged:vector")]
    mod_comp = [(0, 0.0)] + [(st[0], st[3]) for st in m.nc.steps]
    out["compensation"] = (rec_comp == mod_comp, len(rec_comp) - 1, "" if rec_comp == mod_comp else f"{len(rec_comp)} vs {len(mod_comp)}")
    for clk, sub, emit in ((m.nc.C, "clock", True), (m.nc.U, "clock.underlyingClock", True)):
        fixed, alt = MC.predicted_samples(m.nc, clk, emit)
        ok, n, bad = MC.compare_samples(v(sub, "timeChanged:vector"), fixed, alt)
        out[sub] = (ok, n, str(bad))
    return out
