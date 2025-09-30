"""
Entry point for the web interface.

"""

import io
import json
import threading
import time
from typing import List, Dict, Any

import requests
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    jsonify,
    g,
    Response,
)

from .constants import UPLOAD_FOLDER, SECRET_KEY, BED_TEMP_THRESHOLD
from .config_manager import load_config, save_config
from .eventbus import EventBus
from .printer_manager import PrinterManager
from .mapping_manager import read_mapping, write_mapping
from .printer import Printer

from history import load_history, export_history_csv  
from queue_manager import get_queue, add_to_queue, remove_from_queue, save_queue, mark_current_done 
from printer_files import fetch_files_from_printer
from ftps import upload_file_to_printer, delete_file_from_printer 
from start_print import start_print
from .bol.watcher import BolOrderWatcher  


# ----------------------------------------------------------------------------
# Application initialisation
# ----------------------------------------------------------------------------

app = Flask(__name__)

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.secret_key = SECRET_KEY

event_bus = EventBus()
printer_manager = PrinterManager()


# ----------------------------------------------------------------------------
# Context processors and request hooks
# ----------------------------------------------------------------------------

@app.context_processor
def inject_settings() -> Dict[str, Any]:
    return {"app_settings": load_config()}


@app.before_request
def apply_dark_mode_to_g() -> None:
    g.dark_mode = bool(load_config().get("dark_mode", False))


# ----------------------------------------------------------------------------
# Event streaming
# ----------------------------------------------------------------------------

@app.route("/events")
def sse_events() -> Response:
    q = event_bus.add_listener()
    resp = Response(event_bus.sse_stream(q), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# ----------------------------------------------------------------------------
# Feedback from ESP modules
# ----------------------------------------------------------------------------

@app.route("/schuif_feedback", methods=["POST"])
def schuif_feedback() -> Response:
    data = request.get_json(force=True) or {}
    status = data.get("status")
    esp_ip = request.remote_addr
    serial = printer_manager.handle_slide_feedback(esp_ip, status)
    if not serial:
        return jsonify({"result": "printer not found for IP"}), 404
    if status == "vast":
        event_bus.emit(
            "slide_jam",
            f"Schuif vastgelopen bij printer {serial}",
            {"serial": serial}
        )
    return jsonify({"result": "ok"})


# ----------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------

@app.route("/settings")
def settings_page() -> Response:
    """Render the settings page with the current configuration and printers."""
    cfg = load_config()
    printers = list(printer_manager.printers.values())
    return render_template("settings.html", settings=cfg, printers=printers)


@app.route("/settings/global", methods=["POST"])
def settings_save_global() -> Response:
    """Persist global settings from the settings form."""
    cfg = load_config()
    val = (request.form.get("default_min_bed_temp") or "").strip()
    try:
        cfg["default_min_bed_temp"] = float(val)
    except Exception:
        pass  # keep existing value
    cfg["dark_mode"] = ("dark_mode" in request.form)
    cfg["browser_notifications"] = ("browser_notifications" in request.form)
    save_config(cfg)
    return redirect(url_for("settings_page"))


@app.route("/settings/update_printer", methods=["POST"])
def settings_update_printer() -> Response:
    """Update printer details from the settings page."""
    old_serial = request.form.get("old_serial", "")
    name = (request.form.get("name") or "").strip()
    ip = (request.form.get("ip") or "").strip()
    serial = (request.form.get("serial") or "").strip()
    access_code = (request.form.get("access_code") or "").strip()
    esp_ip = (request.form.get("esp_ip") or "").strip()

    pr = printer_manager.get_printer(old_serial)
    if not pr:
        return "Printer niet gevonden", 404

    # Update fields if provided
    if name:
        pr.name = name
    if ip:
        pr.ip = ip
    if serial:
        # serial is also the key in the dictionary; handle rename
        if serial != pr.serial:
            # Remove old key and reinsert
            del printer_manager.printers[pr.serial_str]
            pr.serial = serial
            printer_manager.printers[pr.serial_str] = pr
    if access_code:
        pr.access_code = access_code
    if esp_ip:
        pr.esp_ip = esp_ip

    printer_manager.save_printers()
    return redirect(url_for("settings_page"))


# ----------------------------------------------------------------------------
# Printer management
# ----------------------------------------------------------------------------

@app.route("/add_printer", methods=["POST"])
def add_printer() -> Response:
    name = request.form.get("name")
    ip = request.form.get("ip")
    serial = request.form.get("serial")
    access_code = request.form.get("access_code")
    esp_ip = request.form.get("esp_ip")
    if not all([name, ip, serial, access_code, esp_ip]):
        return "Missing printer fields", 400
    printer_manager.add_printer(name, ip, serial, access_code, esp_ip)
    return redirect(url_for("index"))


@app.route("/remove_printer", methods=["POST"])
def remove_printer() -> Response:
    serial = request.form.get("serial")
    if not serial:
        return "Geen serial opgegeven", 400
    ok = printer_manager.remove_printer(serial)
    if not ok:
        return "Printer niet gevonden", 404
    return redirect(url_for("index"))


@app.route("/deur_openen", methods=["POST"])
def deur_openen_route() -> Response:
    serial = request.form.get("serial")
    pr = printer_manager.get_printer(serial)
    if pr:
        try:
            pr.open_door()
        except Exception as e:
            print(f"Fout bij openen deur: {e}")
    return redirect(url_for("index"))


@app.route("/deur_sluiten", methods=["POST"])
def deur_sluiten_route() -> Response:
    serial = request.form.get("serial")
    pr = printer_manager.get_printer(serial)
    if pr:
        try:
            pr.close_door()
        except Exception as e:
            print(f"Fout bij sluiten deur: {e}")
    return redirect(url_for("index"))


@app.route("/toggle_pause", methods=["POST"])
def toggle_pause_route() -> Response:
    serial = request.form.get("serial")
    if not serial:
        return redirect(url_for("index"))
    pr = printer_manager.get_printer(serial)
    if not pr:
        return redirect(url_for("index"))
    inst = pr.mqtt_client_instance
    if inst:
        try:
            current = (pr.status or "").upper()
            if current == "PRINTING":
                ok = getattr(inst, "pause", lambda: False)()
                if ok:
                    pr.status = "PAUSED"
            elif current in ("PAUSE", "PAUSED"):
                ok = getattr(inst, "resume", lambda: False)()
                if ok:
                    pr.status = "PRINTING"
        except Exception as e:
            print(f"toggle_pause error: {e}")
    return redirect(url_for("index"))


# ----------------------------------------------------------------------------
# Queue management
# ----------------------------------------------------------------------------

@app.route("/add_to_queue", methods=["POST"])
def add_to_queue_route() -> Response:
    serial = request.form.get("serial")
    filename = request.form.get("filename")
    count = request.form.get("count")
    if not all([serial, filename, count]):
        return "Missing queue fields", 400
    try:
        count_int = int(count)
    except Exception:
        return "Ongeldig aantal", 400
    val = (request.form.get("min_bed_temp") or "").strip()
    cfg = load_config()
    try:
        default_min = float(cfg.get("default_min_bed_temp", BED_TEMP_THRESHOLD))
    except Exception:
        default_min = BED_TEMP_THRESHOLD
    try:
        min_bed_temp = float(val) if val != "" else default_min
    except Exception:
        min_bed_temp = default_min
    add_to_queue(serial, filename, count_int, min_bed_temp)
    return redirect(url_for("index"))


@app.route("/remove_from_queue", methods=["POST"])
def remove_from_queue_route() -> Response:
    serial = request.form.get("serial")
    filename = request.form.get("filename")
    remove_from_queue(serial, filename)
    return redirect(url_for("index"))


@app.route("/start_queue", methods=["POST"])
def start_queue_route() -> Response:
    serial = request.form.get("serial")
    pr = printer_manager.get_printer(serial)
    if not pr:
        return "Printer niet gevonden", 404
    queue = get_queue(pr.serial_str)
    print(
        f"Start wachtrij voor printer {pr.name} — status={pr.status} "
        f"finished_cooling_down={pr.finished_cooling_down}"
    )
    print(f"Wachtrij: {queue}")
    if pr.status in ["IDLE", "FINISH", "FAILED", "Onbekend"] and not pr.finished_cooling_down:
        if queue:
            current = queue[0]
            if current.get("printed", 0) < current.get("count", 0) and current.get("status") != "printing":
                print(f"[{pr.name}] Handmatig starten vanuit wachtrij: {current['filename']}")
                current["status"] = "printing"
                save_queue({pr.serial_str: queue})
                try:
                    start_print(pr.__dict__, current["filename"])
                except Exception as e:
                    return f"Fout bij starten: {e}", 500
    return redirect(url_for("index"))


@app.route("/update_min_temp", methods=["POST"])
def update_min_temp_route() -> Response:
    serial = request.form.get("serial")
    filename = request.form.get("filename")
    new_temp = request.form.get("min_bed_temp")
    if not all([serial, filename, new_temp]):
        return "Missing fields", 400
    try:
        new_temp_float = float(new_temp)
    except Exception:
        return "Ongeldige temperatuur", 400
    queue = get_queue(serial)
    for item in queue:
        if item["filename"] == filename:
            item["min_bed_temp"] = new_temp_float
            break
    save_queue({serial: queue})
    return redirect(url_for("index"))


@app.route("/move_up", methods=["POST"])
def move_up_route() -> Response:
    serial = request.form.get("serial")
    filename = request.form.get("filename")
    queue = get_queue(serial)
    for i in range(1, len(queue)):
        if queue[i]["filename"] == filename:
            queue[i - 1], queue[i] = queue[i], queue[i - 1]
            break
    save_queue({serial: queue})
    return redirect(url_for("index"))


@app.route("/move_down", methods=["POST"])
def move_down_route() -> Response:
    serial = request.form.get("serial")
    filename = request.form.get("filename")
    queue = get_queue(serial)
    for i in range(len(queue) - 1):
        if queue[i]["filename"] == filename:
            queue[i], queue[i + 1] = queue[i + 1], queue[i]
            break
    save_queue({serial: queue})
    return redirect(url_for("index"))


@app.route("/reorder_queue", methods=["POST"])
def reorder_queue_route() -> Response:
    try:
        data = request.get_json(force=True) or {}
        serial = data.get("serial")
        order = data.get("order") or []
        if not serial or not isinstance(order, list):
            return jsonify({"ok": False, "error": "invalid_payload"}), 400
        queue = get_queue(serial)
        qmap = {item["filename"]: item for item in queue}
        new_queue = [qmap[f] for f in order if f in qmap]
        for item in queue:
            if item["filename"] not in order:
                new_queue.append(item)
        save_queue({serial: new_queue})
        return jsonify({"ok": True})
    except Exception as e:
        print(f"reorder_queue error: {e}")
        return jsonify({"ok": False, "error": "server_error"}), 500


# ----------------------------------------------------------------------------
# File management (upload/delete)
# ----------------------------------------------------------------------------

@app.route("/start_print", methods=["POST"])
def start_print_route() -> Response:
    serial = request.form.get("serial")
    filename = request.form.get("filename")
    pr = printer_manager.get_printer(serial)
    if not pr:
        print(f"Printer niet gevonden voor serial: {serial}")
        return "Printer niet gevonden", 404
    try:
        start_print(pr.__dict__, filename)
        return redirect(url_for("index"))
    except Exception as e:
        print(f"Fout in start_print(): {e}")
        return f"Fout bij printen: {e}", 500


@app.post("/upload")
def upload_route() -> Response:
    file = request.files.get("file")
    serial = request.form.get("printer_serial")
    if not file:
        return jsonify({"success": False, "error": "No file"}), 400
    pr = printer_manager.get_printer(serial) if serial else None
    if not pr:
        return jsonify({"success": False, "error": "Unknown or missing printer"}), 400
    res = upload_file_to_printer(file, pr.__dict__)
    status = 200 if res.get("success") else 500
    return jsonify(res), status


@app.route("/upload_file", methods=["POST"])
def upload_file_ajax() -> Response:
    try:
        file = request.files.get('file')
        serial = request.form.get('serial')
        if not file or not serial:
            return "missing file or serial", 400
        pr = printer_manager.get_printer(serial)
        if not pr:
            return "printer not found", 404
        res = upload_file_to_printer(file, pr.__dict__)
        if res.get("success"):
            return "ok"
        return f"error: {res.get('error','unknown')}", 500
    except Exception as e:
        print(f"upload_file_ajax error: {e}")
        return "server error", 500


@app.route("/delete_file", methods=["POST"])
def delete_file_route() -> Response:
    serial = request.form.get("serial")
    filename = request.form.get("filename")
    pr = printer_manager.get_printer(serial)
    if not pr:
        return "Printer niet gevonden", 404
    result = delete_file_from_printer(pr.__dict__, filename)
    if result.get("success"):
        return redirect(url_for("index"))
    else:
        return f"Fout bij verwijderen: {result.get('error')}", 500


# ----------------------------------------------------------------------------
# Slide activation
# ----------------------------------------------------------------------------

@app.route("/activate", methods=["POST"])
def activate() -> Response:
    serial = (request.form.get("serial") or "").strip()
    if not serial:
        flash("Geen printer‑serial opgegeven.", "danger")
        return redirect(url_for("index"))
    pr = printer_manager.get_printer(serial)
    if not pr:
        flash("Printer niet gevonden.", "danger")
        return redirect(url_for("index"))
    success = False
    try:
        success = pr.activate_slide()
    except Exception as e:
        print(f"Activate error: {e}")
    if success:
        flash(f"Schuif voor {pr.name} geactiveerd.", "success")
    else:
        flash(f"Fout bij activeren van de schuif van {pr.name}", "danger")
    return redirect(url_for("index"))


# ----------------------------------------------------------------------------
# Data 
# ----------------------------------------------------------------------------

@app.route("/data")
def data_route() -> Response:
    """Return a simplified JSON structure with printer statuses."""
    simplified: List[Dict[str, Any]] = []
    for pr in printer_manager.printers.values():
        simplified.append({
            "name": pr.name,
            "serial": pr.serial,
            "status": pr.status,
            "bed_temp": pr.bed_temp,
            "mc_percent": pr.mc_percent,
        })
    return jsonify(simplified)


# ----------------------------------------------------------------------------
# Orders
# ----------------------------------------------------------------------------

@app.route("/orders")
def orders() -> Response:
    mapping = read_mapping()
    mapping_list: List[Dict[str, Any]] = []
    for k, v in mapping.items():
        if isinstance(v, dict):
            mapping_list.append({
                "ean": k,
                "filename": v.get("filename", ""),
                "printer_serial": v.get("printer_serial", ""),
                "bed_temp_threshold": v.get("bed_temp_threshold"),
            })
        else:
            mapping_list.append({
                "ean": k,
                "filename": v,
                "printer_serial": "",
                "bed_temp_threshold": None,
            })
    collect_printer_files()  
    items = load_history(limit=500)  
    cfg = load_config()
    default_min_bed_temp = cfg.get("default_min_bed_temp", BED_TEMP_THRESHOLD)
    return render_template(
        "orders.html",
        mapping_list=sorted(mapping_list, key=lambda x: x["ean"]),
        items=items,
        printers=list(printer_manager.printers.values()),
        default_min_bed_temp=default_min_bed_temp,
    )


@app.post("/orders/map-add")
def orders_map_add() -> Response:
    ean = (request.form.get("ean") or "").strip()
    filename = (request.form.get("filename") or "").strip()
    printer_serial = (request.form.get("printer_serial") or "").strip()
    thr_raw = (request.form.get("bed_temp_threshold") or "").strip()
    if not ean or not filename:
        flash("Vul zowel EAN als bestand in.", "danger")
        return redirect(url_for("orders"))
    if not ean.isdigit() or not (8 <= len(ean) <= 14):
        flash("EAN lijkt ongeldig. Alleen cijfers, 8–14 tekens.", "danger")
        return redirect(url_for("orders"))
    if printer_serial and not printer_manager.get_printer(printer_serial):
        flash("Onbekende printer.", "danger")
        return redirect(url_for("orders"))
    cfg = load_config()
    default_thr = float(cfg.get("default_min_bed_temp", BED_TEMP_THRESHOLD))
    try:
        thr = float(thr_raw) if thr_raw else default_thr
    except Exception:
        thr = default_thr
    thr = max(20.0, min(110.0, thr))
    mapping = read_mapping()
    mapping[ean] = {
        "filename": filename,
        "printer_serial": printer_serial,
        "bed_temp_threshold": thr,
    }
    write_mapping(mapping)
    flash(
        f"Mapping toegevoegd: {ean} → {filename} (temp: {thr:.0f}°C, printer: {printer_serial or '–'})",
        "success",
    )
    return redirect(url_for("orders"))


@app.post("/orders/map-update")
def orders_map_update() -> Response:
    original_ean = (request.form.get("original_ean") or "").strip()
    new_ean = (request.form.get("ean") or "").strip()
    filename = (request.form.get("filename") or "").strip()
    printer_serial = (request.form.get("printer_serial") or "").strip()
    thr_raw = (request.form.get("bed_temp_threshold") or "").strip()
    if not original_ean:
        flash("Ontbrekende originele EAN.", "danger")
        return redirect(url_for("orders"))
    if not new_ean or not new_ean.isdigit() or not (8 <= len(new_ean) <= 14):
        flash("Nieuwe EAN ongeldig. Alleen cijfers, 8–14 tekens.", "danger")
        return redirect(url_for("orders"))
    if not filename:
        flash("Kies een bestand.", "danger")
        return redirect(url_for("orders"))
    if printer_serial and not printer_manager.get_printer(printer_serial):
        flash("Onbekende printer.", "danger")
        return redirect(url_for("orders"))
    cfg = load_config()
    default_thr = float(cfg.get("default_min_bed_temp", BED_TEMP_THRESHOLD))
    try:
        thr = float(thr_raw) if thr_raw else default_thr
    except Exception:
        thr = default_thr
    thr = max(20.0, min(110.0, thr))
    mapping = read_mapping()
    if original_ean not in mapping:
        flash("Originele EAN niet gevonden.", "danger")
        return redirect(url_for("orders"))
    if new_ean != original_ean and new_ean in mapping:
        flash(f"EAN {new_ean} bestaat al.", "danger")
        return redirect(url_for("orders"))
    if new_ean != original_ean:
        mapping.pop(original_ean, None)
    mapping[new_ean] = {
        "filename": filename,
        "printer_serial": printer_serial,
        "bed_temp_threshold": thr,
    }
    write_mapping(mapping)
    flash(
        f"Mapping opgeslagen: {new_ean} → {filename} (temp: {thr:.0f}°C, printer: {printer_serial or '–'})",
        "success",
    )
    return redirect(url_for("orders"))


@app.post("/orders/map-delete")
def orders_map_delete() -> Response:
    ean = (request.form.get("ean") or "").strip()
    if not ean:
        flash("Geen EAN opgegeven.", "danger")
        return redirect(url_for("orders"))
    mapping = read_mapping()
    if ean in mapping:
        mapping.pop(ean)
        write_mapping(mapping)
        flash(f"Mapping verwijderd: {ean}", "success")
    else:
        flash("EAN niet gevonden.", "danger")
    return redirect(url_for("orders"))


@app.route("/orders/history.csv")
def orders_history_csv() -> Response:
    csv_bytes = export_history_csv()  
    return send_file(
        io.BytesIO(csv_bytes),
        mimetype="text/csv",
        as_attachment=True,
        download_name="print_history.csv",
    )


@app.route("/orders/mapping.json")
def orders_mapping_json() -> Response:
    return jsonify(read_mapping())


# ----------------------------------------------------------------------------
# Index / home page
# ----------------------------------------------------------------------------

def collect_printer_files() -> List[Printer]:  # type: ignore
    """Fetch files from all printers for listing in the UI."""
    for pr in printer_manager.printers.values():
        try:
            pr.files = fetch_files_from_printer(pr.ip, "bblp", pr.access_code)  # type: ignore
        except Exception:
            pr.files = []
    return list(printer_manager.printers.values())


@app.route("/")
def index() -> Response:
    for pr in printer_manager.printers.values():
        # Update list of files and queue for each printer
        try:
            pr.files = fetch_files_from_printer(pr.ip, "bblp", pr.access_code)  # type: ignore
        except Exception:
            pr.files = []
        pr.queue = get_queue(pr.serial_str)
        # Query the ESP for door status if reachable
        try:
            resp = requests.get(f"http://{pr.esp_ip}/deur_status", timeout=1)
            pr.deur_status = resp.json().get("deur_status", "onbekend")
        except Exception:
            pr.deur_status = "niet bereikbaar"
    return render_template("index.html", printers=list(printer_manager.printers.values()))


# ----------------------------------------------------------------------------
# App entrypoint
# ----------------------------------------------------------------------------

if __name__ == "__main__":
    # Optionally start the BolOrderWatcher based on configuration and available printers
    try:
        try:
            from config import PRINTER_SERIAL as DEFAULT_PRINTER_SERIAL  # type: ignore
        except Exception:
            DEFAULT_PRINTER_SERIAL = None
        target_serial = None
        try:
            target_serial = (
                list(printer_manager.printers.values())[0].serial
                if DEFAULT_PRINTER_SERIAL is None
                else DEFAULT_PRINTER_SERIAL
            )
        except Exception:
            target_serial = DEFAULT_PRINTER_SERIAL
        if target_serial:
            cfg = load_config()
            _min_temp = float(cfg.get("default_min_bed_temp", BED_TEMP_THRESHOLD))
            _bol_watcher = BolOrderWatcher(
                printer_serial=target_serial, interval_sec=120, min_bed_temp=_min_temp
            )
            _bol_watcher.start()
        app.run(debug=True, host="0.0.0.0", port=5000)
    except Exception as _e:
        print(f"Kon BolOrderWatcher niet starten of app runnen: {_e}")