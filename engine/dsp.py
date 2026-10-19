import numpy as np
from scipy import signal

class NoiseGate:
    def __init__(self, threshold_db=-60.0, ratio=4.0, attack_ms=2.0, release_ms=50.0, sample_rate=48000):
        self.threshold_db = threshold_db
        self.ratio = ratio
        self.sample_rate = sample_rate
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

        coeff = self.attack_coeff if rms > self.envelope else self.release_coeff
        self.envelope = coeff * self.envelope + (1.0 - coeff) * rms

        thresh_lin = 10.0 ** (self.threshold_db / 20.0)
        if self.envelope < thresh_lin and thresh_lin > 1e-7:
            diff_db = 20.0 * np.log10(max(self.envelope, 1e-7) / thresh_lin)
            gain_db = diff_db * (self.ratio - 1.0) / self.ratio
            target_gain = float(10.0 ** (gain_db / 20.0))
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
    def __init__(self, gain=0.6, bass=0.5, mid=0.5, treble=0.5, presence=0.5, master=0.7, model='5150', sample_rate=48000):
        self.gain = gain
        self.bass = bass
        self.mid = mid
        self.treble = treble
        self.presence = presence
        self.master = master
        self.model = model  # '5150', 'Plexi', 'Twin', 'Clean'
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
        self.ir_name = 'Celestion V30 4x12'
        self.ir_data = self._generate_synthetic_ir('v30')
        self.zi = np.zeros(len(self.ir_data) - 1)

    def _generate_synthetic_ir(self, cab_type='v30'):
        # High-quality synthetic speaker IR response (600 samples)
        length = 600
        t = np.linspace(0, 1.0, length)
        # Speaker resonance around 100 Hz, mid scoop around 800 Hz, speaker peak around 3-4 kHz, steep roll-off at 5.5 kHz
        envelope = np.exp(-t * 28.0)
        ir = (
            np.sin(2.0 * np.pi * 95.0 * t * (length / self.sample_rate)) * 0.6 +
            np.sin(2.0 * np.pi * 2200.0 * t * (length / self.sample_rate)) * 0.4 +
            np.sin(2.0 * np.pi * 3800.0 * t * (length / self.sample_rate)) * 0.7
        ) * envelope
        
        # Normalize IR
        ir = ir / (np.max(np.abs(ir)) + 1e-6) * 0.35
        return ir.astype(np.float32)

    def load_ir_file(self, path):
        try:
            from scipy.io import wavfile
            sr, data = wavfile.read(path)
            if data.ndim > 1:
                data = data[:, 0]
            if np.issubdtype(data.dtype, np.integer):
                data = data.astype(np.float32) / np.iinfo(data.dtype).max
            # Resample if needed
            if sr != self.sample_rate:
                num_samples = int(len(data) * self.sample_rate / sr)
                data = signal.resample(data, num_samples)
            # Truncate to reasonable length (e.g. 1024 samples)
            data = data[:1024]
            self.ir_data = data / (np.max(np.abs(data)) + 1e-6) * 0.35
            self.zi = np.zeros(len(self.ir_data) - 1)
            return True
        except Exception as e:
            print("Failed to load IR:", e)
            return False

    def process(self, audio):
        if not self.enabled:
            return audio
            
        mono = audio[:, 0] if audio.ndim > 1 else audio
        out = signal.fftconvolve(mono, self.ir_data, mode='full')[:len(mono)]
        
        if audio.ndim > 1:
            return np.column_stack((out, out))
        return out


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
    def __init__(self, decay=0.5, mix=0.2, sample_rate=48000):
        self.decay = decay
        self.mix = mix
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
        self.noise_gate = NoiseGate(threshold_db=-55.0, sample_rate=sample_rate)
        self.screamer = Overdrive(drive=0.4, tone=0.6, level=0.7, sample_rate=sample_rate)
        self.amp = AmpHead(gain=0.65, bass=0.55, mid=0.5, treble=0.6, presence=0.6, master=0.7, sample_rate=sample_rate)
        self.cab = CabinetSimulator(sample_rate=sample_rate)
        self.delay = Delay(time_sec=0.36, feedback=0.35, mix=0.25, sample_rate=sample_rate)
        self.reverb = Reverb(decay=0.5, mix=0.2, sample_rate=sample_rate)
        self.input_level_meter = 0.0
        self.output_level_meter = 0.0

    def process(self, input_chunk):
        # Calculate input level
        in_rms = float(np.sqrt(np.mean(input_chunk ** 2) + 1e-9))
        self.input_level_meter = self.input_level_meter * 0.8 + in_rms * 0.2
        
        x = self.noise_gate.process(input_chunk)
        x = self.screamer.process(x)
        x = self.amp.process(x)
        x = self.cab.process(x)
        x = self.delay.process(x)
        x = self.reverb.process(x)
        
        # Master brickwall limiter to protect hearing / speakers
        x = np.clip(x, -1.0, 1.0)
        
        out_rms = float(np.sqrt(np.mean(x ** 2) + 1e-9))
        self.output_level_meter = self.output_level_meter * 0.8 + out_rms * 0.2
        
        return x.astype(np.float32)
