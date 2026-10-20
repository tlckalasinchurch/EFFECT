"""
TONE3000 API client for กดจนหลอนTone.

Implements the OAuth 2.0 Authorization Code + PKCE flow documented at
https://www.tone3000.com/api :

    select_tone  - the user signs in on TONE3000, browses the catalogue and
                   picks a tone; the callback carries `tone_id`.
    load_tone    - the app already knows the tone id; TONE3000 verifies access
                   (and lets the user pick a replacement when it is gone).

Only the standard library is used (urllib), so no extra pip install is needed.
Tokens are refreshed automatically and persisted in `t3k_tokens.json`; the
publishable key lives in `t3k_config.json` (both git-ignored).

Nothing in here touches the audio engine. server.py downloads the model and
hands the bytes to engine.nam, which keeps this module testable on its own.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import config

logger = logging.getLogger(__name__)

API_BASE = "https://www.tone3000.com/api/v1"
SITE_BASE = "https://www.tone3000.com"

CONFIG_PATH = Path(getattr(config, "T3K_CONFIG_PATH", config.PROJECT_ROOT / "t3k_config.json"))
TOKEN_PATH = Path(getattr(config, "T3K_TOKEN_PATH", config.PROJECT_ROOT / "t3k_tokens.json"))

DEFAULT_REDIRECT_URI = f"http://127.0.0.1:{config.WEB_PORT}/api/t3k/callback"
DEFAULT_ARCHITECTURE = "2"          # A2 first: engine.nam understands SlimmableContainer
ARCHITECTURES = ("1", "2", "custom")  # values accepted by the API
MODEL_SIZE_ORDER = ("standard", "lite", "feather", "nano", "custom")
PENDING_TTL_SECONDS = 15 * 60
HTTP_TIMEOUT = 30


class T3KError(Exception):
    """An error worth showing to the user (bad key, access denied, ...)."""

    def __init__(self, message: str, status: int = 502, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


# ---------------------------------------------------------------------------
# Small JSON file store
# ---------------------------------------------------------------------------

_STORE_LOCK = threading.RLock()


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("Cannot read %s: %s", path.name, exc)
        return {}


def _write_json(path: Path, data: dict) -> None:
    """Atomic replace so a crash mid-write cannot corrupt tokens or config."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)
    try:                      # tokens are credentials: keep them owner-only
        os.chmod(path, 0o600)
    except OSError:
        pass                  # Windows may not support it; not fatal


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _http(method: str, url: str, *, headers: dict | None = None,
          form: dict | None = None, timeout: int = HTTP_TIMEOUT) -> tuple[int, bytes, dict]:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if form is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for key, value in (headers or {}).items():
        req.add_header(key, value)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        detail, code = _error_detail(body)
        if exc.code == 401:
            raise T3KError("TONE3000: ต้องเข้าสู่ระบบใหม่ (token หมดอายุ)", 401, code) from exc
        raise T3KError(detail or f"TONE3000 ตอบกลับ HTTP {exc.code}", exc.code, code) from exc
    except urllib.error.URLError as exc:
        raise T3KError(f"เชื่อมต่อ TONE3000 ไม่ได้: {exc.reason}", 502) from exc


def _error_detail(body: bytes) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    detail = payload.get("error_description") or payload.get("message") or payload.get("detail")
    code = payload.get("error") or payload.get("code")
    if isinstance(detail, list):          # FastAPI-style validation errors
        detail = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)
    return (str(detail) if detail else None), (str(code) if code else None)


def _json_request(method: str, path: str, *, params: dict | None = None,
                  token: str | None = None, form: dict | None = None) -> dict:
    url = API_BASE + path
    if params:
        clean = {k: v for k, v in params.items() if v not in (None, "", False)}
        if clean:
            url += "?" + urllib.parse.urlencode(clean, doseq=True)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    _status, body, _hdrs = _http(method, url, headers=headers, form=form)
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise T3KError("TONE3000 ส่งข้อมูลที่ไม่ใช่ JSON กลับมา", 502) from exc


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with _STORE_LOCK:
        cfg = _read_json(CONFIG_PATH)
    cfg.setdefault("client_id", os.getenv("T3K_CLIENT_ID", "").strip())
    cfg.setdefault("redirect_uri", os.getenv("T3K_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip())
    cfg.setdefault("architecture", DEFAULT_ARCHITECTURE)
    if cfg["architecture"] not in ARCHITECTURES:
        cfg["architecture"] = DEFAULT_ARCHITECTURE
    return cfg


def save_config(client_id: str | None = None, redirect_uri: str | None = None,
                architecture: str | None = None) -> dict:
    cfg = load_config()
    if client_id is not None:
        client_id = client_id.strip()
        if client_id and not (client_id.startswith(("t3k_pub_", "t3k_pk_")) or len(client_id) >= 16):
            raise T3KError("Publishable key ไม่ถูกต้อง (ควรขึ้นต้นด้วย t3k_pub_)", 400)
        cfg["client_id"] = client_id
    if redirect_uri is not None:
        redirect_uri = redirect_uri.strip() or DEFAULT_REDIRECT_URI
        if not redirect_uri.startswith(("http://", "https://")):
            raise T3KError("Redirect URI ต้องเป็น http:// หรือ https://", 400)
        cfg["redirect_uri"] = redirect_uri
    if architecture is not None:
        architecture = str(architecture)
        if architecture not in ARCHITECTURES:
            raise T3KError("architecture ต้องเป็น 1, 2 หรือ custom", 400)
        cfg["architecture"] = architecture
    with _STORE_LOCK:
        _write_json(CONFIG_PATH, cfg)
    return cfg


def _mask(key: str) -> str:
    if not key:
        return ""
    return key if len(key) <= 12 else f"{key[:8]}…{key[-4:]}"


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def load_tokens() -> dict:
    with _STORE_LOCK:
        return _read_json(TOKEN_PATH)


def clear_tokens() -> None:
    with _STORE_LOCK:
        try:
            TOKEN_PATH.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Cannot delete token file: %s", exc)


def _store_token_response(payload: dict) -> dict:
    cfg = load_config()
    previous = load_tokens()
    now = time.time()
    tokens = {
        "access_token": payload.get("access_token", ""),
        "refresh_token": payload.get("refresh_token", ""),
        "token_type": payload.get("token_type", "bearer"),
        "scope": payload.get("scope", ""),
        "expires_at": now + float(payload.get("expires_in") or 3600) - 30,
        "client_id": cfg["client_id"],
    }
    if not tokens["access_token"]:
        raise T3KError("TONE3000 ไม่ได้ส่ง access token กลับมา", 502)
    if previous.get("user"):          # keep the cached profile across refreshes
        tokens["user"] = previous["user"]
    with _STORE_LOCK:
        _write_json(TOKEN_PATH, tokens)
    return tokens


def _store_user(user: dict | None) -> None:
    if not isinstance(user, dict) or not user:
        return
    with _STORE_LOCK:
        tokens = _read_json(TOKEN_PATH)
        if not tokens.get("access_token"):
            return
        tokens["user"] = user
        _write_json(TOKEN_PATH, tokens)


def _refresh_tokens(tokens: dict) -> dict:
    cfg = load_config()
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise T3KError("ไม่มี refresh token — ต้องเข้าสู่ระบบ TONE3000 ใหม่", 401)
    payload = _json_request("POST", "/oauth/token", form={
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": cfg["client_id"],
    })
    new = _store_token_response(payload)
    if not new.get("refresh_token"):
        new["refresh_token"] = refresh
        with _STORE_LOCK:
            _write_json(TOKEN_PATH, new)
    logger.info("TONE3000 access token refreshed")
    return new


def _access_token(force_refresh: bool = False) -> str:
    tokens = load_tokens()
    if not tokens.get("access_token"):
        raise T3KError("ยังไม่ได้เชื่อมต่อ TONE3000", 401, "not_authenticated")
    if force_refresh or float(tokens.get("expires_at") or 0) <= time.time():
        tokens = _refresh_tokens(tokens)
    return tokens["access_token"]


def api_get(path: str, params: dict | None = None) -> dict:
    """Authenticated GET with one automatic refresh on a 401."""
    try:
        return _json_request("GET", path, params=params, token=_access_token())
    except T3KError as exc:
        if exc.status != 401:
            raise
        return _json_request("GET", path, params=params, token=_access_token(force_refresh=True))


# ---------------------------------------------------------------------------
# OAuth: authorization, callback, token exchange
# ---------------------------------------------------------------------------

_PENDING: dict[str, dict] = {}


def _prune_pending() -> None:
    cutoff = time.time() - PENDING_TTL_SECONDS
    for state in [s for s, p in _PENDING.items() if p["created"] < cutoff]:
        _PENDING.pop(state, None)


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorize_url(prompt: str = "select_tone", *, tone_id: int | str | None = None,
                        gears: str | None = None, model_format: str = "nam",
                        architecture: str | None = None,
                        menubar: bool = True, preview: bool = True) -> dict:
    """
    Build the TONE3000 authorize URL and remember the PKCE verifier + state.

    `prompt`: "select_tone" (browse and pick) or "load_tone" (tone_id known).
    Returns {"authorize_url", "state", "redirect_uri", "expires_in"}.
    """
    cfg = load_config()
    if not cfg["client_id"]:
        raise T3KError("ยังไม่มี Publishable key — ใส่ key ในหน้า TONE3000 ก่อน", 400, "no_client_id")
    if prompt not in ("select_tone", "load_tone"):
        raise T3KError("prompt ต้องเป็น select_tone หรือ load_tone", 400)
    if prompt == "load_tone" and not tone_id:
        raise T3KError("load_tone ต้องมี tone_id", 400)

    _prune_pending()
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    _PENDING[state] = {
        "verifier": verifier,
        "redirect_uri": cfg["redirect_uri"],
        "prompt": prompt,
        "tone_id": str(tone_id) if tone_id else None,
        "created": time.time(),
    }

    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "prompt": prompt,
        "format": model_format,
        "architecture": architecture or cfg["architecture"],
        "locale": "en",
    }
    if gears:
        params["gears"] = gears
    if tone_id:
        params["tone_id"] = str(tone_id)
    if menubar:
        params["menubar"] = "true"
    if preview and prompt == "select_tone":
        params["preview"] = "true"

    return {
        "authorize_url": f"{SITE_BASE}/api/v1/oauth/authorize?{urllib.parse.urlencode(params)}",
        "state": state,
        "redirect_uri": cfg["redirect_uri"],
        "expires_in": PENDING_TTL_SECONDS,
    }


def exchange_code(code: str, verifier: str, redirect_uri: str) -> dict:
    cfg = load_config()
    payload = _json_request("POST", "/oauth/token", form={
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "client_id": cfg["client_id"],
    })
    tokens = _store_token_response(payload)
    logger.info("TONE3000 authorization complete")
    return tokens


def handle_callback(query: dict) -> dict:
    """
    Validate the redirect and exchange the code.

    `query` is the raw callback query string as a dict (single values).
    Returns {"tone_id", "canceled", "user"}; raises T3KError on failure.
    """
    error = query.get("error")
    if error:
        raise T3KError(query.get("error_description") or f"TONE3000 ปฏิเสธ: {error}", 400, error)

    state = query.get("state") or ""
    pending = _PENDING.pop(state, None) if state else None
    if not pending:
        raise T3KError("state ไม่ตรงหรือหมดอายุ — เริ่มเชื่อมต่อใหม่", 400, "invalid_state")
    if pending["created"] < time.time() - PENDING_TTL_SECONDS:
        raise T3KError("คำขอเชื่อมต่อหมดอายุ — เริ่มใหม่", 400, "expired_state")

    canceled = str(query.get("canceled", "")).lower() == "true"
    code = query.get("code")
    if not code:
        # The menubar's close button before sign-in redirects with canceled=true
        # and no code — that is a normal cancel, not an error.
        if canceled:
            return {"tone_id": None, "canceled": True, "user": None}
        raise T3KError("TONE3000 ไม่ได้ส่ง authorization code กลับมา", 400, "missing_code")

    exchange_code(code, pending["verifier"], pending["redirect_uri"])

    tone_id = query.get("tone_id")
    user = None
    try:
        user = get_user()
        _store_user(user)
    except T3KError as exc:      # tokens are valid; profile is a nicety
        logger.warning("TONE3000 user lookup failed: %s", exc)
    return {"tone_id": int(tone_id) if tone_id and str(tone_id).isdigit() else None,
            "canceled": canceled, "user": user}


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

def get_user() -> dict:
    return api_get("/user")


def status() -> dict:
    cfg = load_config()
    tokens = load_tokens()
    logged_in = bool(tokens.get("access_token"))
    if logged_in and float(tokens.get("expires_at") or 0) <= time.time() and tokens.get("refresh_token"):
        try:
            _refresh_tokens(tokens)
            tokens = load_tokens()
        except T3KError as exc:
            logger.warning("TONE3000 refresh failed: %s", exc)
            logged_in = False
    if logged_in and not tokens.get("user"):
        try:                      # cache the profile once, then stay offline
            _store_user(get_user())
            tokens = load_tokens()
        except T3KError as exc:
            logger.info("TONE3000 profile not available yet: %s", exc)

    return {
        "configured": bool(cfg["client_id"]),
        "client_id": _mask(cfg["client_id"]),
        "redirect_uri": cfg["redirect_uri"],
        "architecture": cfg["architecture"],
        "logged_in": logged_in,
        "user": tokens.get("user"),
        "expires_at": tokens.get("expires_at"),
    }


def search_tones(query: str = "", page: int = 1, *, gear: str | None = None,
                 sort: str | None = None, verified: bool = False) -> dict:
    """GET /tones/search (page size is capped at 25 by the API)."""
    cfg = load_config()
    data = api_get("/tones/search", {
        "query": query,
        "page": max(1, int(page)),
        "page_size": 25,
        "sort": sort,
        "gears": gear,
        "format": "nam",
        "architecture": cfg["architecture"],
        "verified": "true" if verified else None,
    })
    return _normalise_page(data)


def list_tones(kind: str = "trending", page: int = 1, *, gear: str | None = None,
               query: str = "") -> dict:
    """Bounded lists: favourited / created / downloaded / trending / latest."""
    if kind not in ("favorited", "created", "downloaded", "trending", "latest"):
        raise T3KError("kind ต้องเป็น favorited, created, downloaded, trending หรือ latest", 400)
    if kind in ("trending", "latest"):
        data = api_get(f"/tones/{kind}", {"gear": gear})
        tones = data.get("data") or []
        return {"data": tones, "page": 1, "page_size": len(tones),
                "total": len(tones), "total_pages": 1}
    data = api_get(f"/tones/{kind}", {
        "page": max(1, int(page)),
        "page_size": 50,
        "gear": gear,
        "query": query or None,
    })
    return _normalise_page(data)


def _normalise_page(data: dict) -> dict:
    tones = data.get("data")
    if not isinstance(tones, list):
        tones = []
    return {
        "data": tones,
        "page": int(data.get("page") or 1),
        "page_size": int(data.get("page_size") or len(tones)),
        "total": int(data.get("total") or len(tones)),
        "total_pages": int(data.get("total_pages") or 1),
    }


def get_tone(tone_id: int | str, architecture: str | None = None) -> dict:
    cfg = load_config()
    return api_get(f"/tones/{int(tone_id)}",
                   {"architecture": architecture or cfg["architecture"]})


def list_models(tone_id: int | str, architecture: str | None = None) -> list[dict]:
    cfg = load_config()
    data = api_get("/models", {
        "tone_id": int(tone_id),
        "page_size": 300,
        "architecture": architecture or cfg["architecture"],
    })
    models = data.get("data")
    return models if isinstance(models, list) else []


def _model_rank(model: dict) -> tuple:
    size = str(model.get("size") or "standard")
    rank = MODEL_SIZE_ORDER.index(size) if size in MODEL_SIZE_ORDER else len(MODEL_SIZE_ORDER)
    return (rank, 0 if model.get("architecture_version") == "1" else 1)


def pick_model(models: list[dict], model_id: int | str | None = None) -> dict | None:
    """Explicit id wins; otherwise the biggest non-custom A1/A2 model."""
    if model_id:
        wanted = str(model_id)
        for m in models:
            if str(m.get("id")) == wanted:
                return m
        raise T3KError(f"ไม่พบ model id {model_id} ใน tone นี้", 404)
    if not models:
        return None
    return sorted(models, key=_model_rank)[0]


def download_model(model: dict) -> tuple[bytes, str]:
    """Download one model file with the access token. Returns (bytes, filename)."""
    url = model.get("model_url") or ""
    if not url:
        raise T3KError("model นี้ไม่มี model_url", 502)
    url = urllib.parse.urljoin(SITE_BASE, url)
    token = _access_token()
    _status, body, headers = _http("GET", url, headers={"Authorization": f"Bearer {token}"})
    if not body:
        raise T3KError("TONE3000 ส่งไฟล์ว่างกลับมา", 502)

    name = ""
    disposition = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
    if "filename=" in disposition:
        name = disposition.split("filename=", 1)[1].strip().strip('";')
    if not name:
        name = os.path.basename(urllib.parse.urlparse(url).path) or ""
    if not os.path.splitext(name)[1]:
        # URLs like /models/7/download carry no filename: use the model name.
        base = re.sub(r"[^A-Za-z0-9._ -]+", "_", str(model.get("name") or "")).strip()
        if not name or name.lower() in ("download", "file", "model", "get"):
            name = base or f"model_{model.get('id')}"
        name += ".nam"
    return body, name


def fetch_package(tone_id: int | str, model_id: int | str | None = None,
                  architecture: str | None = None) -> dict:
    """
    Everything needed to install a tone: tone row, model list, chosen model,
    and the downloaded file bytes.
    """
    tone = get_tone(tone_id, architecture)
    models = list_models(tone_id, architecture)
    chosen = pick_model(models, model_id)
    if chosen is None:
        raise T3KError("tone นี้ยังไม่มีไฟล์ model ให้ดาวน์โหลด", 404, "no_models")
    raw, filename = download_model(chosen)
    return {
        "tone": tone,
        "models": models,
        "model": chosen,
        "bytes": raw,
        "filename": filename,
        "architecture": architecture or load_config()["architecture"],
        "was_fallback": False,
    }
