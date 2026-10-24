"""Minimal Kemper SysEx framing based on the local rigpack parser."""

KEMPER_MANUFACTURER = b"\x00\x20\x33"


def parse_kemper_sysex(data: bytes) -> tuple[bytes, int, bytes]:
    """Validate one complete Kemper message and return (address, subcommand, value)."""
    data = bytes(data)
    if len(data) < 10 or data[0] != 0xF0 or data[-1] != 0xF7:
        raise ValueError("Expected one complete F0...F7 SysEx message")
    if data[1] & 0x80:
        if len(data) < 3:
            raise ValueError("Truncated extended SysEx length")
        header = 3
        declared = ((data[1] & 0x7F) << 7) | data[2]
        if data[2] & 0x80:
            raise ValueError("Invalid extended SysEx length")
    else:
        header = 2
        declared = data[1]
    if len(data) != header + declared or declared < 8:
        raise ValueError("SysEx length does not match frame")
    if data[header:header + 3] != KEMPER_MANUFACTURER:
        raise ValueError("SysEx manufacturer is not Kemper")
    body = data[header + 3:-1]
    if len(body) < 4 or any(byte > 0x7F for byte in data[header + 3:-1]):
        raise ValueError("Invalid Kemper address/subcommand or non-7-bit value")
    return body[:3], body[3], body[4:]


def frame_kemper_sysex(address: bytes, subcommand: int, value: bytes) -> bytes:
    """Encode framing only; semantic command identifiers are not inferred."""
    address, value = bytes(address), bytes(value)
    if len(address) != 3 or any(byte > 0x7F for byte in address):
        raise ValueError("address must be exactly three 7-bit bytes")
    if not isinstance(subcommand, int) or not 0 <= subcommand <= 0x7F:
        raise ValueError("subcommand must be a 7-bit integer")
    if any(byte > 0x7F for byte in value):
        raise ValueError("value must contain only 7-bit bytes")
    body = KEMPER_MANUFACTURER + address + bytes((subcommand,)) + value
    # Local parser computes end = start + header + length; it therefore uses
    # the encoded byte count (payload + F7) as the length.
    length = len(body) + 1
    if length <= 0x7F:
        prefix = bytes((length,))
    elif length <= 0x3FFF:
        prefix = bytes((0x80 | (length >> 7), length & 0x7F))
    else:
        raise ValueError("SysEx message exceeds 14-bit length")
    return b"\xF0" + prefix + body + b"\xF7"
