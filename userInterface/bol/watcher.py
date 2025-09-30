"""
Bol.com order watcher for the printer schuif web interface.

This module polls the bol.com Retailer API on a configurable interval
to detect new order items.  When a new order item is found, and a
matching EAN exists in the mapping file, the watcher adds a job to
the printer queue via the global ``queue_manager`` and records the
event via the ``history`` module.  Processed order item IDs are
persisted to disk so that already handled items are not processed
again across restarts.

"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set, Dict

from ..constants import STORAGE_DIR, MAPPING_FILE
from .auth import get_access_token
from .orders import get_orders

PROCESSED_FILE: Path = STORAGE_DIR / "processed_orderitems.json"

def load_processed_ids() -> Set[str]:
    """Read processed orderItemIds from disk and return them as a set."""
    if not PROCESSED_FILE.exists():
        return set()
    try:
        return set(json.loads(PROCESSED_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()

def save_processed_ids(ids: Set[str]) -> None:
    """Persist processed orderItemIds to disk, trimming history to 5000 items."""
    lst = list(ids)
    if len(lst) > 5000:
        lst = lst[-5000:]
    try:
        PROCESSED_FILE.write_text(json.dumps(lst), encoding="utf-8")
    except Exception as e:
        print(f"Kon processed_orderitems.json niet schrijven: {e}")

def load_mapping() -> Dict[str, object]:
    """Load the EAN mapping from the global mapping file."""
    if not MAPPING_FILE.exists():
        return {}
    try:
        return json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

class BolOrderWatcher:
    """Polls the bol.com Retailer API for new orders and enqueues jobs."""

    def __init__(self, printer_serial: str, interval_sec: int = 120, min_bed_temp: float = 35.0) -> None:
        self.printer_serial: str = printer_serial
        self.interval: int = interval_sec
        self.min_bed_temp: float = float(min_bed_temp)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"BolOrderWatcher gestart (interval {self.interval}s) → printer {self.printer_serial}")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        processed: Set[str] = load_processed_ids()
        token: str | None = None
        token_expiry: datetime = datetime.min

        while not self._stop.is_set():
            try:
                now_utc = datetime.utcnow()
                # Renew the access token if expired or about to expire (1 minute buffer)
                if token is None or now_utc > token_expiry - timedelta(seconds=60):
                    token = get_access_token()
                    token_expiry = now_utc + timedelta(minutes=9)  # token is valid ~10 minutes

                orders = get_orders(token)
                mapping = load_mapping()

                from queue_manager import add_to_queue, save_queue  # type: ignore
                from history import append_history  # type: ignore

                new_processed: Set[str] = set(processed)

                for order in orders:
                    for item in order.get("orderItems", []):
                        iid = item.get("orderItemId")
                        if not iid or iid in processed or iid in new_processed:
                            continue

                        ean = item.get("ean")
                        qty = int(item.get("quantity", 1))

                        filename: str | None = None
                        target_serial: str = self.printer_serial
                        min_temp: float = self.min_bed_temp

                        if ean and ean in mapping:
                            entry = mapping[ean]
                            if isinstance(entry, dict):
                                filename = entry.get("filename")
                                target_serial = entry.get("printer_serial") or self.printer_serial
                                try:
                                    thr = entry.get("bed_temp_threshold")
                                    if thr is None:
                                        thr = entry.get("min_bed_temp")
                                    if thr is not None:
                                        min_temp = float(thr)
                                except Exception:
                                    min_temp = self.min_bed_temp
                            else:
                                filename = entry
                                target_serial = self.printer_serial
                                min_temp = self.min_bed_temp

                            if filename:
                                try:
                                    add_to_queue(target_serial, filename, qty, min_temp)
                                    save_queue()
                                    print(
                                        f"✅ Nieuwe bestelling {filename} x{qty} → wachtrij printer {target_serial} "
                                        f"(EAN {ean}, item {iid}, temp {min_temp}°C)"
                                    )
                                    append_history({
                                        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                                        "orderItemId": iid,
                                        "ean": ean,
                                        "filename": filename,
                                        "quantity": qty,
                                        "printer_serial": target_serial,
                                        # Log the temperature used
                                        "min_bed_temp": min_temp,
                                    })
                                except Exception as e:
                                    print(f"⚠️ Kon item niet toevoegen aan wachtrij: {e}")
                            else:
                                print(f"⚠️ Mapping zonder filename voor EAN {ean}")
                        else:
                            if ean:
                                print(f"⚠️ Geen mapping voor EAN {ean} (orderItemId {iid})")
                            else:
                                print(f"⚠️ Ontbrekende EAN voor orderItemId {iid}")

                        new_processed.add(iid)

                processed = new_processed
                # Always persist processed IDs so we don't log duplicates on restart
                save_processed_ids(processed)

            except Exception as ex:
                print(f"Fout in BolOrderWatcher: {ex}")

            # Sleep for the configured interval, but wake early if stopped
            for _ in range(self.interval):
                if self._stop.is_set():
                    break
                time.sleep(1)
