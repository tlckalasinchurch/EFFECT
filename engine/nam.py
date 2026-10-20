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


class SlimmableWaveNet:
    """NAM "SlimmableContainer": WaveNet submodels of growing size, picked by max_value."""

    def __init__(self, model, build="all"):
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
