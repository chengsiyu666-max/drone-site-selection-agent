from __future__ import annotations

import csv
import io
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_TOKEN = os.environ.get("DEEPSEEK_TOKEN", "")
DEEPSEEK_MODEL = "deepseek-chat"

from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from openclaw_client import openclaw_chat, openclaw_chat_stream

from optimizer import (
    city_params,
    get_city_configs,
    normalize_city,
    parse_rdcs,
    parse_stores,
    point_inner_ring_violation,
    run_full_model,
)


BASE_DIR = Path(__file__).resolve().parent
SAMPLE_DIR = BASE_DIR / "sample_data"
AGENT_OUTPUT_DIR = BASE_DIR / "agent_outputs"
BUILTIN_EXISTING_STORES_FILE = SAMPLE_DIR / "existing_stores_beijing_hangzhou.csv"

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))


def _is_excel_bytes(raw: bytes) -> bool:
    # xlsx/xlsm (zip container)
    if raw.startswith(b"PK\x03\x04"):
        return True
    # legacy xls (OLE Compound File)
    if raw.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
        return True
    return False


def _parse_excel_upload(raw: bytes, label: str) -> List[Dict[str, object]]:
    try:
        import pandas as pd

        df = pd.read_excel(io.BytesIO(raw), sheet_name=0, dtype=object)
    except Exception as exc:
        raise ValueError(f"{label} looks like an Excel file, but failed to parse: {exc}") from exc

    df = df.dropna(how="all")
    rows: List[Dict[str, object]] = []
    for rec in df.to_dict(orient="records"):
        row: Dict[str, object] = {}
        for k, v in rec.items():
            key = str(k).strip() if k is not None else ""
            if not key or key.lower().startswith("unnamed:"):
                continue
            if pd.isna(v):
                row[key] = ""
            else:
                row[key] = v
        if any(str(v).strip() for v in row.values()):
            rows.append(row)
    return rows


def parse_csv_upload(file_obj, label: str = "file") -> List[Dict[str, str]]:
    if file_obj is None or not file_obj.filename:
        return []
    raw = file_obj.read()
    if not raw:
        return []

    # Support non-standard uploads where an Excel file is renamed as .csv.
    if _is_excel_bytes(raw):
        return _parse_excel_upload(raw, label)

    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="ignore")

    last_exc: Exception | None = None
    candidates = [text, text.replace("\r\n", "\n").replace("\r", "\n")]
    for candidate in candidates:
        try:
            reader = csv.DictReader(io.StringIO(candidate, newline=""))
            return [dict(row) for row in reader]
        except csv.Error as exc:
            last_exc = exc

    # Last fallback: try parsing as Excel when text CSV parse fails.
    if _is_excel_bytes(raw):
        return _parse_excel_upload(raw, label)

    raise ValueError(f"{label} is not a valid CSV: {last_exc}")


def parse_csv_file(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def parse_p_values(raw: str) -> List[int]:
    values = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            continue
    return values or [1, 2, 3, 4, 5]


def parse_int(raw: str, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def parse_bool(raw: str, default: bool = False) -> bool:
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "t", "on"}:
        return True
    if text in {"0", "false", "no", "n", "f", "off"}:
        return False
    return default


def parse_float(raw: str, default: float | None = None) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def chunked(seq: Sequence, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def merge_distance_rows(primary_rows: List[Dict[str, object]], secondary_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    merged: Dict[Tuple[str, str], Dict[str, object]] = {}
    for row in primary_rows:
        key = (str(row.get("rdc_id") or ""), str(row.get("store_id") or ""))
        if key[0] and key[1]:
            merged[key] = dict(row)
    for row in secondary_rows:
        key = (str(row.get("rdc_id") or ""), str(row.get("store_id") or ""))
        if key[0] and key[1]:
            merged[key] = dict(row)
    return list(merged.values())


def merge_store_rows(primary_rows: List[Dict[str, object]], secondary_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """
    Merge store rows by `store_id`, keeping uploaded rows as authoritative and
    appending only missing supplemental records.
    """
    seen_ids = set()
    merged: List[Dict[str, object]] = []

    for row in primary_rows:
        store_id = str(row.get("store_id") or row.get("id") or "").strip()
        if store_id:
            seen_ids.add(store_id)
        merged.append(dict(row))

    for row in secondary_rows:
        store_id = str(row.get("store_id") or row.get("id") or "").strip()
        if not store_id or store_id in seen_ids:
            continue
        seen_ids.add(store_id)
        merged.append(dict(row))

    return merged


def amap_distance_batch(origins: List[Tuple[str, float, float]], destination_lon: float, destination_lat: float, amap_key: str, timeout_sec: int):
    origin_text = "|".join(f"{lon},{lat}" for _, lat, lon in origins)
    params = {
        "origins": origin_text,
        "destination": f"{destination_lon},{destination_lat}",
        "type": 1,
        "key": amap_key,
    }
    url = "https://restapi.amap.com/v3/distance?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "happy-monkey-site-model/1.0"})
    with urlopen(req, timeout=timeout_sec) as resp:
        payload = resp.read().decode("utf-8", errors="ignore")
    data = json.loads(payload)
    if str(data.get("status")) != "1":
        raise RuntimeError(data.get("info") or "unknown amap api error")

    results = data.get("results") or []
    out = []
    for idx, row in enumerate(origins):
        r = results[idx] if idx < len(results) else None
        if not r:
            continue
        distance_m = float(r.get("distance") or 0.0)
        out.append((row[0], distance_m / 1000.0))
    return out


def build_amap_distance_rows(store_rows: List[Dict[str, object]], rdc_rows: List[Dict[str, object]], amap_key: str, timeout_sec: int = 8):
    stores = [s for s in parse_stores(store_rows) if -90 <= s.lat <= 90 and -180 <= s.lon <= 180]
    rdcs = [r for r in parse_rdcs(rdc_rows) if -90 <= r.lat <= 90 and -180 <= r.lon <= 180]

    warnings: List[str] = []
    rows: List[Dict[str, object]] = []

    stores_by_city: Dict[str, List] = {}
    rdcs_by_city: Dict[str, List] = {}
    for s in stores:
        stores_by_city.setdefault(s.city, []).append(s)
    for r in rdcs:
        rdcs_by_city.setdefault(r.city, []).append(r)

    for city, city_stores in stores_by_city.items():
        city_rdcs = rdcs_by_city.get(city, [])
        if not city_rdcs:
            continue

        origins = [(r.rdc_id, r.lat, r.lon) for r in city_rdcs]
        for store in city_stores:
            for batch in chunked(origins, 20):
                try:
                    results = amap_distance_batch(batch, store.lon, store.lat, amap_key, timeout_sec=timeout_sec)
                except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as exc:
                    warnings.append(f"amap distance failed for {city}/{store.store_id}: {exc}")
                    continue

                for rdc_id, km in results:
                    rows.append({"rdc_id": rdc_id, "store_id": store.store_id, "distance_km": round(km, 6)})

    return rows, warnings


def parse_custom_rdcs(raw_json: str, focus_city: str | None = None) -> List[Dict[str, object]]:
    if not raw_json:
        return []
    try:
        arr = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(arr, list):
        return []

    out: List[Dict[str, object]] = []
    for idx, item in enumerate(arr, start=1):
        if not isinstance(item, dict):
            continue

        city = normalize_city(str(item.get("city") or focus_city or "beijing"))
        cp = city_params(city)
        lat = float(item.get("lat") or 0.0)
        lon = float(item.get("lon") or 0.0)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue

        rent_cap = float(cp.get("rent_cap_per_sqm_day") or 1.7)
        out.append(
            {
                "rdc_id": str(item.get("rdc_id") or f"CUSTOM_{idx}"),
                "name": str(item.get("name") or f"Custom RDC {idx}"),
                "city": city,
                "lat": lat,
                "lon": lon,
                "area_sqm": float(item.get("area_sqm") or 10000),
                "initial_investment_10k": float(item.get("initial_investment_10k") or 220),
                "annual_rent_10k": float(item.get("annual_rent_10k") or 500),
                "annual_property_10k": float(item.get("annual_property_10k") or 38),
                "annual_operating_10k": float(item.get("annual_operating_10k") or 58),
                "annual_labor_10k": float(item.get("annual_labor_10k") or 53),
                "annual_utility_10k": float(item.get("annual_utility_10k") or 33),
                "residual_rate": float(item.get("residual_rate") or 0.25),
                "rent_per_sqm_day": float(item.get("rent_per_sqm_day") or max(rent_cap - 0.08, 0.5)),
                "lease_years": float(item.get("lease_years") or 6),
                "blue_access": int(item.get("blue_access") if item.get("blue_access") is not None else 1),
                "core_travel_min": float(item.get("core_travel_min") or 28),
                "clear_height_m": float(item.get("clear_height_m") or 7.5),
                "loading_dock": int(item.get("loading_dock") if item.get("loading_dock") is not None else 1),
                "can_three_temp": int(item.get("can_three_temp") if item.get("can_three_temp") is not None else 1),
                "fire_pass": int(item.get("fire_pass") if item.get("fire_pass") is not None else 1),
                "disturbance_risk": int(item.get("disturbance_risk") if item.get("disturbance_risk") is not None else 0),
            }
        )

    return out


def build_threshold_overrides(focus_city: str, npv_raw: str, dpp_raw: str, rev_raw: str):
    npv_val = parse_float(npv_raw)
    dpp_val = parse_float(dpp_raw)
    rev_val = parse_float(rev_raw)
    if npv_val is None and dpp_val is None and rev_val is None:
        return None

    payload = {}
    targets = [focus_city] if focus_city in {"beijing", "hangzhou"} else ["beijing"]
    for city in targets:
        payload[city] = {}
        if npv_val is not None:
            payload[city]["npv_threshold_10k"] = npv_val
        if dpp_val is not None:
            payload[city]["dpp_threshold_years"] = dpp_val
        if rev_val is not None:
            payload[city]["revenue_per_sqm_threshold_10k"] = rev_val
    return payload


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/cities")
def city_configs():
    return jsonify({"cities": get_city_configs()})


@app.post("/api/validate-rdc-point")
def validate_rdc_point():
    payload = request.get_json(silent=True) or {}
    city = str(payload.get("city") or "")
    lat = float(payload.get("lat") or 0.0)
    lon = float(payload.get("lon") or 0.0)
    return jsonify(point_inner_ring_violation(city, lat, lon))


@app.get("/api/sample/<filename>")
def sample_file(filename: str):
    safe = {
        "stores.csv": "stores.csv",
        "rdcs.csv": "rdcs.csv",
        "distances.csv": "distances.csv",
    }
    if filename not in safe:
        return jsonify({"error": "unknown sample file"}), 404
    return send_from_directory(SAMPLE_DIR, safe[filename], as_attachment=True)


@app.post("/api/run")
def run_model():
    try:
        store_rows = parse_csv_upload(request.files.get("store_file"), "store_file")
        rdc_rows = parse_csv_upload(request.files.get("rdc_file"), "rdc_file")
        uploaded_distance_rows = parse_csv_upload(request.files.get("distance_file"), "distance_file")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not store_rows:
        return jsonify({"error": "store_file is required and must be a valid CSV"}), 400
    if not rdc_rows:
        return jsonify({"error": "rdc_file is required and must be a valid CSV"}), 400

    builtin_existing_rows = parse_csv_file(BUILTIN_EXISTING_STORES_FILE)
    before_merge_store_rows = len(store_rows)
    store_rows = merge_store_rows(store_rows, builtin_existing_rows)
    builtin_existing_added = max(0, len(store_rows) - before_merge_store_rows)

    focus_city = normalize_city(request.form.get("focus_city", ""))
    max_new_stores = parse_int(request.form.get("max_new_stores"), 20)
    p_values = parse_p_values(request.form.get("p_values", "1,2,3,4,5"))
    threshold_overrides = build_threshold_overrides(
        focus_city,
        request.form.get("npv_threshold_10k"),
        request.form.get("dpp_threshold_years"),
        request.form.get("revenue_per_sqm_threshold_10k"),
    )

    custom_rdcs = parse_custom_rdcs(request.form.get("custom_rdcs_json", ""), focus_city=focus_city)
    if custom_rdcs:
        rdc_rows = list(rdc_rows) + custom_rdcs

    use_road_distance = parse_bool(request.form.get("use_road_distance"), False)
    amap_key = (request.form.get("amap_key") or "").strip()

    generated_distance_rows: List[Dict[str, object]] = []
    amap_warnings: List[str] = []
    distance_source = "uploaded_or_haversine"

    if use_road_distance and amap_key:
        generated_distance_rows, amap_warnings = build_amap_distance_rows(store_rows, rdc_rows, amap_key)
        distance_source = "amap_driving+uploaded_fallback"

    # merge_distance_rows: secondary overwrites primary.
    # When Amap is enabled we want it to be authoritative and fall back to the
    # uploaded file only for pairs Amap couldn't resolve — so uploaded is the
    # primary (base layer) and Amap results are layered on top.
    distance_rows = merge_distance_rows(uploaded_distance_rows, generated_distance_rows)

    try:
        result = run_full_model(
            store_rows=store_rows,
            rdc_rows=rdc_rows,
            distance_rows=distance_rows,
            max_new_stores=max_new_stores,
            p_values=p_values,
            focus_city=focus_city if focus_city in {"beijing", "hangzhou"} else "beijing",
            threshold_overrides=threshold_overrides,
        )
    except Exception as exc:
        return jsonify({"error": f"model execution failed: {exc}"}), 500

    result["meta"] = {
        "distance_source": distance_source,
        "uploaded_distance_rows": len(uploaded_distance_rows),
        "amap_distance_rows": len(generated_distance_rows),
        "amap_warnings": amap_warnings[:40],
        "custom_rdcs": len(custom_rdcs),
        "builtin_existing_store_rows": len(builtin_existing_rows),
        "builtin_existing_store_rows_added": builtin_existing_added,
    }

    return jsonify(result)


@app.post("/api/run-sample")
def run_sample_model():
    store_rows = parse_csv_file(SAMPLE_DIR / "stores.csv")
    rdc_rows = parse_csv_file(SAMPLE_DIR / "rdcs.csv")
    uploaded_distance_rows = parse_csv_file(SAMPLE_DIR / "distances.csv")

    builtin_existing_rows = parse_csv_file(BUILTIN_EXISTING_STORES_FILE)
    before_merge_store_rows = len(store_rows)
    store_rows = merge_store_rows(store_rows, builtin_existing_rows)
    builtin_existing_added = max(0, len(store_rows) - before_merge_store_rows)

    focus_city = normalize_city(request.form.get("focus_city", ""))
    max_new_stores = parse_int(request.form.get("max_new_stores"), 20)
    p_values = parse_p_values(request.form.get("p_values", "1,2,3,4,5"))
    threshold_overrides = build_threshold_overrides(
        focus_city,
        request.form.get("npv_threshold_10k"),
        request.form.get("dpp_threshold_years"),
        request.form.get("revenue_per_sqm_threshold_10k"),
    )

    custom_rdcs = parse_custom_rdcs(request.form.get("custom_rdcs_json", ""), focus_city=focus_city)
    if custom_rdcs:
        rdc_rows = list(rdc_rows) + custom_rdcs

    use_road_distance = parse_bool(request.form.get("use_road_distance"), False)
    amap_key = (request.form.get("amap_key") or "").strip()

    generated_distance_rows: List[Dict[str, object]] = []
    amap_warnings: List[str] = []
    distance_source = "sample+uploaded_or_haversine"

    if use_road_distance and amap_key:
        generated_distance_rows, amap_warnings = build_amap_distance_rows(store_rows, rdc_rows, amap_key)
        distance_source = "sample+amap_driving+uploaded_fallback"

    # merge_distance_rows: secondary overwrites primary.
    # When Amap is enabled we want it to be authoritative and fall back to the
    # uploaded file only for pairs Amap couldn't resolve — so uploaded is the
    # primary (base layer) and Amap results are layered on top.
    distance_rows = merge_distance_rows(uploaded_distance_rows, generated_distance_rows)

    try:
        result = run_full_model(
            store_rows=store_rows,
            rdc_rows=rdc_rows,
            distance_rows=distance_rows,
            max_new_stores=max_new_stores,
            p_values=p_values,
            focus_city=focus_city if focus_city in {"beijing", "hangzhou"} else "beijing",
            threshold_overrides=threshold_overrides,
        )
    except Exception as exc:
        return jsonify({"error": f"sample model execution failed: {exc}"}), 500

    result["meta"] = {
        "distance_source": distance_source,
        "uploaded_distance_rows": len(uploaded_distance_rows),
        "amap_distance_rows": len(generated_distance_rows),
        "amap_warnings": amap_warnings[:40],
        "custom_rdcs": len(custom_rdcs),
        "builtin_existing_store_rows": len(builtin_existing_rows),
        "builtin_existing_store_rows_added": builtin_existing_added,
    }

    return jsonify(result)


@app.get("/api/chat/models")
def chat_models():
    return jsonify({"data": [{"id": "openclaw/main", "name": "OpenClaw · main agent (DeepSeek)"}]})


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages") or []
    session_key = str(payload.get("session_key") or "")
    if not messages:
        return jsonify({"error": "messages required"}), 400

    # 取最后一条用户消息作为本次输入
    user_message = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_message = m.get("content", "")
            break
    if not user_message:
        return jsonify({"error": "no user message found"}), 400

    try:
        _t0 = time.perf_counter()
        reply, new_session_key = openclaw_chat(
            user_message=user_message,
            session_key=session_key or None,
            timeout=90,
        )
        _elapsed_ms = (time.perf_counter() - _t0) * 1000
        app.logger.warning(
            "[openclaw_chat_timing] elapsed=%.0fms reuse_session=%s reply_len=%d",
            _elapsed_ms,
            bool(session_key),
            len(reply),
        )
        return jsonify({
            "choices": [{"message": {"role": "assistant", "content": reply}}],
            "session_key": new_session_key,
        })
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502


@app.post("/api/chat/stream")
def chat_stream():
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages") or []
    session_key = str(payload.get("session_key") or "")
    if not messages:
        return jsonify({"error": "messages required"}), 400

    user_message = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_message = m.get("content", "")
            break
    if not user_message:
        return jsonify({"error": "no user message found"}), 400

    def sse_gen():
        t0 = time.perf_counter()
        first_delta_ms = None
        last_text_len = 0
        try:
            for ev in openclaw_chat_stream(
                user_message=user_message,
                session_key=session_key or None,
                timeout=600,
            ):
                ev_type = ev.get("type")
                if ev_type == "delta" and first_delta_ms is None:
                    first_delta_ms = (time.perf_counter() - t0) * 1000
                if ev_type in ("delta", "done"):
                    last_text_len = len(ev.get("text", ""))
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            raise
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            total_ms = (time.perf_counter() - t0) * 1000
            first_str = f"{first_delta_ms:.0f}ms" if first_delta_ms is not None else "n/a"
            app.logger.warning(
                "[openclaw_stream_timing] total=%.0fms first_delta=%s reuse_session=%s reply_len=%d",
                total_ms,
                first_str,
                bool(session_key),
                last_text_len,
            )

    return Response(
        sse_gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/agent-outputs")
def list_agent_outputs():
    if not AGENT_OUTPUT_DIR.exists():
        return jsonify({"files": []})
    files = []
    for p in AGENT_OUTPUT_DIR.iterdir():
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in {".md", ".txt", ".csv", ".json"}:
            files.append({"name": p.name, "mtime": p.stat().st_mtime, "size": p.stat().st_size})
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify({"files": files})


@app.get("/api/agent-outputs/<path:filename>")
def download_agent_output(filename: str):
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return jsonify({"error": "invalid filename"}), 400

    base_dir = AGENT_OUTPUT_DIR.resolve()
    target = (base_dir / filename).resolve()
    try:
        target.relative_to(base_dir)
    except ValueError:
        return jsonify({"error": "invalid filename"}), 400

    if not target.exists() or not target.is_file():
        return jsonify({"error": "file not found"}), 404
    if target.suffix.lower() not in {".md", ".txt", ".csv", ".json"}:
        return jsonify({"error": "unsupported file type"}), 400

    return send_from_directory(base_dir, target.name, as_attachment=True)


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "5001"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)
