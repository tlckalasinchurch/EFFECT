import os

import numpy as np
from scipy import signal

import config

class NoiseGate:
    def __init__(self, threshold_db=-60.0, ratio=4.0, attack_ms=2.0, release_ms=50.0, hold_ms=50.0, range_db=-60.0, sample_rate=48000):
        self.threshold_db = threshold_db
        self.ratio = ratio
        self.sample_rate = sample_rate
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.hold_ms = hold_ms
        self.range_db = range_db
        self.hold_counter = 0
        self.envelope = 0.0
        self.enabled = True
        self.set_timing(attack_ms, release_ms)

    def set_timing(self, attack_ms, release_ms):
        self.attack_coeff = np.exp(-1.0 / (attack_ms * 0.001 * self.sample_rate + 1e-6))
        self.release_coeff = np.exp(-1.0 / (release_ms * 0.001 * self.sample_rate + 1e-6))

    def process(self, audio):
        if not self.enabled:
            return audio
        
        mono = audio[:, 0] if audio.ndim > 1 else audio
        rms = float(np.sqrt(np.mean(mono ** 2) + 1e-9))

        thresh_lin = 10.0 ** (self.threshold_db / 20.0)
        hold_samples = int(self.hold_ms * 0.001 * self.sample_rate)

        if rms >= thresh_lin:
            self.hold_counter = hold_samples
            coeff = self.attack_coeff
        else:
            if self.hold_counter > 0:
                self.hold_counter -= len(mono)
                coeff = self.attack_coeff
            else:
                coeff = self.release_coeff

        self.envelope = coeff * self.envelope + (1.0 - coeff) * rms

        min_gain = float(10.0 ** (self.range_db / 20.0))
        if self.envelope < thresh_lin and thresh_lin > 1e-7:
            diff_db = 20.0 * np.log10(max(self.envelope, 1e-7) / thresh_lin)
            gain_db = diff_db * (self.ratio - 1.0) / self.ratio
            target_gain = max(min_gain, float(10.0 ** (gain_db / 20.0)))
        else:
            target_gain = 1.0

        if not hasattr(self, 'last_gain'):
            self.last_gain = target_gain
        gain_curve = np.linspace(self.last_gain, target_gain, len(mono), dtype=np.float32)
        self.last_gain = target_gain

        if audio.ndim > 1:
            return audio * gain_curve[:, np.newaxis]
        return audio * gain_curve


class Overdrive:
    def __init__(self, drive=0.5, tone=0.5, level=0.7, sample_rate=48000):
        self.drive = drive  # 0.0 to 1.0
        self.tone = tone    # 0.0 to 1.0
        self.level = level  # 0.0 to 1.0
        self.enabled = False
        self.sample_rate = sample_rate
        self._update_filter()

    def _update_filter(self):
        # Tone control: lowpass/highpass tilt around 1 kHz
        cutoff = 800.0 + self.tone * 3500.0
        nyq = self.sample_rate * 0.5
        norm_cutoff = min(max(cutoff / nyq, 0.01), 0.95)
        self.b, self.a = signal.butter(1, norm_cutoff, btype='low')
        self.zi = np.zeros((1, max(len(self.a), len(self.b)) - 1))

    def process(self, audio):
        if not self.enabled:
            return audio
        
        # Gain boost before clipping: 1x to 40x
        gain = 1.0 + (self.drive ** 2) * 39.0
        x = audio * gain
        
        # Asymmetric soft clipping (Tube Screamer diode saturation)
        # Positive swing clips softer, negative swing clips harder
        y = np.where(x > 0, np.tanh(x * 1.2) * 0.85, np.tanh(x * 0.9) * 0.95)
        
        # Filter tone
        if audio.ndim > 1:
            out = np.zeros_like(y)
            for ch in range(y.shape[1]):
                out[:, ch], _ = signal.lfilter(self.b, self.a, y[:, ch], zi=self.zi[0])
            y = out
        else:
            y, self.zi[0] = signal.lfilter(self.b, self.a, y, zi=self.zi[0])
            
        return y * (self.level * 1.5)


class AmpHead:
    """Tube Amplifier Emulation with 12AX7 / 6L6 non-linear stages and Tone Stack"""
    def __init__(self, gain=0.6, bass=0.5, mid=0.5, treble=0.5, presence=0.5, master=0.7, model='5150', bright=False, sample_rate=48000):
        self.gain = gain
        self.bass = bass
        self.mid = mid
        self.treble = treble
        self.presence = presence
        self.master = master
        self.model = model  # '5150', 'Plexi', 'Twin', 'Clean'
        self.bright = bright
        self.enabled = True
        self.sample_rate = sample_rate
        self._init_filters()

    def _init_filters(self):
        nyq = self.sample_rate * 0.5
        # Pre-emphasis filter (guitar tight low-cut)
        b_lowcut, a_lowcut = signal.butter(2, 80.0 / nyq, btype='high')
        self.lowcut_b = b_lowcut
        self.lowcut_a = a_lowcut
        self.lowcut_zi = np.zeros(2)

    def process(self, audio):
        if not self.enabled:
            return audio
            
        mono = audio[:, 0] if audio.ndim > 1 else audio
        
        # 1. Pre-amp low cut (tightens the bass before distortion)
        x, self.lowcut_zi = signal.lfilter(self.lowcut_b, self.lowcut_a, mono, zi=self.lowcut_zi)

        # Bright switch adds treble definition in front of the preamp
        if self.bright:
            x = x + 0.35 * (x - np.roll(x, 1))
        
        # 2. Multi-stage tube preamp saturation
        # Stage 1: Initial tube saturation
        pre_gain = 1.0 + (self.gain ** 2.2) * 60.0
        s1 = np.tanh(x * pre_gain)
        
        # Stage 2: Second triode stage with DC offset / even harmonic generation
        dc_bias = 0.15 * min(self.gain, 0.8)
        s2 = np.tanh((s1 + dc_bias) * 1.8) - np.tanh(dc_bias * 1.8)
        
        # Stage 3: Power amp sag & compression
        power_drive = s2 * (0.8 + self.master * 0.7)
        s3 = np.clip(power_drive, -1.2, 1.2)
        s3 = (3.0 * s3 - s3**3) / 2.0  # soft polynomial saturation
        
        # 3. Tone Stack (Bass, Middle, Treble, Presence)
        # Bass shelf around 120 Hz
        bass_gain_db = (self.bass - 0.5) * 24.0
        # Mid peak around 800 Hz
        mid_gain_db = (self.mid - 0.5) * 18.0
        # Treble shelf around 3500 Hz
        treble_gain_db = (self.treble - 0.5) * 22.0
        # Presence boost around 5000 Hz
        presence_gain_db = (self.presence - 0.5) * 15.0
        
        # Apply parametric filters
        out = self._apply_eq(s3, bass_gain_db, mid_gain_db, treble_gain_db, presence_gain_db)
        
        # Master volume
        out = out * (self.master * 1.2)
        
        if audio.ndim > 1:
            return np.column_stack((out, out))
        return out

    def _apply_eq(self, x, bass_db, mid_db, treble_db, pres_db):
        nyq = self.sample_rate * 0.5
        # Low shelf for bass
        b_bass, a_bass = self._shelf(150.0 / nyq, bass_db, 'low')
        x = signal.lfilter(b_bass, a_bass, x)
        
        # Peaking filter for mid (800 Hz, Q=1.0)
        b_mid, a_mid = self._peak(800.0 / nyq, mid_db, 1.0)
        x = signal.lfilter(b_mid, a_mid, x)
        
        # High shelf for treble
        b_treb, a_treb = self._shelf(3500.0 / nyq, treble_db, 'high')
        x = signal.lfilter(b_treb, a_treb, x)
        
        # High shelf for presence
        b_pres, a_pres = self._shelf(5500.0 / nyq, pres_db, 'high')
        x = signal.lfilter(b_pres, a_pres, x)
        
        return x

    def _shelf(self, norm_freq, gain_db, btype='low'):
        # 1st-order shelf approximation
        A = 10.0 ** (gain_db / 40.0)
        w0 = np.tan(np.pi * norm_freq * 0.5)
        if btype == 'low':
            b = np.array([A * w0 + 1.0, A * w0 - 1.0])
            a = np.array([w0 + 1.0, w0 - 1.0])
        else:
            b = np.array([A + w0, A - w0])
            a = np.array([1.0 + w0, 1.0 - w0])
        return b / a[0], a / a[0]

    def _peak(self, norm_freq, gain_db, Q=1.0):
        # 2nd order peaking biquad
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * norm_freq * 0.5
        alpha = np.sin(w0) / (2.0 * Q)
        b = np.array([1.0 + alpha * A, -2.0 * np.cos(w0), 1.0 - alpha * A])
        a = np.array([1.0 + alpha / A, -2.0 * np.cos(w0), 1.0 - alpha / A])
        return b / a[0], a / a[0]


class CabinetSimulator:
    """Impulse Response (IR) Convolution Cabinet Simulator"""
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self.enabled = True
        self.level = 1.0
        self.ir_name = 'Celestion V30 4x12'
        self.ir_data = self._generate_synthetic_ir('v30')
        self.zi = np.zeros(len(self.ir_data) - 1)
        # Per-block EQ (TONE3000-plugin style): Low Cut / High Cut / dry-wet.
        self.lowcut_hz = 20.0
        self.highcut_hz = 20000.0
        self.mix = 1.0
        self._design_cutoffs()

    # Per-cabinet voicing. Previously `_generate_synthetic_ir` ignored its
    # `cab_type` argument, so every cabinet produced a byte-identical
    # response and selecting a cab in the UI changed nothing audible.
    CAB_PROFILES = {
        "v30": {
            "name": "Celestion V30 4x12",
            "resonance": ((105.0, 0.55), (320.0, 0.35)),
            "scoop_hz": 800.0, "scoop_db": -5.0,
            "presence_hz": 3200.0, "presence_db": 3.0,
            "rolloff_hz": 6200.0, "hf_db": -6.0,
            "decay": 0.020,
        },
        "greenback": {
            "name": "Marshall 1960A Greenback",
            "resonance": ((95.0, 0.62), (420.0, 0.30)),
            "scoop_hz": 900.0, "scoop_db": -3.0,
            "presence_hz": 2600.0, "presence_db": 4.5,
            "rolloff_hz": 5600.0, "hf_db": -4.0,
            "decay": 0.024,
        },
        "mesa": {
            "name": "Mesa Rectifier 4x12 Slant",
            "resonance": ((90.0, 0.58), (260.0, 0.28)),
            "scoop_hz": 720.0, "scoop_db": -7.5,
            "presence_hz": 3400.0, "presence_db": 2.0,
            "rolloff_hz": 7000.0, "hf_db": -1.5,
            "decay": 0.017,
        },
        "twin": {
            "name": "Fender Twin 2x12 Jensen",
            "resonance": ((80.0, 0.60), (240.0, 0.40)),
            "scoop_hz": 1100.0, "scoop_db": -1.5,
            "presence_hz": 4200.0, "presence_db": 5.0,
            "rolloff_hz": 8200.0, "hf_db": 1.0,
            "decay": 0.022,
        },
    }

    DEFAULT_CAB = "v30"

    # TONE3000 presets without an embedded speaker IR report a synthetic cab
    # fallback by real gear name; alias it to the closest voice we have.
    CAB_ALIASES = {
        "matchless 2x12 custom": "greenback",   # Class-A mid-forward crunch
        "vintage 1x12 oxford": "twin",           # Magnatone sparkle / chime
        "ampeg 8x10 svt": "greenback",
        "bogner 4x12 v30": "v30",
        "dumble 2x12 open": "greenback",
    }

    @classmethod
    def cab_key_for_name(cls, cab_name: str) -> str:
        """Map a display name back to its profile key (case-insensitive)."""
        target = (cab_name or "").strip().lower()
        if target in cls.CAB_ALIASES:
            return cls.CAB_ALIASES[target]
        for key, profile in cls.CAB_PROFILES.items():
            if profile["name"].lower() == target:
                return key
        return cls.DEFAULT_CAB

    def _generate_synthetic_ir(self, cab_type=None):
        """
        Build a deterministic, cab-specific impulse response.

        Shapes a decaying noise burst through the cabinet's magnitude
        response (body resonances, mid scoop, presence peak, HF roll-off).
        Generated once at load time, so this is not on the audio hot path.
        """
        key = cab_type if cab_type in self.CAB_PROFILES else self.DEFAULT_CAB
        profile = self.CAB_PROFILES[key]

        length = 600
        rng = np.random.default_rng(sum(ord(c) for c in key) * 2654435761 % (2**32))
        noise = rng.standard_normal(length).astype(np.float32)
        env = np.exp(-np.linspace(0.0, 1.0, length, dtype=np.float32) / profile["decay"] * 3.0)
        ir = noise * env

        # Frequency-domain voicing.
        spectrum = np.fft.rfft(ir)
        freqs = np.maximum(np.fft.rfftfreq(length, d=1.0 / self.sample_rate), 1e-3)
        gain_db = np.zeros_like(freqs)

        # Speaker body resonances.
        for res_hz, res_gain in profile["resonance"]:
            gain_db += res_gain * np.exp(-((np.log2(freqs / res_hz)) ** 2) / 0.28)

        # Mid scoop.
        gain_db += profile["scoop_db"] * np.exp(
            -((np.log2(freqs / profile["scoop_hz"])) ** 2) / 0.22
        )

        # Presence peak.
        gain_db += profile["presence_db"] * np.exp(
            -((np.log2(freqs / profile["presence_hz"])) ** 2) / 0.30
        )

        # HF roll-off above the cone break-up point.
        gain_db += profile["hf_db"] * np.clip(
            (np.log2(freqs / profile["rolloff_hz"])) / 0.9, 0.0, None
        )

        # Gentle overall tilt keeps the low mids from collapsing.
        gain_db += 0.2 * np.log2(freqs / 1000.0)

        ir = np.fft.irfft(spectrum * (10.0 ** (gain_db / 20.0)), n=length).astype(np.float32)

        peak = float(np.max(np.abs(ir)))
        if peak > 1e-9:
            ir = ir / peak * config.IR_NORMALIZATION_GAIN
        return np.ascontiguousarray(ir, dtype=np.float32)

    def _design_cutoffs(self):
        """Build the cab's Low Cut / High Cut biquads and clear their state."""
        nyq = self.sample_rate * 0.5
        low = min(max(float(self.lowcut_hz), 10.0), nyq * 0.90)
        high = min(max(float(self.highcut_hz), low * 1.5), nyq * 0.95)
        self.hp_b, self.hp_a = signal.butter(2, low / nyq, btype='high')
        self.lp_b, self.lp_a = signal.butter(2, high / nyq, btype='low')
        self.hp_zi = np.zeros(max(len(self.hp_a), len(self.hp_b)) - 1, dtype=np.float64)
        self.lp_zi = np.zeros(max(len(self.lp_a), len(self.lp_b)) - 1, dtype=np.float64)

    def set_cutoffs(self, lowcut_hz=None, highcut_hz=None):
        """Set the IR CAB Low Cut / High Cut without touching the loaded IR."""
        if lowcut_hz is not None:
            self.lowcut_hz = float(lowcut_hz)
        if highcut_hz is not None:
            self.highcut_hz = float(highcut_hz)
        self._design_cutoffs()


    def select_cab(self, cab_name: str) -> str:
        """
        Install the factory IR matching a display name and set the name.

        Returns the canonical cabinet name; unknown names fall back to default.
        """
        key = self.cab_key_for_name(cab_name)
        ir = self._generate_synthetic_ir(key)
        self.set_ir_data(ir, self.CAB_PROFILES[key]["name"])
        return self.ir_name

    @staticmethod
    def _prepare_ir(data, sr, target_rate, max_length):
        """
        Normalise arbitrary WAV samples into a bounded, click-free IR buffer.

        Returns (float32 array, was_truncated).
        Raises ValueError on unusable input.
        """
        data = np.asarray(data)
        if data.ndim > 1:
            data = data[:, 0]
        if data.size == 0:
            raise ValueError("IR contains no audio samples")

        # Integer PCM -> float in [-1, 1]
        if np.issubdtype(data.dtype, np.integer):
            data = data.astype(np.float32) / float(np.iinfo(data.dtype).max)
        else:
            data = data.astype(np.float32)

        # Resample to the engine rate if needed.
        sr = int(sr) if sr else 0
        target_rate = int(target_rate) if target_rate else 0
        if sr > 0 and target_rate > 0 and sr != target_rate:
            num_samples = max(1, int(round(len(data) * target_rate / sr)))
            data = signal.resample(data, num_samples)

        truncated = False
        if max_length and len(data) > max_length:
            data = data[:max_length]
            truncated = True
            # Fade the tail so the hard cut cannot produce a click.
            fade = min(len(data), 64)
            if fade > 1:
                ramp = np.linspace(1.0, 0.0, fade, dtype=np.float32)
                data[-fade:] *= ramp

        peak = float(np.max(np.abs(data)))
        if peak > 1e-9:
            data = data / peak * config.IR_NORMALIZATION_GAIN
        else:
            raise ValueError("IR is silent (all samples are zero)")

        return np.ascontiguousarray(data, dtype=np.float32), truncated

    def load_ir_file(self, path):
        """Load and normalise an IR from a WAV file on disk."""
        try:
            from scipy.io import wavfile
            sr, data = wavfile.read(path)
            prepared, _ = self._prepare_ir(data, sr, self.sample_rate, config.IR_MAX_LENGTH)
            self.set_ir_data(prepared, os.path.basename(path))
            return True
        except Exception as e:
            print(f"Failed to load IR ({path}): {e}")
            return False

    def set_ir_data(self, ir_data, ir_name):
        """
        Install a prepared IR buffer directly (custom uploads / presets).

        Validates before mutating so a rejected buffer cannot leave the
        cabinet in a half-updated state.
        """
        prepared = np.ascontiguousarray(np.asarray(ir_data), dtype=np.float32).ravel()
        if prepared.size < 2:
            raise ValueError("IR must contain at least 2 samples")
        if not np.all(np.isfinite(prepared)):
            raise ValueError("IR contains NaN or infinite samples")

        # Commit only after every check passes.
        self.ir_data = prepared
        self.ir_name = str(ir_name)
        self.zi = np.zeros(len(self.ir_data) - 1, dtype=np.float32)
        # A new IR must not inherit the previous cabinet's filter history.
        self._design_cutoffs()
        return True

    def process(self, audio):
        if not self.enabled:
            return audio

        mono = audio[:, 0] if audio.ndim > 1 else audio
        wet = signal.fftconvolve(mono, self.ir_data, mode='full')[:len(mono)]

        # Per-block EQ: Low Cut then High Cut, exactly like the plugin's IR CAB
        # block. Both filters are 2nd-order Butterworth biquads.
        wet, self.hp_zi = signal.lfilter(self.hp_b, self.hp_a, wet, zi=self.hp_zi)
        wet, self.lp_zi = signal.lfilter(self.lp_b, self.lp_a, wet, zi=self.lp_zi)
        if self.level != 1.0:
            wet = wet * self.level

        out = wet if self.mix >= 0.999 else mono * (1.0 - self.mix) + wet * self.mix

        if audio.ndim > 1:
            return np.column_stack((out, out))
        return out


class PitchShifter:
    """
    Vectorized dual-tap crossfading pitch shifter with zero audio loop allocations.
    Transposes pitch from -24 to +24 semitones with fine cents tuning.
    """
    def __init__(self, semitones=0.0, cents=0.0, mix=1.0, window_ms=30.0, glide=0.0, sample_rate=48000):
        self.sample_rate = sample_rate
        self.enabled = False
        self.semitones = float(semitones)
        self.target_semitones = float(semitones)
        self._target_dirty = False
        self.cents = float(cents)
        self.mix = float(mix)
        self.glide_pct = max(0.0, min(100.0, float(glide)))
        self.glide_ms = (self.glide_pct / 100.0) * 400.0
        self.window_size = int(sample_rate * (window_ms / 1000.0))
        if self.window_size < 128:
            self.window_size = 128
        self.buf_size = self.window_size * 4
        self.buffer = np.zeros(self.buf_size, dtype=np.float32)
        self.write_pos = 0
        self.phase = 0.0
        w = np.arange(self.window_size, dtype=np.float32)
        self.window_lut = (0.5 * (1.0 - np.cos(2.0 * np.pi * w / self.window_size))).astype(np.float32)

    def set_semitones(self, value):
        """Set the transposition target; Glide decides how fast it is reached."""
        self.target_semitones = float(value)
        self._target_dirty = True
        if self.glide_ms <= 0.0:
            self.semitones = self.target_semitones
            self._target_dirty = False

    def set_glide(self, pct):
        """Glide time 0-100 % -> 0-400 ms portamento."""
        self.glide_pct = max(0.0, min(100.0, float(pct)))
        self.glide_ms = (self.glide_pct / 100.0) * 400.0
        if self.glide_ms <= 0.0:
            self.semitones = self.target_semitones
            self._target_dirty = False

    def _ratio(self):
        return 2.0 ** ((self.semitones + self.cents / 100.0) / 12.0)

    def process(self, audio):
        if not self.enabled:
            return audio

        # Portamento: move the current pitch toward the knob target per block.
        diff = self.target_semitones - self.semitones
        if self._target_dirty and abs(diff) > 1e-6:
            if self.glide_ms > 0.0:
                n_glide = len(audio)
                tau = max(0.005, self.glide_ms / 1000.0)
                coeff = 1.0 - np.exp(-n_glide / (tau * self.sample_rate))
                self.semitones += diff * coeff
                if abs(self.target_semitones - self.semitones) < 0.01:
                    self.semitones = self.target_semitones
                    self._target_dirty = False
            else:
                self.semitones = self.target_semitones
                self._target_dirty = False

        if self.semitones == 0.0 and self.cents == 0.0 and self.mix >= 0.999:
            return audio

        mono = audio[:, 0] if audio.ndim > 1 else audio
        n = len(mono)
        ratio = self._ratio()
        rate_diff = 1.0 - ratio
        
        idx = (np.arange(n) + self.write_pos) % self.buf_size
        self.buffer[idx] = mono
        
        phase_arr = (self.phase + np.arange(n) * rate_diff) % self.window_size
        half_win = self.window_size // 2
        p1 = phase_arr.astype(np.int32)
        p2 = ((phase_arr + half_win) % self.window_size).astype(np.int32)
        
        r1 = (idx - p1) % self.buf_size
        r2 = (idx - p2) % self.buf_size
        
        w1 = self.window_lut[p1]
        w2 = self.window_lut[p2]
        
        wet = self.buffer[r1] * w1 + self.buffer[r2] * w2
        self.write_pos = (self.write_pos + n) % self.buf_size
        self.phase = (self.phase + n * rate_diff) % self.window_size
        
        out = (1.0 - self.mix) * mono + self.mix * wet
        if audio.ndim > 1:
            return np.column_stack((out, out))
        return out.astype(np.float32)


class Delay:
    def __init__(self, time_sec=0.35, feedback=0.4, mix=0.25, sample_rate=48000):
        self.time_sec = time_sec
        self.feedback = feedback
        self.mix = mix
        self.enabled = False
        self.sample_rate = sample_rate
        self.max_delay_samples = int(sample_rate * 2.0)
        self.buffer = np.zeros(self.max_delay_samples, dtype=np.float32)
        self.write_pos = 0

    def process(self, audio):
        if not self.enabled or self.mix <= 0.001:
            return audio
            
        mono = audio[:, 0] if audio.ndim > 1 else audio
        delay_samples = int(self.time_sec * self.sample_rate)
        delay_samples = max(1, min(delay_samples, self.max_delay_samples - 1))

        n = len(mono)
        read_idx = (np.arange(n) + self.write_pos - delay_samples) % self.max_delay_samples
        delayed = self.buffer[read_idx]
        write_idx = (np.arange(n) + self.write_pos) % self.max_delay_samples
        self.buffer[write_idx] = mono + delayed * self.feedback
        self.write_pos = (self.write_pos + n) % self.max_delay_samples

        out = (1.0 - self.mix) * mono + self.mix * delayed
        if audio.ndim > 1:
            return np.column_stack((out, out))
        return out


class Reverb:
    """Schroeder-style algorithmic reverberator"""
    def __init__(self, decay=0.5, mix=0.2, tone=0.5, reverb_type='plate', sample_rate=48000):
        self.decay = decay
        self.mix = mix
        self.tone = tone
        self.reverb_type = reverb_type
        self.enabled = False
        self.sample_rate = sample_rate
        # Comb filter delays
        delays = [1557, 1617, 1491, 1422]
        self.comb_buffers = [np.zeros(d, dtype=np.float32) for d in delays]
        self.comb_pos = [0 for _ in delays]

    def process(self, audio):
        if not self.enabled or self.mix <= 0.001:
            return audio
            
        mono = audio[:, 0] if audio.ndim > 1 else audio
        n = len(mono)
        rev = np.zeros(n, dtype=np.float32)
        fb = 0.5 + self.decay * 0.4

        for idx in range(len(self.comb_buffers)):
            buf = self.comb_buffers[idx]
            d = len(buf)
            pos = self.comb_pos[idx]
            if pos + n <= d:
                out_val = buf[pos : pos + n].copy()
                buf[pos : pos + n] = mono + out_val * fb
                self.comb_pos[idx] = (pos + n) % d
            else:
                p1 = d - pos
                p2 = n - p1
                out_val = np.concatenate([buf[pos:d], buf[0:p2]])
                buf[pos:d] = mono[:p1] + out_val[:p1] * fb
                buf[0:p2] = mono[p1:] + out_val[p1:] * fb
                self.comb_pos[idx] = p2
            rev += out_val * 0.25

        out = (1.0 - self.mix) * mono + self.mix * rev
        if audio.ndim > 1:
            return np.column_stack((out, out))
        return out


class GuitarSignalChain:
    """The Complete Guitar Effect Rig Chain"""
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self.master_volume = 1.0
        self.input_trim_db = 0.0
        self.noise_gate = NoiseGate(threshold_db=-55.0, sample_rate=sample_rate)
        self.pitch_shifter = PitchShifter(sample_rate=sample_rate)
        self.screamer = Overdrive(drive=0.4, tone=0.6, level=0.7, sample_rate=sample_rate)
        self.amp = AmpHead(gain=0.65, bass=0.55, mid=0.5, treble=0.6, presence=0.6, master=0.7, sample_rate=sample_rate)
        self.cab = CabinetSimulator(sample_rate=sample_rate)
        self.delay = Delay(time_sec=0.36, feedback=0.35, mix=0.25, sample_rate=sample_rate)
        self.reverb = Reverb(decay=0.5, mix=0.2, sample_rate=sample_rate)
        self.input_level_meter = 0.0
        self.output_level_meter = 0.0
        self.nam = None  # engine.nam.NamChain; replaces the DSP amp stage when set

    def process(self, input_chunk):
        # Calculate input level from the raw signal, then apply the input trim.
        in_rms = float(np.sqrt(np.mean(input_chunk ** 2) + 1e-9))
        self.input_level_meter = self.input_level_meter * 0.8 + in_rms * 0.2

        x = input_chunk
        if self.input_trim_db:
            x = x * np.float32(10.0 ** (self.input_trim_db / 20.0))
        x = self.noise_gate.process(x)
        x = self.pitch_shifter.process(x)

        # DRIVE is a real block in front of the amp, even when a NAM chain is
        # installed. The old path skipped it whenever `nam` was set.
        x = self.screamer.process(x)

        nam = self.nam  # read once: the UI thread may swap it mid-block
        if nam is not None:
            if getattr(nam, "enabled", True):
                x = nam.process(x)
        else:
            x = self.amp.process(x)

        x = self.cab.process(x)
        x = self.delay.process(x)
        x = self.reverb.process(x)
        
        # Master volume control & brickwall limiter to protect hearing / speakers
        x = np.clip(x * self.master_volume, -1.0, 1.0)
        
        out_rms = float(np.sqrt(np.mean(x ** 2) + 1e-9))
        self.output_level_meter = self.output_level_meter * 0.8 + out_rms * 0.2
        
        return x.astype(np.float32)
