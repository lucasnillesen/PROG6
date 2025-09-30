"""
Authentication helpers for the bol.com Retailer API.

This module looks for bol.com API credentials either in the environment
variables ``CLIENT_ID`` and ``CLIENT_SECRET`` or in a JSON file
``bol_credentials.json`` located in the project root.  It exposes
``get_access_token`` which exchanges the client credentials for an
access token that can be used with the Retailer API.

"""

from __future__ import annotations

import os
import json
import requests
from pathlib import Path

def _creds_from_env() -> tuple[str | None, str | None]:
    cid = os.getenv("CLIENT_ID")
    csec = os.getenv("CLIENT_SECRET")
    if cid and csec:
        return cid, csec
    return None, None

def _creds_from_file() -> tuple[str | None, str | None]:
    cfg_path = Path(__file__).resolve().parent.parent / "bol_credentials.json"
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            return data.get("client_id"), data.get("client_secret")
        except Exception:
            pass
    return None, None

def _get_credentials() -> tuple[str, str]:
    cid, csec = _creds_from_env()
    if not cid or not csec:
        cid, csec = _creds_from_file()
    if not cid or not csec:
        raise RuntimeError(
            "Bol.com API credentials ontbreken. Zet CLIENT_ID/CLIENT_SECRET als env vars "
            "of maak bol_credentials.json met {\"client_id\": \"...\", \"client_secret\": \"...\"} in de project root."
        )
    return cid, csec

def get_access_token(timeout: int = 20) -> str:
    client_id, client_secret = _get_credentials()
    url = "https://login.bol.com/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    resp = requests.post(url, headers=headers, data=data, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["access_token"]
