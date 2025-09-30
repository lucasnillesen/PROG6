"""
Order retrieval helpers for the bol.com Retailer API.

This module defines a function ``get_orders`` which retrieves the
current list of orders from the bol.com Retailer API using a bearer
token. On success it returns a list of order dictionaries, each
containing ``orderItems`` among other fields.

"""

from __future__ import annotations

import time
import requests

def get_orders(token: str, retries: int = 2, timeout: int = 20) -> list[dict]:
    url = "https://api.bol.com/retailer/orders"
    headers = {
        "Accept": "application/vnd.retailer.v9+json",
        "Authorization": f"Bearer {token}",
    }
    backoff = 2
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", "5"))
                time.sleep(retry_after)
                continue
            r.raise_for_status()
            return r.json().get("orders", [])
        except requests.HTTPError:
            if 500 <= r.status_code < 600 and attempt < retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise
        except requests.RequestException:
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise
