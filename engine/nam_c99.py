"""
C99 Native NAM Engine Bridge using nam_c99.dll.
Freestanding zero-allocation WaveNet execution for A2-Lite and A2-Full models.
Achieves deterministic sub-millisecond execution (0 audio deadline misses @ 128 samples).
"""
import os
import ctypes
import numpy as np

DLL_PATH = os.path.join(os.path.dirname(__file__), "nam_c99.dll")

class C99NamEngine:
    _dll = None

    @classmethod
    def is_available(cls) -> bool:
        return cls.get_dll() is not None

    @classmethod
    def get_dll(cls):
        if cls._dll is None and os.path.exists(DLL_PATH):
            try:
                dll = ctypes.CDLL(DLL_PATH)
                dll.nam_dll_load.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.c_int,
                    ctypes.POINTER(ctypes.c_char_p)
                ]
                dll.nam_dll_load.restype = ctypes.c_int
                dll.nam_dll_reset.argtypes = []
                dll.nam_dll_reset.restype = None
                dll.nam_dll_process.argtypes = [
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.c_int
                ]
                dll.nam_dll_process.restype = None
                dll.nam_dll_model.argtypes = []
                dll.nam_dll_model.restype = ctypes.c_int
                dll.nam_dll_model_name.argtypes = []
                dll.nam_dll_model_name.restype = ctypes.c_char_p
                cls._dll = dll
            except Exception as e:
                cls._dll = None
        return cls._dll

    def __init__(self, namb_bytes: bytes):
        dll = self.get_dll()
        if not dll:
            raise RuntimeError("nam_c99.dll is not available")
        self._dll = dll
        self.namb_bytes = bytes(namb_bytes)
        err_ptr = ctypes.c_char_p()
        rc = dll.nam_dll_load(self.namb_bytes, len(self.namb_bytes), 1, ctypes.byref(err_ptr))
        if rc != 0:
            err_msg = err_ptr.value.decode("utf-8") if err_ptr.value else "unknown load error"
            raise ValueError(f"C99 NAM load error: {err_msg}")
        self.model_id = dll.nam_dll_model()
        self.model_name = dll.nam_dll_model_name().decode("utf-8")

    @classmethod
    def from_weights(cls, weights, sample_rate=48000.0, loudness=-18.0):
        w_arr = np.ascontiguousarray(weights, dtype=np.float32)
        count = len(w_arr)
        if count == 1871:
            template_path = os.path.join(os.path.dirname(__file__), "a2lite_template.bin")
        elif count == 12146:
            template_path = os.path.join(os.path.dirname(__file__), "a2full_template.bin")
        else:
            raise ValueError(f"Unsupported weight count {count} for C99 A2 engine")
            
        with open(template_path, "rb") as f:
            hdr = bytearray(f.read())
            
        w_bytes = w_arr.tobytes()
        tot_size = len(hdr) + len(w_bytes)
        import struct, zlib
        struct.pack_into("<I", hdr, 8, tot_size)
        struct.pack_into("<I", hdr, 12, len(hdr))
        struct.pack_into("<I", hdr, 16, count)
        struct.pack_into("<d", hdr, 36, float(sample_rate))
        struct.pack_into("<d", hdr, 44, float(loudness))
        struct.pack_into("<I", hdr, 24, 0)
        body = hdr + w_bytes
        crc = zlib.crc32(body[:24] + body[28:])
        struct.pack_into("<I", body, 24, crc)
        return cls(body)

    def reset(self):
        self._dll.nam_dll_reset()

    def process(self, x: np.ndarray) -> np.ndarray:
        x_f32 = np.ascontiguousarray(x, dtype=np.float32)
        n = len(x_f32)
        if n == 0:
            return np.empty(0, dtype=np.float32)
        if n <= 512:
            out = np.empty(n, dtype=np.float32)
            in_ptr = x_f32.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            out_ptr = out.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self._dll.nam_dll_process(in_ptr, out_ptr, n)
            return out
        out = np.empty(n, dtype=np.float32)
        for i in range(0, n, 512):
            cn = min(512, n - i)
            chunk = np.ascontiguousarray(x_f32[i:i + cn])
            in_ptr = chunk.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            out_chunk = np.empty(cn, dtype=np.float32)
            out_ptr = out_chunk.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            self._dll.nam_dll_process(in_ptr, out_ptr, cn)
            out[i:i + cn] = out_chunk
        return out


