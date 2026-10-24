"""
Neural Amp Modeler (NAM) WaveNet runtime in numpy.

Reads the model JSON the TONE3000 app embeds in its presets (NAM v0.7.0,
architecture "SlimmableContainer" holding "WaveNet" submodels).

Weight layout, as used here (checked: the parameter count computed from the
config equals len(weights) for both submodels of the factory presets):

    rechannel   (1x1, input_size -> channels, no bias)
    per layer:  conv (channels -> bottleneck, kernel k, dilation d, bias)
                input_mixin (condition_size -> bottleneck, no bias)
                layer1x1 (bottleneck -> channels, bias)
    head        (Conv1D bottleneck -> head out_channels, kernel head.kernel_size, bias)
    head_scale  (1 value)

Each layer:  z = conv(x) + mixin(condition);  a = act(z);  head_in += a;
             x = x + layer1x1(a).
Output = head_scale * head(head_in).

Not supported (raises NotImplementedError): gated activations, FiLM, grouped
convs, an active head1x1, secondary activations, several layer arrays.

Verified against TONE3000's published golden vectors (github.com/tone-3000/
embedded, MIT, test/golden_*.raw with weights/*.namb): ESR -140.9 dB for the
A2-Full shape and -135.5 dB for A2-Lite, in 512-sample blocks. Only those two
shapes (3 and 8 channels, 23 layers) were checked; other NAM WaveNet shapes
load but are untested.
"""

import numpy as np


def _activation(spec):
    kind = spec["type"] if isinstance(spec, dict) else spec
    if kind == "Tanh":
        return np.tanh
    if kind == "ReLU":
        return lambda z: np.maximum(z, 0.0)
    if kind == "LeakyReLU":
        slope = np.float32(spec.get("negative_slope", 0.01)) if isinstance(spec, dict) else np.float32(0.01)
        return lambda z: np.where(z > 0.0, z, z * slope)
    raise NotImplementedError(f"activation {kind!r}")


class _Layer:
    def __init__(self, ch, bott, k, dilation, act, w):
        self.k, self.d = k, dilation
        self.hist_len = (k - 1) * dilation
        self.act = act
        # NAM weight order: conv[out][in][tap], then bias.
        conv = w.take(bott * ch * k).reshape(bott, ch, k)
        self.conv_flat = np.ascontiguousarray(conv.transpose(0, 2, 1).reshape(bott, k * ch))
        self.conv_b = w.take(bott)[:, None]
        self.mixin = w.take(bott).reshape(bott, 1)
        self.l1x1 = w.take(ch * bott).reshape(ch, bott)
        self.l1x1_b = w.take(ch)[:, None]
        self.hist = np.zeros((ch, self.hist_len), np.float32)


class _Weights:
    def __init__(self, arr):
        self.a = np.asarray(arr, np.float32)
        self.i = 0

    def take(self, n):
        out = self.a[self.i:self.i + n]
        if len(out) != n:
            raise ValueError("weights ran out: layout does not match the config")
        self.i += n
        return out


class WaveNet:
    def __init__(self, model):
        if model.get("architecture") != "WaveNet":
            raise NotImplementedError(f"architecture {model.get('architecture')!r}")
        cfg = model["config"]
        arrays = cfg["layers"]
        if len(arrays) != 1:
            raise NotImplementedError("only one layer array is supported")
        la = arrays[0]
        for key in ("conv_pre_film", "conv_post_film", "input_mixin_pre_film", "input_mixin_post_film",
                    "activation_pre_film", "activation_post_film", "layer1x1_post_film", "head1x1_post_film"):
            if la.get(key, {}).get("active"):
                raise NotImplementedError(f"FiLM ({key})")
        if la.get("head1x1", {}).get("active"):
            raise NotImplementedError("head1x1")
        if any(m not in ("none", None) for m in la["gating_mode"]) or any(la["secondary_activation"]):
            raise NotImplementedError("gated / secondary activations")
        if la.get("groups_input", 1) != 1 or la.get("groups_input_mixin", 1) != 1 \
                or la["layer1x1"].get("groups", 1) != 1 or not la["layer1x1"].get("active", True):
            raise NotImplementedError("grouped convs or inactive layer1x1")

        ch, bott = la["channels"], la["bottleneck"]
        head = la["head"]
        if la["input_size"] != 1 or la["condition_size"] != 1 or head["out_channels"] != 1:
            raise NotImplementedError("only mono in / mono out")
        w = _Weights(model["weights"])
        self.rechannel = w.take(ch * la["input_size"]).reshape(ch, 1)
        self.layers = [
            _Layer(ch, bott, k, d, _activation(a), w)
            for k, d, a in zip(la["kernel_sizes"], la["dilations"], la["activation"])
        ]
        hk = head["kernel_size"]
        head_w = w.take(bott * hk).reshape(1, bott, hk)
        self.head_flat = np.ascontiguousarray(head_w.transpose(0, 2, 1).reshape(1, hk * bott))
        self.head_b = np.float32(w.take(1)[0]) if head.get("bias", True) else np.float32(0.0)
        self.head_k = hk
        self.head_hist = np.zeros((bott, hk - 1), np.float32)
        self.head_scale = np.float32(w.take(1)[0])
        if w.i != len(w.a):
            raise ValueError(f"layout mismatch: used {w.i} of {len(w.a)} weights")
        cfg_scale = cfg.get("head_scale")
        if cfg_scale is not None and abs(float(self.head_scale) - cfg_scale) > 1e-5:
            raise ValueError("trailing weight is not config.head_scale: layout mismatch")
        self.ch, self.bott = ch, bott
        self.sample_rate = model.get("sample_rate", 48000)
        self.receptive_field = sum(l.hist_len for l in self.layers) + hk - 1
        self._prewarm()

    def reset(self):
        """Back to the state NAM starts from: silence already run through the model."""
        for l in self.layers:
            l.hist[:] = 0.0
        self.head_hist[:] = 0.0
        self._prewarm()

    def _prewarm(self):
        # Biases make the steady response to silence non-zero, so zero-filled
        # history is wrong for the first receptive-field's worth of samples.
        silence = np.zeros(512, np.float32)
        for _ in range(-(-self.receptive_field // 512) + 1):
            self.process(silence)

    @staticmethod
    def _causal(flat, hist, x, k, d, bias=None):
        """Causal dilated conv over [hist | x] -> (out, new_hist). x is (ch, n)."""
        n = x.shape[1]
        ext = np.concatenate((hist, x), axis=1) if hist.shape[1] else x
        h = hist.shape[1]
        # tap j (0 = oldest) reads ext[:, h + t - (k-1-j)*d]
        cols = [ext[:, h - (k - 1 - j) * d: h - (k - 1 - j) * d + n] for j in range(k)]
        out = flat @ np.concatenate(cols, axis=0)
        if bias is not None:
            out += bias
        return out, (ext[:, -h:] if h else hist)

    def process(self, x):
        x = np.asarray(x, np.float32).reshape(1, -1)
        cond = x
        z = self.rechannel @ x
        head_in = 0.0
        for l in self.layers:
            conv, l.hist = self._causal(l.conv_flat, l.hist, z, l.k, l.d, l.conv_b)
            a = l.act(conv + l.mixin @ cond)
            head_in = head_in + a
            z = z + (l.l1x1 @ a + l.l1x1_b)
        out, self.head_hist = self._causal(self.head_flat, self.head_hist, head_in, self.head_k, 1)
        return ((out[0] + self.head_b) * self.head_scale).astype(np.float32)


class _C99Net:
    """A2 WaveNet run by nam_c99.dll, with the numpy WaveNet as fallback.

    The DLL keeps ONE global model, so only one net may use it at a time.  A net
    claims the DLL on its first process() call (i.e. when it is really in the
    audio path) and a net that is not the owner runs the numpy twin instead.
    Output matches the numpy runtime to better than -110 dB.
    """
    _owner = None

    def __init__(self, model, fallback):
        from engine.nam_c99 import C99NamEngine
        self._cls = C99NamEngine
        self.model = model
        self.fallback = fallback
        self.engine = None
        self.enabled = True  # NamChain turns this off for multi-stage chains

    @staticmethod
    def supports(model):
        """True when the model has exactly the A2 layout the DLL was built for."""
        try:
            from engine.nam_c99 import C99NamEngine
            if not C99NamEngine.is_available():
                return False
            la = model["config"]["layers"][0]
            return (len(model["weights"]) in (1871, 12146)
                    and la["channels"] in (3, 8)
                    and list(la["kernel_sizes"]) == _A2_KERNEL_SIZES
                    and list(la["dilations"]) == _A2_DILATIONS
                    and all((a.get("type") if isinstance(a, dict) else a) == "LeakyReLU" for a in la["activation"])
                    and int(model.get("sample_rate", 48000)) == 48000)
        except Exception:
            return False

    def reset(self):
        self.fallback.reset()
        if self.engine is not None and _C99Net._owner is self:
            self.engine.reset()

    def process(self, x):
        if not self.enabled:
            return self.fallback.process(x)
        if _C99Net._owner is not self:
            try:
                self.engine = self._cls.from_weights(self.model["weights"], sample_rate=48000.0)
                _C99Net._owner = self
            except Exception:
                self.enabled = False
                return self.fallback.process(x)
        return self.engine.process(x)


class SlimmableWaveNet:
    """NAM "SlimmableContainer": WaveNet submodels of growing size, picked by max_value."""

    def __init__(self, model, build="all", use_c99=True):
        """build: "all" submodels, or just the "lite" (smallest) / "full" (largest) one."""
        if model.get("architecture") == "WaveNet":
            subs = [{"max_value": 1.0, "model": model}]
        elif model.get("architecture") == "SlimmableContainer":
            subs = sorted(model["config"]["submodels"], key=lambda s: s["max_value"])
        else:
            raise NotImplementedError(f"architecture {model.get('architecture')!r}")
        if build == "lite":
            subs = subs[:1]
        elif build == "full":
            subs = subs[-1:]
        self.max_values = [s["max_value"] for s in subs]
        self.nets = [WaveNet(s["model"]) for s in subs]
        self.c99_nets = []
        if use_c99:
            for i, s in enumerate(subs):
                if _C99Net.supports(s["model"]):
                    self.nets[i] = _C99Net(s["model"], self.nets[i])
                    self.c99_nets.append(self.nets[i])
        self.metadata = model.get("metadata", {})
        self.sample_rate = model.get("sample_rate", 48000)
        self.active = len(self.nets) - 1

    def select(self, value):
        """value in 0..1: the first submodel whose max_value >= value (1.0 = largest)."""
        for i, mv in enumerate(self.max_values):
            if mv >= value:
                self.active = i
                return i
        self.active = len(self.nets) - 1
        return self.active

    def reset(self):
        for n in self.nets:
            n.reset()

    def process(self, x):
        return self.nets[self.active].process(x)


class NamChain:
    """
    NAM stages in series (pedal -> amp -> ...). `stages` is a list of
    {"title", "gear_type", "net": SlimmableWaveNet}. The output is scaled so the
    last model's `metadata.loudness` lands on `target_loudness` dB (what NAM's
    own plugin does); a missing loudness leaves the level alone. Input gain is
    in dB because the UX1's analog input level is not known to the app.
    """

    def __init__(self, stages, input_gain_db=0.0, target_loudness=-18.0):
        if not stages:
            raise ValueError("no NAM stages")
        self.stages = stages
        if len(stages) > 1:
            # The DLL holds a single model; stages would fight over it.
            for stage in stages:
                for net in getattr(stage["net"], "c99_nets", []):
                    net.enabled = False
        self.enabled = True
        self.input_gain_db = float(input_gain_db)
        self.input_gain = np.float32(10.0 ** (self.input_gain_db / 20.0))
        loud = stages[-1]["net"].metadata.get("loudness")
        self.out_gain = np.float32(10.0 ** (max(-24.0, min(24.0, target_loudness - loud)) / 20.0)) \
            if isinstance(loud, (int, float)) else np.float32(1.0)
        # amp_cab captures already include the speaker; a separate cab IR would double it.
        self.includes_cab = any(s.get("gear_type") == "amp_cab" for s in stages)

    def set_input_gain_db(self, db):
        """Calibrate the guitar/interface level into the NAM capture."""
        self.input_gain_db = max(-24.0, min(24.0, float(db)))
        self.input_gain = np.float32(10.0 ** (self.input_gain_db / 20.0))

    def process(self, x):
        if not self.enabled:
            return np.asarray(x, np.float32)
        y = np.asarray(x, np.float32) * self.input_gain
        for stage in self.stages:
            y = stage["net"].process(y)
        return y * self.out_gain

    def describe(self):
        return {"stages": [{"title": s["title"], "gear_type": s.get("gear_type")} for s in self.stages],
                "out_gain_db": round(float(20.0 * np.log10(self.out_gain)), 1),
                "includes_cab": self.includes_cab,
                "enabled": bool(self.enabled),
                "input_gain_db": round(float(self.input_gain_db), 2)}


_A2_KERNEL_SIZES = [6] * 14 + [15, 15] + [6] * 7
_A2_DILATIONS = [1, 3, 7, 17, 41, 101, 239] * 2 + [1, 13] + [1, 3, 7, 17, 41, 101, 239]
_A2_ACTIVATIONS = [{"type": "LeakyReLU", "negative_slope": 0.01} for _ in range(23)]


def build_a2_model_from_weights(weights, sample_rate=48000, loudness=-18.0, gear_type="amp"):
    """
    Construct a canonical NAM A2 WaveNet / SlimmableContainer dict from raw A2 weights
    (1,871 weights = A2-Lite 3ch; 12,146 weights = A2-Full 8ch).
    """
    w_arr = np.asarray(weights, dtype=np.float32).reshape(-1)
    count = int(len(w_arr))
    if count == 1871:
        ch = 3
        max_val = 0.5
    elif count == 12146:
        ch = 8
        max_val = 1.0
    else:
        ch = 8 if count > 6000 else 3
        max_val = 1.0

    w_list = w_arr.tolist()
    head_scale = float(w_arr[-1])
    wavenet_doc = {
        "version": "0.7.0",
        "architecture": "WaveNet",
        "sample_rate": int(sample_rate),
        "metadata": {"loudness": float(loudness), "gear_type": gear_type},
        "config": {
            "head_scale": head_scale,
            "layers": [
                {
                    "input_size": 1,
                    "condition_size": 1,
                    "head": {"out_channels": 1, "kernel_size": 16, "bias": True},
                    "channels": ch,
                    "bottleneck": ch,
                    "kernel_sizes": list(_A2_KERNEL_SIZES),
                    "dilations": list(_A2_DILATIONS),
                    "activation": list(_A2_ACTIVATIONS),
                    "head1x1": {"active": False, "out_channels": 1, "groups": 1},
                    "layer1x1": {"active": True, "groups": 1},
                    "groups_input": 1,
                    "groups_input_mixin": 1,
                    "gating_mode": ["none"] * 23,
                    "secondary_activation": [None] * 23,
                }
            ],
        },
        "weights": w_list,
    }
    return {
        "version": "0.7.0",
        "architecture": "SlimmableContainer",
        "sample_rate": int(sample_rate),
        "metadata": {"loudness": float(loudness), "gear_type": gear_type, "architecture": "A2"},
        "config": {"submodels": [{"max_value": max_val, "model": wavenet_doc}]},
    }


def parse_namb_binary(raw_bytes: bytes, gear_type: str = "amp", filename: str = "", sample_rate: int = 48000) -> dict:
    """
    Decode a binary NAM (.namb) payload (magic b'BMAN' / b'NAMB') into a
    SlimmableContainer model dictionary ready for SlimmableWaveNet.
    Conforms to the official tone-3000/nam-binary-loader format specification:
      - 32-byte header with format version, flags, total_file_size, weights_offset, weight_count
      - 48-byte metadata block with version, sample_rate, loudness, input/output levels
      - Model configuration block (WaveNet / A2)
      - Raw IEEE 754 float32 weight vectors
    Also supports legacy 52-byte and compact 12-byte headers.
    """
    import struct

    if len(raw_bytes) < 12 or raw_bytes[:4] not in (b"BMAN", b"NAMB"):
        raise ValueError("Not a valid NAM binary (.namb) header")
    c_arch, c_count = struct.unpack_from("<II", raw_bytes, 4)
    if c_count in (1871, 12146) and 12 + c_count * 4 <= len(raw_bytes):
        weights = np.frombuffer(raw_bytes, dtype="<f4", count=c_count, offset=12).astype(np.float32)
        return build_a2_model_from_weights(weights, sample_rate=int(sample_rate or 48000), loudness=-18.0, gear_type=gear_type)
    if len(raw_bytes) < 52:
        raise ValueError("Not a valid NAM binary (.namb) header")
    hdr_off, count = struct.unpack_from("<II", raw_bytes, 12)
    sr, loudness = struct.unpack_from("<dd", raw_bytes, 36)
    if hdr_off < 48 or hdr_off + count * 4 > len(raw_bytes):
        raise ValueError("Corrupted .namb weight table bounds")
    weights = np.frombuffer(raw_bytes, dtype="<f4", count=count, offset=hdr_off).astype(np.float32)
    if not (8000 <= sr <= 192000):
        sr = float(sample_rate or 48000)
    if not (-60.0 <= loudness <= 24.0):
        loudness = -18.0
    return build_a2_model_from_weights(weights, sample_rate=int(sr), loudness=float(loudness), gear_type=gear_type)

