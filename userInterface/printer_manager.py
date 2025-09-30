"""
Management of printers and automatic handling of print cycles.

The `PrinterManager` class is responsible for loading printer
definitions from disk, managing the lifecycle of printers and their
associated MQTT clients, and running a background thread per printer
which automates slide activation and automatic print starting.

When a printer is added or loaded the manager starts a `PrinterClient`
from the `mqtt_listener` module and calls `start_auto_trigger()` on
that printer, which launches a loop that monitors the printer's
status and temperature and initiates actions such as opening the door,
activating the slide or starting the next print when appropriate.

The manager also provides helper methods to save printers back to
disk, add or remove printers at runtime, and handle slide feedback
events.
"""

import json
import threading
import time
from typing import Dict, Optional

from .constants import PRINTER_FILE, BED_TEMP_THRESHOLD
from .printer import Printer
from .config_manager import load_config

from queue_manager import get_queue, save_queue, mark_current_done  # type: ignore
from start_print import start_print  # type: ignore
from mqtt_listener import PrinterClient  # type: ignore


class PrinterManager:
    def __init__(self) -> None:
        self.printers: Dict[str, Printer] = {}
        self.load_printers()

    def load_printers(self) -> None:
        if PRINTER_FILE.exists():
            try:
                data = json.loads(PRINTER_FILE.read_text(encoding="utf-8"))
                for p in data:
                    printer = Printer(
                        name=p.get("name"),
                        ip=p.get("ip"),
                        serial=str(p.get("serial")),
                        access_code=p.get("access_code"),
                        esp_ip=p.get("esp_ip"),
                    )
                    self.printers[printer.serial_str] = printer
            except Exception as e:
                print(f"Kon printers.json niet lezen: {e}")
        for printer in self.printers.values():
            self._start_mqtt_for(printer)
            self.start_auto_trigger(printer)

    def _start_mqtt_for(self, printer: Printer) -> None:
        try:
            mqtt_instance = PrinterClient(printer.__dict__)
            mqtt_instance.start()
            printer.mqtt_client_instance = mqtt_instance
        except Exception as e:
            print(f"⚠️ Kon MQTT niet starten voor {printer.name}: {e}")

    def save_printers(self) -> None:
        try:
            with open(PRINTER_FILE, "w", encoding="utf-8") as f:
                json.dump([
                    {
                        "name": p.name,
                        "ip": p.ip,
                        "serial": p.serial,
                        "access_code": p.access_code,
                        "esp_ip": p.esp_ip,
                    }
                    for p in self.printers.values()
                ], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("⚠️ Kon printers.json niet schrijven:", e)

    def add_printer(self, name: str, ip: str, serial: str, access_code: str, esp_ip: str) -> Printer:
        printer = Printer(name=name, ip=ip, serial=serial, access_code=access_code, esp_ip=esp_ip)
        self.printers[printer.serial_str] = printer
        self.save_printers()
        self._start_mqtt_for(printer)
        self.start_auto_trigger(printer)
        return printer

    def remove_printer(self, serial: str) -> bool:
        serial_str = str(serial)
        printer = self.printers.get(serial_str)
        if not printer:
            return False
        # Stop MQTT if running
        if printer.mqtt_client_instance:
            try:
                printer.mqtt_client_instance.stop()
            except Exception as e:
                print(f"Fout bij stoppen van MQTT: {e}")
        del self.printers[serial_str]
        self.save_printers()
        return True

    def get_printer(self, serial: str) -> Optional[Printer]:
        """Retrieve a printer by serial, or None if not found."""
        return self.printers.get(str(serial))

    def start_auto_trigger(self, printer: Printer) -> None:
        def loop() -> None:
            while True:
                current_status = printer.status
                previous_status = printer.vorige_status

                # When a print is running reset flags to indicate a print is underway
                if current_status == "PRINTING":
                    printer.heeft_geprint = True
                    printer.finished_cooling_down = False
                    printer.schuif_bezig = False
                    printer.schuif_commando_verstuurd = False

                # Print just finished; open the door and set waiting-for-cooldown flag
                if (
                    printer.heeft_geprint
                    and previous_status == "PRINTING"
                    and current_status in ["IDLE", "FINISH", "Onbekend"]
                    and not printer.finished_cooling_down
                ):
                    success = printer.open_door()
                    if success:
                        print(f" [{printer.name}] Deur open commando verzonden")
                    else:
                        print(f" [{printer.name}] Fout bij deur openen")
                    printer.finished_cooling_down = True

                cfg = load_config()
                try:
                    config_default = float(cfg.get("default_min_bed_temp", BED_TEMP_THRESHOLD))
                except Exception:
                    config_default = BED_TEMP_THRESHOLD

                queue = get_queue(printer.serial_str)
                if queue:
                    current_item = queue[0]
                    try:
                        min_temp = float(current_item.get("min_bed_temp", config_default))
                    except Exception:
                        min_temp = config_default
                else:
                    min_temp = config_default

                # If the bed is cool enough and we're waiting on cooldown and the slide
                # isn't already in progress, trigger the slide mechanism.
                if (
                    printer.finished_cooling_down
                    and printer.bed_temp <= min_temp
                    and not printer.schuif_bezig
                    and not printer.schuif_vastgelopen
                    and not printer.schuif_commando_verstuurd
                ):
                    print(f"[{printer.name}] Bed koel genoeg, schuif activeren...")
                    success = printer.activate_slide()
                    if success:
                        printer.schuif_bezig = True
                        printer.schuif_commando_verstuurd = True
                        printer.finished_cooling_down = False
                        print(" Schuifcommando verzonden")
                    else:
                        print(" Fout bij verzenden schuifcommando")

                # When the printer is idle and not cooling or sliding, start the next print
                if (
                    current_status in ["IDLE", "FINISH", "Onbekend"]
                    and not printer.finished_cooling_down
                    and not printer.schuif_bezig
                ):
                    queue = get_queue(printer.serial_str)
                    if queue:
                        current = queue[0]
                        # Only start if count isn't reached and we aren't already printing
                        if current.get("printed", 0) < current.get("count", 0) and current.get("status") != "printing":
                            print(f"📨 [{printer.name}] Start print vanuit wachtrij: {current['filename']}")
                            current["status"] = "printing"
                            save_queue({printer.serial_str: queue})
                            try:
                                start_print(printer.__dict__, current["filename"])
                            except Exception as e:
                                print(f"❌ Fout bij automatisch starten: {e}")

                printer.vorige_status = current_status
                time.sleep(2)
                # Debug logging
                print(
                    f"[{printer.name}] DEBUG: status={printer.status} temp={printer.bed_temp} "
                    f"wacht_op_afkoeling={printer.finished_cooling_down} schuif_bezig={printer.schuif_bezig}"
                )

        threading.Thread(target=loop, daemon=True).start()

    def handle_slide_feedback(self, esp_ip: str, status: str) -> Optional[str]:
        printer = next((p for p in self.printers.values() if p.esp_ip == esp_ip), None)
        if not printer:
            return None
        if status == "klaar":
            printer.schuif_bezig = False
            printer.finished_cooling_down = False
            printer.heeft_geprint = False
            printer.schuif_commando_verstuurd = False
            printer.close_door()
            # Mark current queue item as done via queue manager
            mark_current_done(printer.serial_str)
        elif status == "vast":
            printer.schuif_bezig = True
            printer.schuif_vastgelopen = True
            printer.schuif_commando_verstuurd = False
        return printer.serial_str