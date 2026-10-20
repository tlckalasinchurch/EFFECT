#!/usr/bin/env python3
"""TONE3000 amplifier CLI for EFFECT.

The EFFECT backend owns OAuth tokens, downloads NAM models, caches model bytes,
and writes the selected tone into presets.db. This CLI intentionally calls the
local EFFECT API instead of handling tokens or card/secret data itself.

Examples:
    python tools/tone3000_amp.py configure --client-id ...
    python tools/tone3000_amp.py connect --gears amp
    python tools/tone3000_amp.py search "5150" --gear amp
    python tools/tone3000_amp.py models 12345
    python tools/tone3000_amp.py load 12345 --model-id 678 --quality lite
    python tools/tone3000_amp.py status
    python tools/tone3000_amp.py presets
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = os.environ.get("EFFECT_URL", "http://127.0.0.1:8000").rstrip("/")


def request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = None
    headers = {"Accept": "application/json"}
    url = base_url + path
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw).get("detail", raw)
        except json.JSONDecodeError:
            detail = raw
        raise RuntimeError(f"EFFECT API {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            f"เชื่อมต่อ EFFECT backend ไม่ได้ที่ {base_url} — "
            "ให้เริ่มแอป/เซิร์ฟเวอร์ก่อน เช่น python server.py"
        ) from exc


def print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def do_configure(args: argparse.Namespace) -> None:
    payload = {
        "client_id": args.client_id,
        "redirect_uri": args.redirect_uri,
        "architecture": args.architecture,
    }
    print_json(request_json(args.base_url, "/api/t3k/config", "POST", payload))


def do_connect(args: argparse.Namespace) -> None:
    payload = {"prompt": args.prompt, "gears": args.gears}
    if args.tone_id is not None:
        payload["tone_id"] = args.tone_id
    result = request_json(args.base_url, "/api/t3k/connect", "POST", payload)
    print_json(result)
    if result.get("authorize_url"):
        print("\nเปิด authorize_url ใน browser เพื่ออนุมัติ TONE3000 OAuth")


def do_search(args: argparse.Namespace) -> None:
    params = {"query": args.query, "gear": args.gear, "page": args.page, "verified": str(args.verified).lower()}
    path = "/api/t3k/tones?" + urlencode({k: v for k, v in params.items() if v not in (None, "")})
    result = request_json(args.base_url, path)
    tones = result.get("data") or []
    print(f"พบ {len(tones)} tones")
    for tone in tones:
        print(f"{tone.get('id')}\t{tone.get('title', 'Untitled')}\t{tone.get('gear', '')}")
    if args.json:
        print_json(result)


def do_models(args: argparse.Namespace) -> None:
    result = request_json(args.base_url, f"/api/t3k/tones/{args.tone_id}")
    print_json(result)


def do_load(args: argparse.Namespace) -> None:
    payload = {"tone_id": args.tone_id, "model_id": args.model_id, "quality": args.quality}
    result = request_json(args.base_url, "/api/t3k/load", "POST", payload)
    info = result.get("load") or {}
    print("TONE3000 amplifier loaded")
    print(f"  tone:       {info.get('title', args.tone_id)}")
    print(f"  model:      {info.get('model')} (id={info.get('model_id')})")
    print(f"  architecture: A{info.get('architecture')} / {info.get('quality')}")
    print(f"  cache file:  {info.get('cache_file')}")
    print(f"  preset saved: {info.get('preset_saved')}")
    print("  persistence: model cache + presets.db")
    if args.json:
        print_json(result)


def do_status(args: argparse.Namespace) -> None:
    print_json(request_json(args.base_url, "/api/t3k/status"))


def do_presets(args: argparse.Namespace) -> None:
    result = request_json(args.base_url, "/api/presets")
    presets = result.get("presets") or []
    for preset in presets:
        marker = "TONE3000" if "_t3k" in (preset.get("settings") or {}) else "DSP"
        print(f"{preset.get('id')}\t[{marker}]\t{preset.get('name')}")
    if args.json:
        print_json(result)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", dest="base_url", default=DEFAULT_BASE_URL, help="EFFECT backend URL")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("configure", help="save TONE3000 client configuration")
    c.add_argument("--client-id", required=True)
    c.add_argument("--redirect-uri")
    c.add_argument("--architecture", choices=("1", "2"), default="2")
    c.set_defaults(func=do_configure)

    c = sub.add_parser("connect", help="create OAuth authorize URL")
    c.add_argument("--prompt", default="select_tone")
    c.add_argument("--tone-id", type=int)
    c.add_argument("--gears", default="amp")
    c.set_defaults(func=do_connect)

    c = sub.add_parser("search", help="search TONE3000 tones")
    c.add_argument("query", nargs="?", default="")
    c.add_argument("--gear", default="amp")
    c.add_argument("--page", type=int, default=1)
    c.add_argument("--verified", action="store_true")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=do_search)

    c = sub.add_parser("models", help="list models for a tone")
    c.add_argument("tone_id", type=int)
    c.set_defaults(func=do_models)

    c = sub.add_parser("load", help="download, install and persist an amp")
    c.add_argument("tone_id", type=int)
    c.add_argument("--model-id", type=int)
    c.add_argument("--quality", choices=("lite", "full"), default="lite")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=do_load)

    c = sub.add_parser("status", help="show TONE3000 auth and loaded model status")
    c.set_defaults(func=do_status)

    c = sub.add_parser("presets", help="list persisted presets")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=do_presets)
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
