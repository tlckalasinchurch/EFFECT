import sounddevice as sd
import numpy as np
import threading
import time
from .dsp import GuitarSignalChain

# Guitar standard tuning reference frequencies
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def freq_to_note(freq):
    if freq < 20.0 or freq > 2000.0:
        return {"note": "--", "octave": 0, "cents": 0, "freq": 0.0}
    # A4 = 440 Hz = MIDI note 69
    midi_num = 69.0 + 12.0 * np.log2(freq / 440.0)
    nearest_midi = int(round(midi_num))
    cents = int(round((midi_num - nearest_midi) * 100.0))
    note_idx = nearest_midi % 12
    octave = (nearest_midi // 12) - 1
    return {
        "note": NOTE_NAMES[note_idx],
        "octave": octave,
        "cents": cents,
        "freq": round(freq, 1)
    }

class AudioEngine:
    def __init__(self, sample_rate=48000, block_size=512):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.chain = GuitarSignalChain(sample_rate=sample_rate)
        self.stream = None
        self.is_running = False
        self.tuner_active = False
        self.tuner_info = {"note": "--", "octave": 0, "cents": 0, "freq": 0.0}
        self._pitch_buffer = np.zeros(2048, dtype=np.float32)  # rolling buffer for pitch detection
        self._tuner_skip = 0
        self.input_device = None
        self.output_device = None
        self.reset_audio_stats()
        self.auto_detect_ux1()

    def get_device_list(self):
        devices = []
        for idx, dev in enumerate(sd.query_devices()):
            devices.append({
                "id": idx,
                "name": dev["name"],
                "hostapi": dev["hostapi"],
                "inputs": dev["max_input_channels"],
                "outputs": dev["max_output_channels"],
                "is_ux1": "UX1" in dev["name"] or "Line 6" in dev["name"]
            })
        return devices

    def auto_detect_ux1(self):
        # Look for UX1, prioritizing low-latency Windows APIs: WASAPI (2) > DirectSound (1) > others
        devices = sd.query_devices()
        in_candidates = []
        out_candidates = []

        for idx, dev in enumerate(devices):
            name = dev["name"]
            if "UX1" in name or "Line 6" in name:
                api = dev["hostapi"]
                # Higher score = better latency (WASAPI=2 -> priority 3, DirectSound=1 -> priority 2, MME=0 -> priority 1)
                prio = 3 if api == 2 else (2 if api == 1 else 1)
                if dev["max_input_channels"] > 0:
                    in_candidates.append((prio, idx))
                if dev["max_output_channels"] > 0:
                    out_candidates.append((prio, idx))

        if in_candidates:
            in_candidates.sort(key=lambda x: x[0], reverse=True)
            self.input_device = in_candidates[0][1]
        if out_candidates:
            out_candidates.sort(key=lambda x: x[0], reverse=True)
            self.output_device = out_candidates[0][1]

    def _audio_callback(self, indata, outdata, frames, time_info, status):
        t_start = time.perf_counter()
        if status:
            # Counted, not fixed: a rising count tells us the dropouts are
            # the audio path (device/buffer), not the DSP.
            for flag in ("input_underflow", "input_overflow", "output_underflow", "output_overflow"):
                if getattr(status, flag, False):
                    self.xruns[flag] += 1

        mono_in = indata[:, 0].copy()

        # Pitch detection for tuner if active (throttled to ~15 Hz to protect audio thread)
        if self.tuner_active:
            self._tuner_skip += 1
            if self._tuner_skip % 6 == 0:
                pitch = self._estimate_pitch(mono_in)
                if pitch > 0:
                    self.tuner_info = freq_to_note(pitch)
                else:
                    self.tuner_info = {"note": "--", "octave": 0, "cents": 0, "freq": 0.0}

        # Process through effect chain
        processed = self.chain.process(mono_in)
        
        # Fill stereo output
        if outdata.shape[1] >= 2:
            outdata[:, 0] = processed[:, 0] if processed.ndim > 1 else processed
            outdata[:, 1] = processed[:, 1] if processed.ndim > 1 else processed
        else:
            outdata[:, 0] = processed[:, 0] if processed.ndim > 1 else processed

        self.callback_ms_max = max(self.callback_ms_max, (time.perf_counter() - t_start) * 1000.0)
        # Output hitting full scale is clipping at the converter: buzzy, crackly sound.
        if np.max(np.abs(outdata)) >= 0.999:
            self.clipped_blocks += 1

    def reset_audio_stats(self):
        self.xruns = {"input_underflow": 0, "input_overflow": 0, "output_underflow": 0, "output_overflow": 0}
        self.callback_ms_max = 0.0
        self.clipped_blocks = 0

    def _estimate_pitch(self, audio):
        """NSDF pitch detector for guitar range (60-1200 Hz).
        Uses a 2048-sample rolling buffer for sub-block accuracy."""
        self._pitch_buffer = np.roll(self._pitch_buffer, -len(audio))
        self._pitch_buffer[-len(audio):] = audio

        buf = self._pitch_buffer
        if np.max(np.abs(buf)) < 0.015:
            return 0.0  # signal too weak

        N = len(buf)
        min_lag = int(self.sample_rate / 1200.0)   # ~40 @ 48kHz
        max_lag = int(self.sample_rate / 60.0)      # ~800 @ 48kHz

        # NSDF: r[tau] / m[tau]  (YIN-style normalization avoids harmonic errors)
        # r[tau] = sum x[i] * x[i+tau]  (unnormalized autocorr)
        # m[tau] = sum x[i]^2 + x[i+tau]^2  (normalization term)
        nsdf = np.zeros(max_lag + 1)
        x2_sum = np.sum(buf ** 2)
        for tau in range(min_lag, max_lag + 1):
            r_tau  = float(np.dot(buf[:N - tau], buf[tau:]))
            m_tau  = x2_sum + float(np.dot(buf[tau:], buf[tau:])) - float(np.dot(buf[:N - tau], buf[:N - tau]))
            nsdf[tau] = 2.0 * r_tau / (m_tau + 1e-9)

        # Find first peak that crosses the 0.8 threshold (NSDF peaks at 1.0 for perfect period)
        tau = min_lag
        while tau < max_lag and nsdf[tau] > 0:
            tau += 1
        while tau < max_lag and nsdf[tau] <= 0:
            tau += 1

        best_tau = -1
        best_nsdf = 0.0
        while tau < max_lag - 1:
            if nsdf[tau] > nsdf[tau - 1] and nsdf[tau] >= nsdf[tau + 1]:
                if nsdf[tau] > best_nsdf:
                    best_nsdf = nsdf[tau]
                    best_tau = tau
                    if best_nsdf > 0.9:
                        break  # found a strong peak — take it
            tau += 1

        if best_tau > 0 and best_nsdf > 0.6:
            # Quadratic interpolation for sub-sample precision
            a, b_val, c = nsdf[best_tau - 1], nsdf[best_tau], nsdf[best_tau + 1]
            denom = a - 2.0 * b_val + c
            delta = 0.5 * (a - c) / (denom + 1e-9) if abs(denom) > 1e-9 else 0.0
            true_lag = best_tau + delta
            if true_lag > 0:
                return float(self.sample_rate / true_lag)
        return 0.0


    def start(self, input_id=None, output_id=None):
        if self.is_running:
            self.stop()
            
        if input_id is not None:
            self.input_device = input_id
        if output_id is not None:
            self.output_device = output_id
            
        self.reset_audio_stats()
        try:
            self.stream = sd.Stream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                device=(self.input_device, self.output_device),
                channels=(1, 2),
                dtype=np.float32,
                latency='low',
                callback=self._audio_callback
            )
            self.stream.start()
            self.is_running = True
            print(f"Audio Engine Started: In={self.input_device}, Out={self.output_device}")
            return True, "Audio Engine Running"
        except Exception as e:
            err_msg = str(e)
            print("Audio Engine Start Error:", err_msg)
            # Try default device fallback
            try:
                self.stream = sd.Stream(
                    samplerate=self.sample_rate,
                    blocksize=self.block_size,
                    channels=(1, 2),
                    dtype=np.float32,
                    latency='low',
                    callback=self._audio_callback
                )
                self.stream.start()
                self.is_running = True
                return True, f"Running on Default Audio Devices (UX1 direct access had error: {err_msg})"
            except Exception as e2:
                return False, str(e2)

    def stop(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self.is_running = False

    def _get_telemetry(self):
        ram_mb = 0.0
        cpu_pct = 0.0
        try:
            import ctypes, ctypes.wintypes
            class PMC(ctypes.Structure):
                _fields_ = [('cb', ctypes.wintypes.DWORD), ('PageFaultCount', ctypes.wintypes.DWORD),
                            ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                            ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                            ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]
            psapi = ctypes.windll.psapi
            kernel32 = ctypes.windll.kernel32
            psapi.GetProcessMemoryInfo.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(PMC), ctypes.wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                ram_mb = round(pmc.WorkingSetSize / (1024 * 1024), 1)

            class FILETIME(ctypes.Structure):
                _fields_ = [('dwLowDateTime', ctypes.wintypes.DWORD), ('dwHighDateTime', ctypes.wintypes.DWORD)]
            def ft_to_int(ft): return (ft.dwHighDateTime << 32) | ft.dwLowDateTime
            idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
            if kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
                now = time.time()
                i_now, k_now, u_now = ft_to_int(idle), ft_to_int(kernel), ft_to_int(user)
                if hasattr(self, '_last_sys_times'):
                    i_prev, k_prev, u_prev, t_prev = self._last_sys_times
                    if now - t_prev > 0.05:
                        idle_diff = i_now - i_prev
                        total_diff = (k_now - k_prev) + (u_now - u_prev)
                        if total_diff > 0:
                            cpu_pct = round(max(0.0, min(100.0, 100.0 * (1.0 - idle_diff / total_diff))), 1)
                        self._last_sys_times = (i_now, k_now, u_now, now)
                else:
                    self._last_sys_times = (i_now, k_now, u_now, now)
        except Exception:
            pass
        return {"cpu_percent": cpu_pct, "ram_mb": ram_mb}

    def get_state(self):
        return {
            "is_running": self.is_running,
            "sample_rate": self.sample_rate,
            "block_size": self.block_size,
            "input_device": self.input_device,
            "output_device": self.output_device,
            "input_meter": round(float(self.chain.input_level_meter) * 100.0, 1),
            "output_meter": round(float(self.chain.output_level_meter) * 100.0, 1),
            "nam": self.chain.nam.describe() if self.chain.nam is not None else None,
            "system": self._get_telemetry(),
            "audio_stats": {
                "xruns": dict(self.xruns),
                "callback_ms_max": round(self.callback_ms_max, 2),
                "clipped_blocks": self.clipped_blocks,
                "deadline_ms": round(self.block_size / self.sample_rate * 1000.0, 2),
            },
            "tuner": self.tuner_info if self.tuner_active else None,
            "chain": {
                "master_volume": getattr(self.chain, 'master_volume', 1.0),
                "input": {
                    "trim_db": getattr(self.chain, 'input_trim_db', 0.0),
                },
                "gate": {
                    "enabled": self.chain.noise_gate.enabled,
                    "threshold": self.chain.noise_gate.threshold_db,
                    "hold_ms": getattr(self.chain.noise_gate, 'hold_ms', 50.0),
                    "range_db": getattr(self.chain.noise_gate, 'range_db', -60.0),
                    "release_ms": getattr(self.chain.noise_gate, 'release_ms', 50.0),
                },
                "screamer": {
                    "enabled": self.chain.screamer.enabled,
                    "drive": self.chain.screamer.drive,
                    "tone": self.chain.screamer.tone,
                    "level": self.chain.screamer.level
                },
                "amp": {
                    "enabled": self.chain.amp.enabled,
                    "gain": self.chain.amp.gain,
                    "bass": self.chain.amp.bass,
                    "mid": self.chain.amp.mid,
                    "treble": self.chain.amp.treble,
                    "presence": self.chain.amp.presence,
                    "master": self.chain.amp.master,
                    "model": self.chain.amp.model,
                    "bright": getattr(self.chain.amp, 'bright', False),
                },
                "cab": {
                    "enabled": self.chain.cab.enabled,
                    "ir_name": self.chain.cab.ir_name,
                    "level": getattr(self.chain.cab, 'level', 1.0),
                    "lowcut": getattr(self.chain.cab, 'lowcut_hz', 20.0),
                    "highcut": getattr(self.chain.cab, 'highcut_hz', 20000.0),
                    "mix": getattr(self.chain.cab, 'mix', 1.0),
                },
                "delay": {
                    "enabled": self.chain.delay.enabled,
                    "time": self.chain.delay.time_sec,
                    "feedback": self.chain.delay.feedback,
                    "mix": self.chain.delay.mix
                },
                "reverb": {
                    "enabled": self.chain.reverb.enabled,
                    "decay": self.chain.reverb.decay,
                    "mix": self.chain.reverb.mix,
                    "tone": getattr(self.chain.reverb, 'tone', 0.5),
                    "type": getattr(self.chain.reverb, 'reverb_type', 'plate'),
                },
                "pitch": {
                    "enabled": getattr(self.chain.pitch_shifter, 'enabled', False),
                    "semitones": getattr(self.chain.pitch_shifter, 'semitones', 0.0),
                    "target_semitones": getattr(self.chain.pitch_shifter, 'target_semitones', 0.0),
                    "cents": getattr(self.chain.pitch_shifter, 'cents', 0.0),
                    "mix": getattr(self.chain.pitch_shifter, 'mix', 1.0),
                    "glide": getattr(self.chain.pitch_shifter, 'glide_pct', 0.0),
                }
            }
        }

