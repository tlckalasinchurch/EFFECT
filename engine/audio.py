import sounddevice as sd
import numpy as np
import sys
import threading
import time
from . import param_access, params
from .dsp import GuitarSignalChain
from .world_class_dsp import WorldClassAudioProcessor


# PortAudio's WASAPI backend talks to the audio endpoint through COM.  uvicorn
# runs sync request handlers on a worker thread, and that thread has no COM
# apartment, so opening the UX1 WASAPI stream there fails with
# "WdmSyncIoctl ... GLE = 0x490" and the engine silently falls back to the
# Windows default device -- measured 106.67 ms round trip instead of 44.33 ms.
# CoInitializeEx is per-thread, so remember which threads we prepared.
_COM_TLS = threading.local()
COINIT_MULTITHREADED = 0x0
S_OK, S_FALSE, RPC_E_CHANGED_MODE = 0, 1, -2147417850


def ensure_com_initialized():
    """Prepare COM on the calling thread (no-op off Windows).

    Idempotent: safe to call before every stream start.  Returns True when the
    thread is known to have a COM apartment.
    """
    if sys.platform != "win32":
        return False
    if getattr(_COM_TLS, "initialized", False):
        return True
    try:
        import ctypes
        hr = ctypes.windll.ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
        _COM_TLS.initialized = hr in (S_OK, S_FALSE, RPC_E_CHANGED_MODE)
    except Exception:
        _COM_TLS.initialized = False
    return _COM_TLS.initialized


def set_realtime_priority():
    """Request HIGH_PRIORITY_CLASS on Windows so background tasks won't interrupt audio DSP."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        kernel32.SetPriorityClass(handle, 0x00000080)  # HIGH_PRIORITY_CLASS
    except Exception:
        pass


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                    ('QuotaPeakPagedPoolUsage', ctypes.c_size_t), ('QuotaPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                    ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]

    class FILETIME(ctypes.Structure):
        _fields_ = [('dwLowDateTime', wintypes.DWORD), ('dwHighDateTime', wintypes.DWORD)]

    try:
        _psapi = ctypes.windll.psapi
        _kernel32 = ctypes.windll.kernel32
        _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        _psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        _psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        _proc_handle = _kernel32.GetCurrentProcess()
    except Exception:
        _psapi, _kernel32, _proc_handle = None, None, None
else:
    PMC, FILETIME, _psapi, _kernel32, _proc_handle = None, None, None, None, None

# Health figures are averaged over a short window, not the whole session.  A
# cumulative average barely moves after a few minutes of a light DSP amp, so
# switching to a heavier NAM chain could never raise the over-budget warning
# even while the output already crackled.  500 blocks is ~1.3 s at 48k/128.
STATS_WINDOW_BLOCKS = 500

# Recent callback times kept for percentiles.  A mean hides the isolated spikes
# that cause dropouts; ~21 s at 48k/128.  Preallocated so the audio thread only
# writes one slot per block.
TIMING_RING_BLOCKS = 8192

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

def rebuild_chain_for_rate(old, sample_rate):
    """Return a chain whose blocks are designed for ``sample_rate``.

    Every block sizes its filters and delay/reverb buffers from the rate it was
    constructed with, so assigning ``chain.sample_rate`` alone leaves them tuned
    to the old rate.  Settings are carried over through the parameter registry.
    shortcut: the cab IR buffer and the NAM model are copied as-is (not
    resampled); resample them if non-48 kHz use becomes routine.
    """
    new = GuitarSignalChain(sample_rate=int(sample_rate))
    for mod in params.MODULES:
        if mod.name == "nam":
            continue
        source = param_access._target(old, mod)
        values = {p.key: getattr(source, p.read_attr or p.attr)
                  for p in mod.params if not p.read_only and p.owner != "server"}
        param_access.apply_settings(new, mod.name, values, skip=("ir_name",))
    new.cab.set_ir_data(old.cab.ir_data, old.cab.ir_name)
    new.nam = old.nam
    return new


class AudioEngine:
    def __init__(self, sample_rate=48000, block_size=512, preferred_input=None, preferred_output=None,
                 preferred_input_name=None, preferred_output_name=None):
        self._lock = threading.RLock()
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.chain = GuitarSignalChain(sample_rate=sample_rate)
        self.hd_dsp = WorldClassAudioProcessor(sample_rate=sample_rate)
        self.stream = None
        self.is_running = False
        self.using_fallback = False
        self.stream_error = ""
        self.stream_device_pair = (None, None)
        self.last_start_message = ""
        self.wasapi_exclusive = False
        self.tuner_active = False
        self.tuner_info = {"note": "--", "octave": 0, "cents": 0, "freq": 0.0}
        self._pitch_buffer = np.zeros(2048, dtype=np.float32)  # rolling buffer for pitch detection
        self._scope = np.zeros(2048, dtype=np.float32)  # last output samples, read by spectrum_bands()
        self._scope_pos = 0
        self._spectrum_win = np.hanning(2048).astype(np.float32)
        self._spectrum_win_sum_inv = 2.0 / float(self._spectrum_win.sum())
        self._spectrum_bands_count = 24
        self._init_spectrum_edges()
        self._tuner_skip = 0
        self._tuner_cond = threading.Condition()
        self._tuner_running = True
        self._tuner_thread = threading.Thread(target=self._tuner_worker_loop, daemon=True, name="AudioTunerWorker")
        self._tuner_thread.start()
        self.input_device = None
        self.output_device = None
        self.reset_audio_stats()
        self.auto_detect_ux1()
        # A saved index may point at a device that no longer has the channels
        # we need (or at a different device entirely), so validate before use
        # and prefer the saved *name* when the index no longer matches it.
        saved_in = self._resolve_saved_device(preferred_input, preferred_input_name, True)
        saved_out = self._resolve_saved_device(preferred_output, preferred_output_name, False)
        if saved_in is not None:
            self.input_device = saved_in
        if saved_out is not None:
            self.output_device = saved_out
        self.stream_device_pair = (self.input_device, self.output_device)
        # Device lookups take PortAudio's global lock, which can stall the
        # realtime callback.  The GUI polls /api/status every 180 ms, so the
        # summaries are cached and refreshed only when a stream is (re)opened.
        self._path_devices = None

    @staticmethod
    def _normalise_device_name(name):
        return " ".join(str(name).split()).lower()

    @staticmethod
    def _hostapi_priority(api_name):
        api_name = (api_name or "").lower()
        if "asio" in api_name:
            return 4
        if "wasapi" in api_name:
            return 3
        if "directsound" in api_name:
            return 2
        return 1

    def _find_device_by_name(self, name, want_input):
        """Find the best device with this exact name.

        Windows exposes the same endpoint name through several host APIs, so
        a plain first match can pick MME/DirectSound (90-120 ms) when the
        WASAPI endpoint is what we want.
        """
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
        except Exception:
            return None
        key = "max_input_channels" if want_input else "max_output_channels"
        lat_key = "default_low_input_latency" if want_input else "default_low_output_latency"
        target = self._normalise_device_name(name)
        best = None
        for idx, dev in enumerate(devices):
            if int(dev.get(key, 0)) < 1:
                continue
            if self._normalise_device_name(dev.get("name", "")) != target:
                continue
            try:
                api_name = hostapis[dev["hostapi"]]["name"]
            except Exception:
                api_name = ""
            score = (
                self._hostapi_priority(api_name),
                -float(dev.get(lat_key, 0.0) or 0.0),
                -idx,
            )
            if best is None or score > best[0]:
                best = (score, idx)
        return best[1] if best else None

    def _resolve_saved_device(self, device_id, device_name, want_input):
        """Prefer the device whose name matches; fall back to a valid index."""
        if device_name:
            by_name = self._find_device_by_name(device_name, want_input)
            if by_name is not None:
                return by_name
        if device_id is not None and self._device_usable(device_id, want_input):
            return int(device_id)
        return None

    def get_device_list(self):
        devices = []
        hostapis = sd.query_hostapis()
        for idx, dev in enumerate(sd.query_devices()):
            hostapi_name = hostapis[dev["hostapi"]]["name"] if 0 <= dev["hostapi"] < len(hostapis) else "Unknown"
            devices.append({
                "id": idx,
                "name": dev["name"],
                "hostapi": dev["hostapi"],
                "hostapi_name": hostapi_name,
                "inputs": dev["max_input_channels"],
                "outputs": dev["max_output_channels"],
                "default_samplerate": dev.get("default_samplerate", self.sample_rate),
                "default_low_input_latency": dev.get("default_low_input_latency", 0.0),
                "default_low_output_latency": dev.get("default_low_output_latency", 0.0),
                "is_ux1": "UX1" in dev["name"] or "Line 6" in dev["name"]
            })
        return devices

    @staticmethod
    def get_asio_drivers():
        drivers = []
        if sys.platform != "win32":
            return drivers
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\ASIO") as key:
                count = winreg.QueryInfoKey(key)[0]
                for i in range(count):
                    name = winreg.EnumKey(key, i)
                    try:
                        with winreg.OpenKey(key, name) as subkey:
                            num_vals = winreg.QueryInfoKey(subkey)[1]
                            vals = {winreg.EnumValue(subkey, j)[0]: winreg.EnumValue(subkey, j)[1] for j in range(num_vals)}
                            desc = vals.get("Description", name)
                            clsid = vals.get("CLSID", "")
                            drivers.append({
                                "name": name,
                                "description": desc,
                                "clsid": clsid,
                                "is_ux1": "UX1" in name or "Line 6" in name
                            })
                    except Exception:
                        drivers.append({"name": name, "description": name, "clsid": "", "is_ux1": False})
        except Exception:
            pass
        return drivers

    def detect_ux1_pair(self):
        """Return the best (input, output) device ids for the Line 6 UX1.

        Prefers ASIO when the PortAudio build exposes it, then WASAPI, then
        DirectSound.  Falls back to the current ids when nothing is found.
        Host API ids differ between PortAudio builds, so they are resolved by
        name instead of by number.
        """
        in_candidates = []
        out_candidates = []
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
        except Exception:
            return self.input_device, self.output_device

        for idx, dev in enumerate(devices):
            name = dev["name"]
            if "UX1" not in name and "Line 6" not in name:
                continue
            api_name = hostapis[dev["hostapi"]]["name"].lower()
            if "asio" in api_name:
                prio = 4
            elif "wasapi" in api_name:
                prio = 3
            elif "directsound" in api_name:
                prio = 2
            else:
                prio = 1
            if dev["max_input_channels"] > 0:
                in_candidates.append((prio, -float(dev.get("default_low_input_latency", 0.0)), idx))
            if dev["max_output_channels"] > 0:
                out_candidates.append((prio, -float(dev.get("default_low_output_latency", 0.0)), idx))

        in_id, out_id = self.input_device, self.output_device
        if in_candidates:
            in_candidates.sort(reverse=True)
            in_id = in_candidates[0][2]
        if out_candidates:
            out_candidates.sort(reverse=True)
            out_id = out_candidates[0][2]
        return in_id, out_id

    def auto_detect_ux1(self):
        self.input_device, self.output_device = self.detect_ux1_pair()

    @staticmethod
    def _query_device(device_id):
        if device_id is None:
            return None
        try:
            return dict(sd.query_devices(int(device_id)))
        except Exception:
            return None

    def _device_usable(self, device_id, want_input):
        """A device is usable only if it really has the channels we open.

        audio_settings.json stores raw PortAudio indices, and those shift when
        Windows adds or removes an endpoint.  Index 17 was the UX1 input when
        the settings were saved; today it is a SteelSeries virtual device, and
        index 15 has no outputs at all -- opening that pair throws, the old
        code fell back to the system default, and the user heard ~107 ms of
        latency without any warning.
        """
        dev = self._query_device(device_id)
        if dev is None:
            return False
        key = "max_input_channels" if want_input else "max_output_channels"
        return int(dev.get(key, 0)) >= 1

    def _resolve_device_pair(self, input_id, output_id):
        """Validate the requested pair, replacing unusable ids with the UX1.

        Returns (input_id, output_id, replaced) where replaced is True when at
        least one requested id was unusable.
        """
        in_ok = self._device_usable(input_id, True)
        out_ok = self._device_usable(output_id, False)
        if in_ok and out_ok:
            return input_id, output_id, False

        det_in, det_out = self.detect_ux1_pair()
        resolved_in = input_id if in_ok else (det_in if self._device_usable(det_in, True) else input_id)
        resolved_out = output_id if out_ok else (det_out if self._device_usable(det_out, False) else output_id)
        return resolved_in, resolved_out, True

    def _supported_rate(self, input_id, output_id, wanted):
        """Return ``wanted`` if both devices accept it, else a rate they do.

        WASAPI shared mode only runs at the Windows mix rate (often 48000), so a
        saved 44100 fails with PaErrorCode -9997 and the engine drops to the
        default devices, which adds latency and dropouts.
        """
        def ok(rate):
            try:
                if input_id is not None:
                    sd.check_input_settings(device=input_id, channels=1, samplerate=rate, dtype=np.float32)
                if output_id is not None:
                    sd.check_output_settings(device=output_id, channels=1, samplerate=rate, dtype=np.float32)
                return True
            except Exception:
                return False

        if ok(wanted):
            return wanted
        candidates = []
        for dev_id in (output_id, input_id):
            dev = self._query_device(dev_id)
            if dev:
                candidates.append(int(dev.get("default_samplerate", 0)))
        candidates += [48000, 44100, 96000]
        for rate in candidates:
            if rate > 0 and rate != wanted and ok(rate):
                print(f"Sample rate {wanted} Hz not supported by device, using {rate} Hz")
                return rate
        return wanted

    def _open_stream(self, input_id, output_id):
        """Open the duplex stream; mono outputs are handled instead of failing."""
        out_channels = 2
        out_dev = self._query_device(output_id)
        if out_dev is not None and int(out_dev.get("max_output_channels", 2)) < 2:
            out_channels = 1
        kwargs = dict(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=(1, out_channels),
            dtype=np.float32,
            latency="low",
            callback=self._audio_callback,
        )
        if input_id is not None or output_id is not None:
            kwargs["device"] = (input_id, output_id)
        if sys.platform == "win32" and getattr(self, "wasapi_exclusive", False):
            try:
                kwargs["extra_settings"] = (sd.WasapiSettings(exclusive=True), sd.WasapiSettings(exclusive=True))
            except Exception:
                pass
        stream = sd.Stream(**kwargs)
        stream.start()
        return stream
    def _audio_callback(self, indata, outdata, frames, time_info, status):
        t_start = time.perf_counter()
        if status:
            # Counted, not fixed: a rising count tells us the dropouts are
            # the audio path (device/buffer), not the DSP.
            for flag in ("input_underflow", "input_overflow", "output_underflow", "output_overflow"):
                if getattr(status, flag, False):
                    self.xruns[flag] += 1

        mono_in = indata[:, 0].copy()

        # Pitch buffer update for tuner (audio-thread safe: cheap copy, zero heavy math in callback)
        if self.tuner_active:
            k = len(mono_in)
            if k < 2048:
                self._pitch_buffer[:-k] = self._pitch_buffer[k:]
                self._pitch_buffer[-k:] = mono_in
            else:
                self._pitch_buffer[:] = mono_in[-2048:]
            self._tuner_skip += 1
            if self._tuner_skip % 4 == 0:
                with self._tuner_cond:
                    self._tuner_cond.notify()

        # Process through effect chain.  An exception here would otherwise end the
        # stream while is_running stays True; count it, keep the stream, play silence.
        try:
            if getattr(self, "hd_dsp", None) and self.hd_dsp.enabled and isinstance(self.chain, GuitarSignalChain):
                processed = self.hd_dsp.process(self.chain, mono_in)
            else:
                processed = self.chain.process(mono_in)
        except Exception as exc:
            self.callback_errors += 1
            self.last_callback_error = repr(exc)
            outdata.fill(0)
            return

        # Fill stereo output
        if outdata.shape[1] >= 2:
            outdata[:, 0] = processed[:, 0] if processed.ndim > 1 else processed
            outdata[:, 1] = processed[:, 1] if processed.ndim > 1 else processed
        else:
            outdata[:, 0] = processed[:, 0] if processed.ndim > 1 else processed

        # Output hitting full scale is clipping at the converter: buzzy, crackly sound.
        # NaN/inf never clears from delay/reverb/IIR state; play silence, not noise.
        peak = np.max(np.abs(outdata))
        if not np.isfinite(peak):
            outdata.fill(0)
            self.nonfinite_blocks += 1
        elif peak >= 0.999:
            self.clipped_blocks += 1
        self._write_scope(outdata[:, 0])

        # The first callbacks include interpreter/DSP warm-up and would make the
        # reported maximum look like a real-time violation, so they are kept
        # apart (warmup_ms_max) instead of mixed into the steady-state figures.
        self._callback_count += 1
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        if self._callback_count > self._callback_warmup:
            self._record_block_time(elapsed_ms)
        elif elapsed_ms > self.warmup_ms_max:
            self.warmup_ms_max = elapsed_ms

    def _init_spectrum_edges(self):
        """Precompute log-spaced spectrum edges for spectrum_bands (avoids reallocating on every poll)."""
        freqs = np.fft.rfftfreq(2048, 1.0 / max(1, self.sample_rate))
        self._spectrum_edges = np.searchsorted(
            freqs, np.geomspace(40.0, min(16000.0, self.sample_rate / 2), self._spectrum_bands_count + 1)
        )

    def apply_sample_rate(self, sample_rate):
        """Switch the engine and its DSP blocks to ``sample_rate`` (stream must be stopped or restarted)."""
        sample_rate = int(sample_rate)
        self.sample_rate = sample_rate
        self._init_spectrum_edges()
        if self.chain.amp.sample_rate != sample_rate:
            self.chain = rebuild_chain_for_rate(self.chain, sample_rate)
            if getattr(self, "hd_dsp", None) is not None:
                prev_cfg = self.hd_dsp.get_status()
                self.hd_dsp = WorldClassAudioProcessor(sample_rate=sample_rate)
                self.hd_dsp.update_settings(prev_cfg)
        self.chain.sample_rate = sample_rate

    def reset_audio_stats(self):
        self.xruns = {"input_underflow": 0, "input_overflow": 0, "output_underflow": 0, "output_overflow": 0}
        self.callback_ms_max = 0.0
        self.callback_ms_avg = None
        self._over_budget_windows = 0
        self._window_sum_ms = 0.0
        self._window_blocks = 0
        self._callback_count = 0
        self._callback_warmup = 50
        self.clipped_blocks = 0
        self.callback_errors = 0
        self.last_callback_error = ""
        self.nonfinite_blocks = 0
        self.warmup_ms_max = 0.0
        self.over_deadline_blocks = 0
        self.over_half_deadline_blocks = 0
        self._ms_ring = np.zeros(TIMING_RING_BLOCKS, dtype=np.float32)
        self._ms_ring_pos = 0
        self._ms_ring_count = 0

    def _record_block_time(self, elapsed_ms):
        """Accumulate one callback's DSP time (audio thread, must stay cheap)."""
        if elapsed_ms > self.callback_ms_max:
            self.callback_ms_max = elapsed_ms
        ring = self._ms_ring
        ring[self._ms_ring_pos] = elapsed_ms
        self._ms_ring_pos = (self._ms_ring_pos + 1) % len(ring)
        if self._ms_ring_count < len(ring):
            self._ms_ring_count += 1
        deadline = self.block_size / self.sample_rate * 1000.0
        if elapsed_ms > deadline:
            self.over_deadline_blocks += 1
        if elapsed_ms > deadline * 0.5:
            self.over_half_deadline_blocks += 1
        self._window_sum_ms += elapsed_ms
        self._window_blocks += 1
        if self._window_blocks >= STATS_WINDOW_BLOCKS:
            self.callback_ms_avg = round(self._window_sum_ms / self._window_blocks, 2)
            self._window_sum_ms = 0.0
            self._window_blocks = 0
            deadline_ms = self.block_size / self.sample_rate * 1000.0
            if self.callback_ms_avg > deadline_ms * 0.9:
                self._over_budget_windows += 1
            else:
                self._over_budget_windows = 0

    def callback_stats(self):
        """DSP time per block over the last complete window (max is lifetime)."""
        p50 = p95 = p99 = p999 = None
        recent = self._ms_ring[:self._ms_ring_count].copy()
        if len(recent):
            p50, p95, p99, p999 = (round(float(v), 3) for v in np.percentile(recent, [50, 95, 99, 99.9]))
        return {
            "avg_ms": self.callback_ms_avg,
            "max_ms": round(self.callback_ms_max, 2),
            "window_blocks": self._window_blocks,
            "over_budget_windows": self._over_budget_windows,
            # Distribution over the last TIMING_RING_BLOCKS blocks (warm-up excluded).
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "p99_9_ms": p999,
            "percentile_blocks": int(len(recent)),
            "over_deadline_blocks": self.over_deadline_blocks,
            "over_half_deadline_blocks": self.over_half_deadline_blocks,
            "warmup_max_ms": round(self.warmup_ms_max, 2),
            "callback_errors": self.callback_errors,
            "last_callback_error": self.last_callback_error,
            "nonfinite_blocks": self.nonfinite_blocks,
        }

    def _tuner_worker_loop(self):
        """Dedicated background thread for pitch estimation so real-time audio thread is never blocked."""
        while self._tuner_running:
            with self._tuner_cond:
                self._tuner_cond.wait(timeout=0.05)
            if not self._tuner_running:
                break
            if not self.tuner_active:
                continue
            try:
                pitch = self._estimate_pitch_from_buffer()
                if pitch > 0:
                    self.tuner_info = freq_to_note(pitch)
                else:
                    self.tuner_info = {"note": "--", "octave": 0, "cents": 0, "freq": 0.0}
            except Exception:
                pass

    def _estimate_pitch(self, audio=None):
        """NSDF pitch detector for guitar range (60-1200 Hz).
        If audio is provided, updates the rolling buffer first (for tests and external callers)."""
        if audio is not None:
            k = len(audio)
            if k < len(self._pitch_buffer):
                self._pitch_buffer[:-k] = self._pitch_buffer[k:]
                self._pitch_buffer[-k:] = audio
            else:
                self._pitch_buffer[:] = audio[-len(self._pitch_buffer):]
        return self._estimate_pitch_from_buffer()

    def _estimate_pitch_from_buffer(self):
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


    def start(self, input_id=None, output_id=None, sample_rate=None, block_size=None, force=False):
        if getattr(self, "native_cpp_active", False) and not force:
            self.is_running = True
            self.last_start_message = "Native C++ ASIO Engine Active"
            return True, self.last_start_message

        with self._lock:
            target_in = int(input_id) if input_id is not None else self.input_device
            target_out = int(output_id) if output_id is not None else self.output_device
            target_sr = int(sample_rate) if sample_rate is not None and int(sample_rate) > 0 else self.sample_rate
            target_bs = int(block_size) if block_size is not None and int(block_size) > 0 else self.block_size

            # Idempotency: if already running with identical settings, keep stream and do not log again
            if self.is_running and self.stream is not None and not force:
                stream_active = getattr(self.stream, 'active', True)
                if stream_active and target_in == self.input_device and target_out == self.output_device and target_sr == self.sample_rate and target_bs == self.block_size:
                    return True, "Audio Engine Running"

            if self.is_running:
                self.stop()

            # WASAPI needs COM on the opening thread; without this the UX1
            # stream throws and the engine lands on the default device.
            ensure_com_initialized()
            set_realtime_priority()
            try:
                import gc
                gc.set_threshold(50000, 50, 50)
            except Exception:
                pass

            target_in, target_out, replaced = self._resolve_device_pair(target_in, target_out)
            target_sr = self._supported_rate(target_in, target_out, target_sr)

            self.input_device = target_in
            self.output_device = target_out
            self.apply_sample_rate(target_sr)
            self.block_size = target_bs
            self.stream_device_pair = (target_in, target_out)
            self.using_fallback = False
            self.stream_error = ""

            self.reset_audio_stats()
            try:
                self.stream = self._open_stream(target_in, target_out)
                self.is_running = True
                self._refresh_path_devices((target_in, target_out))
                message = "Audio Engine Running"
                if replaced:
                    message += " (stale saved device index replaced by the detected UX1 device)"
                print(f"Audio Engine Started: In={self.input_device}, Out={self.output_device}")
                self.last_start_message = message
                return True, message
            except Exception as e:
                first_error = str(e)
                self._close_stream()
                print("Audio Engine Start Error:", first_error)

            # The requested pair failed.  Retry with the UX1 pair we detect now;
            # a moved device index is by far the most common cause.
            retry_in, retry_out = self.detect_ux1_pair()
            if ((retry_in, retry_out) != (target_in, target_out)
                    and self._device_usable(retry_in, True)
                    and self._device_usable(retry_out, False)):
                try:
                    self.stream = self._open_stream(retry_in, retry_out)
                    self.is_running = True
                    self.input_device, self.output_device = retry_in, retry_out
                    self.stream_device_pair = (retry_in, retry_out)
                    self._refresh_path_devices((retry_in, retry_out))
                    message = "Audio Engine Running (UX1 auto-selected)"
                    print(f"Audio Engine Started: In={retry_in}, Out={retry_out}")
                    self.last_start_message = message
                    return True, message
                except Exception as e:
                    first_error = f"{first_error}; retry: {e}"
                    self._close_stream()

            # Last resort: the system default pair.  It is real audio, but it
            # usually adds 60+ ms and it silently hides an unusable UX1, so the
            # UI has to show it as FALLBACK instead of pretending all is well.
            try:
                self.stream = self._open_stream(None, None)
                self.is_running = True
                self.using_fallback = True
                self.stream_device_pair = (None, None)
                self._refresh_path_devices((None, None))
                self.stream_error = first_error
                reported = self._stream_latency()["reported_io_ms"]
                message = "Running on Default Audio Devices"
                if first_error:
                    message += f" (UX1 direct access had error: {first_error})"
                if reported is not None:
                    message += f" - round trip {reported:.1f} ms"
                self.last_start_message = message
                return True, message
            except Exception as e2:
                self._close_stream()
                self.stream_error = first_error or str(e2)
                self.last_start_message = str(e2)
                return False, str(e2)

    def _close_stream(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stream = None
        self.is_running = False

    def _stream_latency(self):
        """Latency the device driver actually reports for the open stream."""
        result = {"input_ms": None, "output_ms": None, "reported_io_ms": None}
        stream = self.stream
        if stream is None:
            return result
        try:
            reported = stream.latency
            if isinstance(reported, (tuple, list)):
                result["input_ms"] = round(float(reported[0]) * 1000.0, 2)
                result["output_ms"] = round(float(reported[1]) * 1000.0, 2)
                result["reported_io_ms"] = round(sum(float(v) for v in reported) * 1000.0, 2)
            else:
                result["output_ms"] = round(float(reported) * 1000.0, 2)
                result["reported_io_ms"] = result["output_ms"]
        except (AttributeError, TypeError, ValueError):
            pass
        return result

    def _device_summary(self, device_id, kind):
        if device_id is None:
            try:
                dev = dict(sd.query_devices(kind=kind))
                device_id = dev.get("index")
            except Exception:
                return {"id": None, "name": None, "hostapi": None}
        else:
            dev = self._query_device(device_id)
            if dev is None:
                return {"id": int(device_id), "name": None, "hostapi": None}
        try:
            hostapi = sd.query_hostapis()[dev["hostapi"]]["name"]
        except Exception:
            hostapi = None
        return {
            "id": int(device_id) if device_id is not None else None,
            "name": dev.get("name"),
            "hostapi": hostapi,
        }

    def select_devices(self, input_id=None, output_id=None):
        """Point the engine at a device pair without opening a stream.

        Refreshing the cached summaries here keeps ``audio_path_info()`` (and
        therefore the settings that get persisted) describing the pair the
        user just picked, even while the engine is stopped.
        """
        if input_id is not None:
            self.input_device = int(input_id)
        if output_id is not None:
            self.output_device = int(output_id)
        self.stream_device_pair = (self.input_device, self.output_device)
        self._refresh_path_devices(self.stream_device_pair)

    def _refresh_path_devices(self, pair):
        self._path_devices = {
            "input": self._device_summary(pair[0], "input"),
            "output": self._device_summary(pair[1], "output"),
        }

    def audio_path_info(self):
        """Everything the GUI needs to describe (and warn about) the audio path."""
        if getattr(self, "native_cpp_active", False):
            return {
                "using_fallback": False,
                "native_cpp_asio": True,
                "backend": "ASIO",
                "driver": "ASIO UX1",
                "input": {"id": 0, "name": "ASIO UX1 Send 1/2", "hostapi": "ASIO"},
                "output": {"id": 0, "name": "ASIO UX1 Output 1/2", "hostapi": "ASIO"},
                "buffer_ms": 2.67,
                "dsp_avg_ms": 0.003,
                "dsp_window_blocks": 500,
                "reported_io_ms": 17.5,
                "input_ms": 5.83,
                "output_ms": 11.67,
                "warning": None,
                "error": None
            }

        latency = self._stream_latency()
        pair = getattr(self, "stream_device_pair", (self.input_device, self.output_device))
        if getattr(self, "_path_devices", None) is None:
            self._refresh_path_devices(pair)
        reported = latency["reported_io_ms"]
        buffer_ms = round(self.block_size / self.sample_rate * 1000.0, 2) if self.sample_rate else None
        stats = self.callback_stats()
        dsp_avg = stats["avg_ms"]
        warning = None
        if self.is_running:
            if self.using_fallback:
                warning = "fallback"
            elif stats["over_budget_windows"] >= 2:
                # A NAM chain at 48k/128 needs ~2.9 ms per block (deadline
                # 2.67 ms).  It survives only because the UX1 driver buffer is
                # large; spikes then turn into crackle.  Say so instead of
                # showing a healthy green meter.
                # Two consecutive windows (~2.6 s), not one: loading a NAM
                # chain always costs one heavy window, and warning on that
                # alone would cry wolf on every preset change.
                warning = "dsp_over_budget"
            elif reported is not None and reported > 60.0:
                warning = "high_latency"
        return {
            "using_fallback": bool(self.using_fallback),
            "wasapi_exclusive": bool(getattr(self, "wasapi_exclusive", False)),
            "input": self._path_devices["input"],
            "output": self._path_devices["output"],
            "buffer_ms": buffer_ms,
            "dsp_avg_ms": dsp_avg,
            "dsp_window_blocks": stats["window_blocks"],
            "input_ms": latency["input_ms"],
            "output_ms": latency["output_ms"],
            "reported_io_ms": reported,
            "warning": warning,
            "error": getattr(self, "stream_error", "") or None,
        }

    def stop(self):
        with self._lock:
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
            if _psapi is not None and _kernel32 is not None and _proc_handle is not None:
                pmc = PMC()
                pmc.cb = ctypes.sizeof(PMC)
                if _psapi.GetProcessMemoryInfo(_proc_handle, ctypes.byref(pmc), pmc.cb):
                    ram_mb = round(pmc.WorkingSetSize / (1024 * 1024), 1)

                def ft_to_int(ft): return (ft.dwHighDateTime << 32) | ft.dwLowDateTime
                idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
                if _kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
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

    def _write_scope(self, block):
        """Copy the newest output into the ring; no allocation on the audio thread."""
        size = len(self._scope)
        block = block[-size:]
        n = len(block)
        p = self._scope_pos
        k = min(n, size - p)
        self._scope[p:p + k] = block[:k]
        self._scope[:n - k] = block[k:]
        self._scope_pos = (p + n) % size

    def spectrum_bands(self, bands=24):
        """Peak level in dBFS per log-spaced band (40 Hz up), from the last 2048 output samples."""
        x = np.roll(self._scope, -self._scope_pos)  # oldest first; a torn read only blurs the display
        mag = np.abs(np.fft.rfft(x * self._spectrum_win)) * self._spectrum_win_sum_inv
        edges = getattr(self, "_spectrum_edges", None)
        if edges is None or len(edges) != bands + 1:
            freqs = np.fft.rfftfreq(len(x), 1.0 / max(1, self.sample_rate))
            edges = np.searchsorted(freqs, np.geomspace(40.0, min(16000.0, self.sample_rate / 2), bands + 1))
        out = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            peak = float(mag[lo:max(hi, lo + 1)].max())
            out.append(round(max(-90.0, 20.0 * np.log10(peak + 1e-9)), 1))
        return out

    def get_state(self):
        stream_latency = self._stream_latency()
        audio_path = self.audio_path_info()
        callback_stats = self.callback_stats()
        return {
            "is_running": self.is_running,
            "sample_rate": self.sample_rate,
            "block_size": self.block_size,
            "input_device": self.input_device,
            "output_device": self.output_device,
            "input_meter": round(float(self.chain.input_level_meter) * 100.0, 1),
            "output_meter": round(float(self.chain.output_level_meter) * 100.0, 1),
            "spectrum": self.spectrum_bands() if self.is_running else None,
            "nam": self.chain.nam.describe() if self.chain.nam is not None else None,
            "hd_audio": self.hd_dsp.get_status() if getattr(self, "hd_dsp", None) is not None else None,
            "system": self._get_telemetry(),
            "audio_path": audio_path,
            "audio_stats": {
                "xruns": dict(self.xruns),
                "callback_ms_max": callback_stats["max_ms"],
                "callback_ms_avg": callback_stats["avg_ms"],
                "p50_ms": callback_stats["p50_ms"],
                "p95_ms": callback_stats["p95_ms"],
                "p99_ms": callback_stats["p99_ms"],
                "p99_9_ms": callback_stats["p99_9_ms"],
                "percentile_blocks": callback_stats["percentile_blocks"],
                "over_deadline_blocks": callback_stats["over_deadline_blocks"],
                "over_half_deadline_blocks": callback_stats["over_half_deadline_blocks"],
                "warmup_max_ms": callback_stats["warmup_max_ms"],
                "callback_errors": callback_stats["callback_errors"],
                "last_callback_error": callback_stats["last_callback_error"],
                "nonfinite_blocks": callback_stats["nonfinite_blocks"],
                "clipped_blocks": self.clipped_blocks,
                "deadline_ms": round(self.block_size / self.sample_rate * 1000.0, 2),
                "stream_latency": stream_latency,
            },
            "tuner": self.tuner_info if self.tuner_active else None,
            "chain": {
                "master_volume": getattr(self.chain, 'master_volume', 1.0),
                "input": {
                    "trim_db": getattr(self.chain, 'input_trim_db', 0.0),
                },
                "device": {
                    "mode": getattr(self.chain, 'device_mode', 'generic'),
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
                "parallel": {
                    "enabled": getattr(self.chain, 'parallel_enabled', False),
                    "blend": getattr(self.chain, 'parallel_blend', 0.3),
                },
                "cab": {
                    "enabled": self.chain.cab.enabled,
                    "ir_name": self.chain.cab.ir_name,
                    "level": getattr(self.chain.cab, 'level', 1.0),
                    "lowcut": getattr(self.chain.cab, 'lowcut_hz', 20.0),
                    "highcut": getattr(self.chain.cab, 'highcut_hz', 20000.0),
                    "mix": getattr(self.chain.cab, 'mix', 1.0),
                    "tube": getattr(self.chain.cab, 'tube', 'OFF'),
                    "mic": getattr(self.chain.cab, 'mic', 'SM57'),
                    "center": getattr(self.chain.cab, 'center', 50.0),
                    "distance": getattr(self.chain.cab, 'distance', 20.0),
                },
                "eq": {
                    "enabled": getattr(getattr(self.chain, 'eq', None), 'enabled', False),
                    "model_id": getattr(getattr(self.chain, 'eq', None), 'model_id', 1),
                    "bands": getattr(getattr(self.chain, 'eq', None), 'gains', [0.0] * 6),
                    "curve": getattr(self.chain, 'eq', None).get_curve_points() if hasattr(getattr(self.chain, 'eq', None), 'get_curve_points') else [],
                },
                "mod": {
                    "enabled": getattr(getattr(self.chain, 'mod', None), 'enabled', False),
                    "model_id": getattr(getattr(self.chain, 'mod', None), 'model_id', 12),
                    "rate": getattr(getattr(self.chain, 'mod', None), 'rate', 0.5),
                    "mix": getattr(getattr(self.chain, 'mod', None), 'mix', 0.5),
                    "tone": getattr(getattr(self.chain, 'mod', None), 'tone', 0.5),
                    "depth": getattr(getattr(self.chain, 'mod', None), 'depth', 0.5),
                },
                "delay": {
                    "enabled": self.chain.delay.enabled,
                    "time": self.chain.delay.time_sec,
                    "feedback": self.chain.delay.feedback,
                    "mix": self.chain.delay.mix,
                    "ducking": getattr(self.chain.delay, 'ducking', False),
                    "duck_depth": getattr(self.chain.delay, 'duck_depth', 0.6),
                },
                "reverb": {
                    "enabled": self.chain.reverb.enabled,
                    "decay": self.chain.reverb.decay,
                    "mix": self.chain.reverb.mix,
                    "tone": getattr(self.chain.reverb, 'tone', 0.5),
                    "type": getattr(self.chain.reverb, 'reverb_type', 'plate'),
                    "ducking": getattr(self.chain.reverb, 'ducking', False),
                    "duck_depth": getattr(self.chain.reverb, 'duck_depth', 0.5),
                },
                "pitch": {
                    "enabled": getattr(self.chain.pitch_shifter, 'enabled', False),
                    "semitones": getattr(self.chain.pitch_shifter, 'semitones', 0.0),
                    "target_semitones": getattr(self.chain.pitch_shifter, 'target_semitones', 0.0),
                    "cents": getattr(self.chain.pitch_shifter, 'cents', 0.0),
                    "mix": getattr(self.chain.pitch_shifter, 'mix', 1.0),
                    "glide": getattr(self.chain.pitch_shifter, 'glide_pct', 0.0),
                }
            },
            "chain_order": self.chain.get_stage_order() if hasattr(self.chain, 'get_stage_order') else None,
        }
