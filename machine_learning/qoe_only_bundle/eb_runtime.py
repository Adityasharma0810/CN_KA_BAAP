"""eb_runtime.py - plug-in inference for the three Experience Budget ML models.

Usage (after unzipping the bundle, with eb_runtime.py next to the model files):

    from eb_runtime import ExperienceBudgetModels
    eb = ExperienceBudgetModels.load("eb_bundle")          # reads config.json + *.joblib
    # 1) flow classifier (size/timing/direction only; never payloads)
    bins = eb.bins_from_packets(timestamps, sizes, directions)      # directions: +1 upstream, -1 downstream
    out = eb.classify_flow(bins, is_udp=True, dst_port=443)          # {'label','confidence','source'}
    # 2) capacity forecaster (call once per minute with the Kalman capacity estimate)
    fc = eb.capacity_forecaster(nominal_mbps=100)
    fc.update(cap_obs_mbps, minute_of_day, day_of_week)
    print(fc.recommend())                                           # {'rate_mbps','mode','reason',...}
    # 3) QoE degradation warner (call once per device per second)
    w = eb.qoe_warner()
    print(w.push("D1", t_sec, record))                              # {'alert','p_red','state',...}

Every model has an `enabled` flag in config.json. If the training notebook decided a model did not earn its place,
the runtime silently falls back to the deterministic baseline (port rules / reactive shaper / QoE-level rule).
"""
from __future__ import annotations

import collections
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

__version__ = "1.0"
CLASSES = ["call", "game", "stream", "bulk", "other"]
BIN_S = 0.1
WINDOW_BINS = 100            # 10 s window of 100 ms bins, anchored at the flow's first packet
SPD = 1440                   # capacity samples per day (1-minute resolution)

# ============================================================== 1. FLOW CLASSIFIER ====================================

PORT_RULES = {  # deterministic baseline: well-known ports -> class (anything else is unidentifiable)
    **{p: "call" for p in (3478, 3479, 5060, 5061, 5004, 5005, 19302, 19303, 19304, 19305, 19306, 19307, 19308, 19309)},
    **{p: "game" for p in (27015, 27016, 27017, 27018, 27019, 27020, 3074, 7777, 25565, 9339, 3659)},
    **{p: "stream" for p in (554, 1935, 8554, 8008)},
    **{p: "bulk" for p in (20, 21, 22, 873, 6881, 6882, 6883, 6884, 6885, 6886, 6887, 6888, 6889, 445, 548)},
    **{p: "other" for p in (53, 80, 123, 143, 25, 110, 993, 1883, 8883, 5353)},
}


def port_rule(dst_port):
    """Deterministic baseline. Returns a class or None when the port says nothing (e.g. 443, ephemeral)."""
    return PORT_RULES.get(int(dst_port)) if dst_port is not None else None


def bins_from_packets(timestamps, sizes, directions, observed_s=None, window_s=10.0, bin_s=BIN_S):
    """Turn raw packet metadata into the per-100 ms bins the classifier uses (no payloads).
    timestamps: seconds; sizes: bytes; directions: +1 = upstream (home -> internet), -1 = downstream.
    observed_s: how long the flow has been observed. Pass window_s if the flow is still open (default: until last packet)."""
    ts = np.asarray(timestamps, float); sz = np.asarray(sizes, float); dr = np.asarray(directions)
    n = int(round(window_s / bin_s))
    out = {k: np.zeros(n) for k in ("pk_dn", "pk_up", "by_dn", "by_up", "ss_dn", "ss_up")}
    if len(ts) == 0:
        out["n_bins"] = 1
        return out
    order = np.argsort(ts, kind="stable"); ts, sz, dr = ts[order], sz[order], dr[order]
    rel = ts - ts[0]; keep = rel < window_s
    idx = np.minimum((rel[keep] / bin_s + 1e-9).astype(int), n - 1); sz, dr = sz[keep], dr[keep]   # +1e-9: packets exactly on a bin edge must not fall into the previous bin
    up = dr > 0
    for tag, m in (("up", up), ("dn", ~up)):
        np.add.at(out[f"pk_{tag}"], idx[m], 1.0)
        np.add.at(out[f"by_{tag}"], idx[m], sz[m])
        np.add.at(out[f"ss_{tag}"], idx[m], sz[m] ** 2)
    if observed_s is None:
        observed_s = float(rel[keep].max()) + bin_s if keep.any() else bin_s
    out["n_bins"] = int(max(1, min(n, math.ceil(observed_s / bin_s - 1e-9))))   # -1e-9: 12 x 0.1 s must give 12 bins, not 13
    return out


def _autocorr(x, k):
    x = np.asarray(x, float); x = x - x.mean()
    den = float((x * x).sum())
    if len(x) <= k or den < 1e-9:
        return 0.0
    return float((x[:-k] * x[k:]).sum() / den)


FLOW_FEATURES = ["is_udp", "n_bins", "log_pk", "log_by", "up_frac_bytes", "up_frac_pkts", "mean_sz", "std_sz", "mean_sz_dn",
                 "mean_sz_up", "log_rate_dn", "log_rate_up", "pk_rate", "cv_b", "peak_ratio", "idle_frac", "ac1", "ac5",
                 "cv_pk_dn", "cv_pk_up", "n_bursts", "mean_burst_len", "dn_up_pk_ratio"]


def flow_features_from_bins(b, is_udp):
    """23 size/timing/direction summary features from a flow's first-10-second bins. Used identically in training and at run time."""
    eps = 1e-9
    L = int(max(1, min(int(b["n_bins"]), len(b["pk_dn"]))))
    pdn, pup = np.asarray(b["pk_dn"][:L], float), np.asarray(b["pk_up"][:L], float)
    bdn, bup = np.asarray(b["by_dn"][:L], float), np.asarray(b["by_up"][:L], float)
    sdn, sup = np.asarray(b["ss_dn"][:L], float), np.asarray(b["ss_up"][:L], float)
    tpd, tpu, tbd, tbu = pdn.sum(), pup.sum(), bdn.sum(), bup.sum()
    tpk, tby = tpd + tpu, tbd + tbu
    mean_sz = tby / (tpk + eps)
    var_sz = max((sdn.sum() + sup.sum()) / (tpk + eps) - mean_sz ** 2, 0.0)
    byb, pkb = bdn + bup, pdn + pup
    mean_b = byb.mean(); dur = L * BIN_S
    act = pkb > 0
    trans = int(np.sum(act[1:] & ~act[:-1])) + int(act[0])
    f = {
        "is_udp": float(is_udp), "n_bins": float(L), "log_pk": math.log1p(tpk), "log_by": math.log1p(tby),
        "up_frac_bytes": tbu / (tby + eps), "up_frac_pkts": tpu / (tpk + eps), "mean_sz": mean_sz, "std_sz": math.sqrt(var_sz),
        "mean_sz_dn": tbd / (tpd + eps), "mean_sz_up": tbu / (tpu + eps),
        "log_rate_dn": math.log1p(tbd * 8 / dur), "log_rate_up": math.log1p(tbu * 8 / dur), "pk_rate": tpk / dur,
        "cv_b": float(byb.std() / (mean_b + eps)), "peak_ratio": float(byb.max() / (mean_b + eps)), "idle_frac": float((~act).mean()),
        "ac1": _autocorr(byb, 1), "ac5": _autocorr(byb, 5),
        "cv_pk_dn": float(pdn.std() / (pdn.mean() + eps)), "cv_pk_up": float(pup.std() / (pup.mean() + eps)),
        "n_bursts": float(trans), "mean_burst_len": float(act.sum() / max(trans, 1)),
        "dn_up_pk_ratio": math.log((tpd + 1) / (tpu + 1)),
    }
    return f


class FlowClassifier:
    """ML classifier with confidence + 'unknown' abstention, deterministic port-rule fallback, and a correction buffer."""

    def __init__(self, bundle=None, enabled=True):
        self.enabled = bool(enabled and bundle is not None)
        self.model = bundle["model"] if bundle else None
        self.classes = list(bundle["classes"]) if bundle else CLASSES
        self.features = list(bundle["features"]) if bundle else FLOW_FEATURES
        self.tau = float(bundle["abstain_tau"]) if bundle else 1.0
        self.corrections = []

    def classify_features(self, X, dst_ports=None):
        """X: DataFrame with FLOW_FEATURES columns. Returns a DataFrame with label, confidence, source."""
        n = len(X); labels = ["unknown"] * n; conf = np.zeros(n); src = ["abstain"] * n
        ports = list(dst_ports) if dst_ports is not None else [None] * n
        if self.enabled:
            P = self.model.predict_proba(X[self.features])
            conf = P.max(axis=1); top = np.asarray(self.classes)[P.argmax(axis=1)]
        for i in range(n):
            if self.enabled and conf[i] >= self.tau:
                labels[i], src[i] = str(top[i]), "ml"
            else:
                r = port_rule(ports[i])
                if r is not None:
                    labels[i], src[i] = r, "port_rule"
        return pd.DataFrame({"label": labels, "confidence": conf, "source": src})

    def classify(self, bins, is_udp, dst_port=None):
        X = pd.DataFrame([flow_features_from_bins(bins, is_udp)])
        return self.classify_features(X, [dst_port]).iloc[0].to_dict()

    def add_correction(self, bins, is_udp, true_label):
        """The 'wrong label?' button: stores the flow features + the user's label; export and retrain later."""
        self.corrections.append({**flow_features_from_bins(bins, is_udp), "label": true_label})

    def export_corrections(self, path):
        pd.DataFrame(self.corrections).to_csv(path, index=False)


# ============================================================== 2. CAPACITY FORECASTER ================================

class CapacityForecaster:
    """Online, stateful. Call update() once per minute with the capacity estimate; recommend() returns the shaper rate.
    Needs 3 days of history before the ML forecast activates (use warm_start() with past router logs); until then, and whenever the
    forecast interval is wide, it behaves exactly like the reactive controller."""

    def __init__(self, bundle, nominal_mbps, enabled=True):
        self.enabled = bool(enabled and bundle is not None)
        self.b = bundle; self.cnom = float(nominal_mbps)
        self.h = int(bundle["horizon_min"]); self.alpha, self.gamma = bundle["hw_params"]
        self.feats = list(bundle["feats"]); self.models = bundle["models"]
        self.gate_width = float(bundle["gate_width"]); self.safety = float(bundle.get("safety", 0.95))
        self.x = collections.deque(maxlen=3 * SPD + 1)          # normalised observations
        self._init_buf = []; self.level = None; self.season = None; self.hw_fc = float("nan")
        self.tod = 0; self.dow = 0; self.last_raw = float("nan"); self.n = 0

    def update(self, cap_obs_mbps, minute_of_day, day_of_week):
        y = float(cap_obs_mbps); self.last_raw = y; self.tod = int(minute_of_day); self.dow = int(day_of_week)
        self.x.append(y / self.cnom); self.n += 1
        if self.season is None:
            self._init_buf.append((self.tod, y))
            if len(self._init_buf) == SPD:                       # first full day = Holt-Winters initialisation
                vals = np.array([v for _, v in self._init_buf]); self.level = float(vals.mean())
                self.season = np.zeros(SPD)
                for tod, v in self._init_buf: self.season[tod] = v - self.level
                self._init_buf = []
            return
        k = self.tod; prev = self.level
        self.level = self.alpha * (y - self.season[k]) + (1 - self.alpha) * prev
        self.season[k] = self.gamma * (y - self.level) + (1 - self.gamma) * self.season[k]
        self.hw_fc = self.level + self.season[(k + self.h) % SPD]

    def warm_start(self, history_mbps, first_minute_of_day, first_day_of_week):
        """Feed past 1-minute estimates in order (>= 3 days recommended)."""
        for i, v in enumerate(history_mbps):
            m = first_minute_of_day + i
            self.update(v, m % SPD, (first_day_of_week + m // SPD) % 7)

    def _lag(self, k):
        return self.x[-1 - k] if len(self.x) > k else float("nan")

    def ready(self):
        return len(self.x) > 3 * SPD - self.h and not math.isnan(self.hw_fc)

    def features(self):
        x = self.x; xt = x[-1]; h = self.h
        last = list(x)[-15:]
        tgt_tod = (self.tod + h) % SPD
        y1, y2, y3 = self._lag(SPD - h), self._lag(2 * SPD - h), self._lag(3 * SPD - h)
        tgt_dow = (self.dow + (self.tod + h) // SPD) % 7
        hwn = self.hw_fc / self.cnom
        f = {"x_t": xt, **{f"x_lag{k}": self._lag(k) for k in (1, 2, 3, 5, 10, 15)},
             "roll_mean5": float(np.mean(last[-5:])) if len(x) >= 5 else float("nan"),
             "roll_std5": float(np.std(last[-5:], ddof=1)) if len(x) >= 5 else float("nan"),
             "roll_min15": float(np.min(last)) if len(x) >= 15 else float("nan"),
             "diff5": xt - self._lag(5),
             "tgt_tod_sin": math.sin(2 * math.pi * tgt_tod / SPD), "tgt_tod_cos": math.cos(2 * math.pi * tgt_tod / SPD),
             "tod_sin": math.sin(2 * math.pi * self.tod / SPD), "tod_cos": math.cos(2 * math.pi * self.tod / SPD),
             "tgt_dow": float(tgt_dow), "tgt_weekend": float(tgt_dow >= 5),
             "yday_at_tgt": y1, "mean3d_at_tgt": float(np.mean([y1, y2, y3])), "hw_fc": hwn, "hw_minus_x": hwn - xt}
        return f

    def recommend(self):
        if self.n == 0:
            raise RuntimeError("call update() at least once first")
        base = {"horizon_min": self.h, "last_estimate_mbps": self.last_raw}
        reactive = self.safety * self.last_raw
        if not self.enabled:
            return {**base, "rate_mbps": reactive, "mode": "reactive", "reason": "forecaster disabled by the training verdict (config.json)"}
        if not self.ready():
            return {**base, "rate_mbps": reactive, "mode": "reactive", "reason": "warming up: need 3 days of history"}
        row = pd.DataFrame([self.features()])[self.feats]
        q10, q50, q90 = (float(self.models[k].predict(row)[0]) for k in ("q10", "q50", "q90"))
        width = q90 - q10
        out = {**base, "q10_mbps": q10 * self.cnom, "q50_mbps": q50 * self.cnom, "q90_mbps": q90 * self.cnom, "interval_width": width}
        if width <= self.gate_width:
            xt = self.x[-1]
            return {**out, "rate_mbps": self.safety * min(xt, q50) * self.cnom, "mode": "forecast", "reason": "forecast confident (narrow interval)"}
        return {**out, "rate_mbps": reactive, "mode": "reactive", "reason": "forecast interval too wide: falling back to reactive"}


# ============================================================== 3. QoE DEGRADATION WARNER =============================

QOE_FEATURES = ["qdelay_ms", "qd_d3", "qd_d10", "qd_max10", "rho", "rho_d5", "cap", "cap_ratio5", "cap_ratio15", "mode_fq",
                "n_call_net", "n_game_net", "n_stream_net", "n_bulk_net", "delay", "jitter", "loss", "loss_ema", "rtt_d3",
                "thr_over_cap", "n_flows", "has_call", "has_game", "has_stream", "has_bulk", "qoe_now", "qoe_d3", "qoe_d10",
                "qoe_min10", "buf_min", "buf_d3"]
_NAN = float("nan")


class QoEWarner:
    """Per-device, per-second. push(device, t, record) -> {'state','alert','p_red',...}.
    record keys (network-level, always): qdelay_ms, rho, cap, mode_fq, n_call_net, n_game_net, n_stream_net, n_bulk_net.
    record keys (device-level, None/omitted if the device has no active flow): delay, jitter, loss, thr, n_flows, has_call,
    has_game, has_stream, has_bulk, qoe (device QoE 0-1), buf_min (min stream playback buffer in seconds, or None)."""

    def __init__(self, bundle, horizon_s=10, enabled=True):
        self.enabled = bool(enabled and bundle is not None); self.b = bundle
        self.horizon = int(horizon_s); self.red = float(bundle["red_threshold"]) if bundle else 0.5
        self.features = list(bundle["features"]) if bundle else QOE_FEATURES
        self.model = bundle["models"][self.horizon] if bundle else None
        self.tau = float(bundle["thresholds"][self.horizon]) if bundle else 1.0
        self.fallback_x = float(bundle["fallback_qoe_level"][self.horizon]) if bundle else 0.75
        self.state = {}

    def reset(self, device=None):
        if device is None: self.state.clear()
        else: self.state.pop(device, None)

    def _build(self, st):
        h = st["hist"]; cur = h[-1]
        def lag(key, k): return h[-1 - k][key] if len(h) > k else _NAN
        qd = [r["qdelay_ms"] for r in list(h)[-10:]]
        q10 = [r["qoe"] for r in list(h)[-10:] if not math.isnan(r["qoe"])]
        buf_raw = cur["buf_raw"]
        f = {"qdelay_ms": cur["qdelay_ms"], "qd_d3": cur["qdelay_ms"] - lag("qdelay_ms", 3), "qd_d10": cur["qdelay_ms"] - lag("qdelay_ms", 10),
             "qd_max10": max(qd), "rho": cur["rho"], "rho_d5": cur["rho"] - lag("rho", 5), "cap": cur["cap"],
             "cap_ratio5": cur["cap"] / lag("cap", 5) if not math.isnan(lag("cap", 5)) else _NAN,
             "cap_ratio15": cur["cap"] / lag("cap", 15) if not math.isnan(lag("cap", 15)) else _NAN,
             "mode_fq": cur["mode_fq"], "n_call_net": cur["n_call_net"], "n_game_net": cur["n_game_net"],
             "n_stream_net": cur["n_stream_net"], "n_bulk_net": cur["n_bulk_net"], "delay": cur["delay"], "jitter": cur["jitter"],
             "loss": cur["loss"], "loss_ema": st["ema"], "rtt_d3": cur["delay"] - lag("delay", 3), "thr_over_cap": cur["thr"] / cur["cap"],
             "n_flows": cur["n_flows"], "has_call": cur["has_call"], "has_game": cur["has_game"], "has_stream": cur["has_stream"],
             "has_bulk": cur["has_bulk"], "qoe_now": cur["qoe"], "qoe_d3": cur["qoe"] - lag("qoe", 3), "qoe_d10": cur["qoe"] - lag("qoe", 10),
             "qoe_min10": min(q10), "buf_min": 40.0 if math.isnan(buf_raw) else buf_raw, "buf_d3": buf_raw - lag("buf_raw", 3)}
        return f

    def push(self, device, t, rec):
        st = self.state.setdefault(device, {"hist": collections.deque(maxlen=16), "ema": None})
        def g(k, default=_NAN):
            v = rec.get(k, None)
            return default if v is None else float(v)
        active = rec.get("qoe", None) is not None
        row = {"qdelay_ms": g("qdelay_ms"), "rho": g("rho"), "cap": g("cap"), "mode_fq": g("mode_fq", 0.0),
               "n_call_net": g("n_call_net", 0.0), "n_game_net": g("n_game_net", 0.0), "n_stream_net": g("n_stream_net", 0.0),
               "n_bulk_net": g("n_bulk_net", 0.0), "delay": g("delay") if active else _NAN, "jitter": g("jitter") if active else _NAN,
               "loss": g("loss") if active else _NAN, "thr": g("thr") if active else _NAN, "n_flows": g("n_flows") if active else _NAN,
               "has_call": g("has_call") if active else _NAN, "has_game": g("has_game") if active else _NAN,
               "has_stream": g("has_stream") if active else _NAN, "has_bulk": g("has_bulk") if active else _NAN,
               "qoe": g("qoe") if active else _NAN, "buf_raw": g("buf_min") if active else _NAN}
        lv = 0.0 if math.isnan(row["loss"]) else row["loss"]
        st["ema"] = lv if st["ema"] is None else st["ema"] + (lv - st["ema"]) / 3.0       # ewm(alpha=1/3, adjust=False)
        st["hist"].append(row)
        if not active:
            return {"state": "inactive", "alert": False, "p_red": None}
        if row["qoe"] < self.red:
            return {"state": "red", "alert": False, "p_red": None, "qoe": row["qoe"]}
        feats = self._build(st)
        if self.enabled:
            p = float(self.model.predict_proba(pd.DataFrame([feats])[self.features])[0, 1])
            return {"state": "ok", "alert": p >= self.tau, "p_red": p, "qoe": row["qoe"], "source": "ml", "features": feats}
        return {"state": "ok", "alert": row["qoe"] < self.fallback_x, "p_red": None, "qoe": row["qoe"], "source": "qoe_level_rule", "features": feats}


# ============================================================== AGGREGATE LOADER =====================================

class ExperienceBudgetModels:
    def __init__(self, folder, config, bundles):
        self.folder, self.config, self._b = Path(folder), config, bundles
        self.bins_from_packets = bins_from_packets
        self.flow = FlowClassifier(bundles.get("flow_classifier"), config["flow_classifier"]["enabled"])

    @classmethod
    def load(cls, folder="eb_bundle"):
        folder = Path(folder); cfg = json.loads((folder / "config.json").read_text()); bundles = {}
        for name, fn in (("flow_classifier", "flow_classifier.joblib"), ("capacity_forecaster", "capacity_forecaster.joblib"),
                         ("qoe_predictor", "qoe_predictor.joblib")):
            if (folder / fn).exists(): bundles[name] = joblib.load(folder / fn)
        return cls(folder, cfg, bundles)

    def classify_flow(self, bins, is_udp, dst_port=None):
        return self.flow.classify(bins, is_udp, dst_port)

    def capacity_forecaster(self, nominal_mbps):
        return CapacityForecaster(self._b.get("capacity_forecaster"), nominal_mbps, self.config["capacity_forecaster"]["enabled"])

    def qoe_warner(self, horizon_s=10):
        return QoEWarner(self._b.get("qoe_predictor"), horizon_s, self.config["qoe_predictor"]["enabled"])

    def status(self):
        return {k: {"enabled": v["enabled"], "verdict": v["verdict"]} for k, v in self.config.items() if isinstance(v, dict) and "enabled" in v}
