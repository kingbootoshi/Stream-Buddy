"""
Generate a Twitch User Access Token (Authorization Code flow) for chat scopes.

This script opens a browser for consent, captures the authorization code via a
local HTTP callback, exchanges it for tokens, validates the token to obtain
user info, and saves everything to `backend/.twitch_user_token.json`.

Design goals:
- No new environment variables beyond existing TWITCH_CLIENT_ID/SECRET
- Default scopes: chat:read and chat:edit (write ability is `chat:edit`)
- Clear logging and a single JSON output file for easy consumption

Usage:
  python backend/generate_user_token.py

Notes:
- User tokens (with `chat:edit`) are required to send chat messages.
- If you only need Helix app-level calls, use app tokens instead.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

try:
    from dotenv import load_dotenv

    # Load both root .env and backend/.env if present. Later calls won't
    # override already-set variables, so order is safe.
    load_dotenv(".env")
    load_dotenv("backend/.env")
except Exception:
    # It's okay if python-dotenv is not installed; env vars can come from shell
    pass

from loguru import logger


# Fixed redirect used for the local callback server. Ensure this URI is
# registered in your Twitch Dev Console for the application.
DEFAULT_REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI", "http://localhost:4343/oauth/callback").strip()


def _build_auth_url(client_id: str, redirect_uri: str, scopes: List[str], state: str) -> str:
    """Construct the Twitch OAuth authorize URL for Authorization Code flow."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "force_verify": "true",
    }
    return f"https://id.twitch.tv/oauth2/authorize?{urlencode(params)}"


def _exchange_code_for_tokens(client_id: str, client_secret: str, code: str, redirect_uri: str) -> Dict:
    """Exchange authorization code for user access/refresh tokens."""
    url = "https://id.twitch.tv/oauth2/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    with httpx.Client(timeout=15.0) as client:
        r = client.post(url, data=data)
        try:
            r.raise_for_status()
        except Exception as exc:
            logger.error(f"Token exchange failed: {exc}; body={r.text}")
            raise
        return r.json()


def _validate_user_token(access_token: str) -> Dict:
    """Validate the user token to retrieve owner info and scopes."""
    url = "https://id.twitch.tv/oauth2/validate"
    headers = {"Authorization": f"OAuth {access_token}"}
    with httpx.Client(timeout=10.0) as client:
        r = client.get(url, headers=headers)
        try:
            r.raise_for_status()
        except Exception as exc:
            logger.error(f"Token validate failed: {exc}; body={r.text}")
            raise
        return r.json()


def run_local_user_oauth(scopes: List[str]) -> Dict:
    """Perform local OAuth to obtain user tokens with the requested scopes."""
    client_id = os.getenv("TWITCH_CLIENT_ID", "").strip()
    client_secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
    redirect_uri = DEFAULT_REDIRECT_URI

    if not client_id or not client_secret:
        raise RuntimeError("Missing TWITCH_CLIENT_ID and/or TWITCH_CLIENT_SECRET.")

    state = secrets.token_urlsafe(24)
    code_holder: Dict[str, str] = {}
    done_event = threading.Event()

    class OAuthHandler(BaseHTTPRequestHandler):
        """Minimal handler to capture ?code and ?state from Twitch callback."""

        def log_message(self, fmt: str, *args) -> None:  # pragma: no cover
            return

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path != urlparse(redirect_uri).path:
                    self.send_response(404)
                    self.end_headers()
                    return
                qs = parse_qs(parsed.query)
                code = (qs.get("code") or [""])[0]
                got_state = (qs.get("state") or [""])[0]
                if not code or got_state != state:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Invalid OAuth response. Check logs.")
                    return
                code_holder["code"] = code
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Twitch authorization received. You can close this tab.")
            finally:
                done_event.set()

    # Start local server
    url_parts = urlparse(redirect_uri)
    host = url_parts.hostname or "localhost"
    port = url_parts.port or 4343
    server = HTTPServer((host, port), OAuthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Started local OAuth callback server at {redirect_uri}")

    # Open browser
    import webbrowser

    auth_url = _build_auth_url(client_id, redirect_uri, scopes, state)
    logger.info("Opening Twitch consent in browser...")
    try:
        webbrowser.open(auth_url, new=2)
    except Exception:
        logger.info(f"Open this URL in your browser to authorize: {auth_url}")

    # Wait for callback
    if not done_event.wait(timeout=300):
        server.shutdown()
        raise TimeoutError("Timed out waiting for Twitch OAuth callback (5 minutes)")

    server.shutdown()

    code = code_holder.get("code", "")
    if not code:
        raise RuntimeError("No authorization code captured from Twitch callback.")

    tokens = _exchange_code_for_tokens(client_id, client_secret, code, redirect_uri)
    return tokens


def main() -> None:
    """Entrypoint: obtain user token with chat scopes and save to JSON."""
    # Map requested default scopes. `chat:edit` requested maps to Twitch's
    # actual scope name `chat:edit` for sending messages.
    scopes = ["chat:read", "chat:edit", "user:read:chat", "user:bot", "user:write:chat"]

    logger.info(f"Running local OAuth for scopes: {scopes}")
    tokens = run_local_user_oauth(scopes)

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")
    scope_from_exchange = tokens.get("scope")

    # Validate token to enrich with owner info
    try:
        token_info = _validate_user_token(access_token)
        user_id = token_info.get("user_id", "")
        login = token_info.get("login", "")
        token_scopes = token_info.get("scopes", [])
    except Exception as e:
        logger.warning(f"Could not validate token: {e}")
        user_id = ""
        login = ""
        token_scopes = []

    now = time.time()
    out = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "scope": scope_from_exchange,
        "user_id": user_id,
        "login": login,
        "scopes_validated": token_scopes,
        "timestamp": now,
        "expires_at": (now + int(expires_in)) if expires_in else None,
    }

    out_path = os.path.join("backend",".twitch_user_token.json")
    # Ensure target directory exists to avoid FileNotFoundError on first run
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    logger.success(f"User token saved to {out_path}")
    print(json.dumps({
        "saved": out_path,
        "login": login,
        "user_id": user_id,
        "expires_in": expires_in,
        "scopes": token_scopes,
    }, indent=2))


if __name__ == "__main__":
    main()
