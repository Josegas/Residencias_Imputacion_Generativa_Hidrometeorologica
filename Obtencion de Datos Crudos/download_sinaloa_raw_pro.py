from pathlib import Path
import csv
import ssl
import socket
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
 
# =========================
# CONFIG
# =========================
ESTADO = "sin"
 
BASE_URL = (
    "https://smn.conagua.gob.mx/tools/RESOURCES/Normales_Climatologicas/Diarios/"
    "{estado}/dia{clave}.txt"
)
 
USER_AGENT = "CONAGUA-Downloader/2.0"
 
# Si el script está en /Obtencion de Datos Crudos/, usa .parent.parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent
 
DATA_ROOT = PROJECT_ROOT / "data" / "raw" / "conagua_smn" / f"estado={ESTADO}"
RAW_ROOT  = DATA_ROOT / "fuente=normales_climatologicas" / "producto=diarios_txt"
LOG_DIR   = DATA_ROOT / "_logs"
META_DIR  = DATA_ROOT / "_meta"
 
MANIFEST_PATH      = LOG_DIR / "download_manifest.csv"
RUNLOG_PATH        = LOG_DIR / "download_run.log"
SUMMARY_PATH       = LOG_DIR / "download_summary.csv"
STATIONS_META_PATH = META_DIR / "stations_sin.csv"
 
# =========================
# DESCUBRIMIENTO AUTOMÁTICO
# =========================
# Rango de claves a explorar para Sinaloa (25001–25999).
# El script intentará descargar cada clave del rango.
# Las claves sin archivo en CONAGUA devuelven HTTP 404 y se
# descartan automáticamente. Las claves con archivo válido se
# guardan y quedan disponibles para ejecuciones futuras.
# Si CONAGUA agrega nuevas estaciones dentro del rango, se
# descubrirán en la próxima ejecución completa.
STATION_RANGE_START = 25001
STATION_RANGE_END   = 25300   

# =========================
# PARÁMETROS DE CONEXIÓN
# =========================
REQUEST_TIMEOUT      = 25
RETRIES_PER_PASS      = 3
SLEEP_BETWEEN_CLAVES  = 0.2   # pausa entre requests dentro de cada hilo
MAX_WORKERS           = 10    # descargas simultáneas (no subir de 20)
MAX_HTML_PREVIEW      = 200
 
SSL_CONTEXT_INSECURE = ssl._create_unverified_context()
 
# Locks para escritura segura desde múltiples hilos
_manifest_lock = threading.Lock()
_runlog_lock   = threading.Lock()
 
 
# =========================
# HELPERS
# =========================
def ensure_dirs():
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)
 
 
def write_runlog(line: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{ts}] {line}"
    print(msg)
    with _runlog_lock:
        with RUNLOG_PATH.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
 
 
def save_stations_meta(discovered: list[dict]):
    """Guarda el catálogo de estaciones descubiertas en esta ejecución."""
    with STATIONS_META_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clave", "estado", "status", "file_size_bytes"])
        for s in discovered:
            w.writerow([s["clave"], ESTADO, s["status"], s["file_size_bytes"]])
 
 
def init_manifest():
    if not MANIFEST_PATH.exists():
        with MANIFEST_PATH.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "timestamp",
                "pass_no",
                "estado",
                "clave",
                "status",
                "error_type",
                "error_detail",
                "url",
                "file",
                "file_size_bytes",
                "ssl_mode",
                "attempt",
                "duration_ms",
            ])
 
 
def append_manifest(row: dict):
    with _manifest_lock:
        with MANIFEST_PATH.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                row["timestamp"],
                row["pass_no"],
                row["estado"],
                row["clave"],
                row["status"],
                row["error_type"],
                row["error_detail"],
                row["url"],
                row["file"],
                row["file_size_bytes"],
                row["ssl_mode"],
                row["attempt"],
                row["duration_ms"],
            ])
 
 
def write_summary(summary_rows):
    with SUMMARY_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for key, value in summary_rows:
            w.writerow([key, value])
 
 
def _build_request(url: str) -> Request:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept":     "text/plain,*/*",
        "Connection": "close",
    }
    return Request(url, headers=headers, method="GET")
 
 
def _download_bytes(url: str, context, timeout: int = None):
    req = _build_request(url)
    t = timeout if timeout is not None else REQUEST_TIMEOUT
    with urlopen(req, timeout=t, context=context) as response:
        return response.read()
 
 
def _validate_content(content: bytes):
    if not content:
        raise ValueError("Respuesta vacía")
    sample = content[:2000].decode("latin-1", errors="ignore").lower()
    if "<html" in sample or "<!doctype html" in sample:
        preview = sample[:MAX_HTML_PREVIEW].replace("\n", " ").replace("\r", " ")
        raise ValueError(f"Respuesta HTML inesperada: {preview}")
 
 
def _safe_remove(path: Path):
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
 
 
def _error_type_from_exception(exc) -> str:
    if isinstance(exc, HTTPError):
        return f"HTTP_{exc.code}"
    if isinstance(exc, ssl.SSLError):
        return "SSL_ERROR"
    if isinstance(exc, socket.timeout):
        return "TIMEOUT"
    if isinstance(exc, URLError):
        return "URL_ERROR"
    if isinstance(exc, ValueError):
        return "CONTENT_ERROR"
    return "ERROR"
 
 
def is_temporary_status(status: str) -> bool:
    return status in {
        "SSL_ERROR",
        "TIMEOUT",
        "URL_ERROR",
        "HTTP_500",
        "HTTP_502",
        "HTTP_503",
        "HTTP_504",
    }
 
 
def _ssl_modes():
    # CONAGUA no soporta SSL verificado — va directo a insecure
    return [("insecure", SSL_CONTEXT_INSECURE)]
 
 
# =========================
# DESCARGA DE UNA CLAVE
# =========================
def download_one(clave: int, pass_no: int) -> dict:
    url       = BASE_URL.format(estado=ESTADO, clave=clave)
    file_path = RAW_ROOT / f"dia{clave}.txt"
    tmp_path  = RAW_ROOT / f"dia{clave}.txt.part"
 
    # Archivo ya existe con contenido — no volver a descargar
    if file_path.exists() and file_path.stat().st_size > 0:
        return {
            "timestamp":       datetime.now().isoformat(),
            "pass_no":         pass_no,
            "estado":          ESTADO,
            "clave":           clave,
            "status":          "SKIP_EXISTS",
            "error_type":      "",
            "error_detail":    "",
            "url":             url,
            "file":            str(file_path),
            "file_size_bytes": file_path.stat().st_size,
            "ssl_mode":        "none",
            "attempt":         0,
            "duration_ms":     0,
        }
 
    last_error_type   = "ERROR"
    last_error_detail = ""
    last_ssl_mode     = "default"
    start_total       = time.perf_counter()
 
    for attempt in range(1, RETRIES_PER_PASS + 1):
        for ssl_mode, ssl_context in _ssl_modes():
            last_ssl_mode = ssl_mode
            _safe_remove(tmp_path)
 
            try:
                content = _download_bytes(url, ssl_context)
                _validate_content(content)
 
                with tmp_path.open("wb") as f:
                    f.write(content)
 
                if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                    raise ValueError("Archivo temporal vacío")
 
                tmp_path.replace(file_path)
 
                duration_ms = int((time.perf_counter() - start_total) * 1000)
                return {
                    "timestamp":       datetime.now().isoformat(),
                    "pass_no":         pass_no,
                    "estado":          ESTADO,
                    "clave":           clave,
                    "status":          "OK",
                    "error_type":      "",
                    "error_detail":    "",
                    "url":             url,
                    "file":            str(file_path),
                    "file_size_bytes": file_path.stat().st_size,
                    "ssl_mode":        ssl_mode,
                    "attempt":         attempt,
                    "duration_ms":     duration_ms,
                }
 
            except HTTPError as e:
                last_error_type   = _error_type_from_exception(e)
                last_error_detail = str(e)
                _safe_remove(tmp_path)
 
                # Error definitivo (ej. 404) — no reintentar
                if not is_temporary_status(last_error_type):
                    duration_ms = int((time.perf_counter() - start_total) * 1000)
                    return {
                        "timestamp":       datetime.now().isoformat(),
                        "pass_no":         pass_no,
                        "estado":          ESTADO,
                        "clave":           clave,
                        "status":          last_error_type,
                        "error_type":      last_error_type,
                        "error_detail":    last_error_detail,
                        "url":             url,
                        "file":            str(file_path),
                        "file_size_bytes": 0,
                        "ssl_mode":        ssl_mode,
                        "attempt":         attempt,
                        "duration_ms":     duration_ms,
                    }
 
            except Exception as e:
                last_error_type   = _error_type_from_exception(e)
                last_error_detail = f"{type(e).__name__}: {e}"
                _safe_remove(tmp_path)
 
        if attempt < RETRIES_PER_PASS:
            time.sleep(2.0 * attempt)
 
    _safe_remove(tmp_path)
    duration_ms = int((time.perf_counter() - start_total) * 1000)
 
    return {
        "timestamp":       datetime.now().isoformat(),
        "pass_no":         pass_no,
        "estado":          ESTADO,
        "clave":           clave,
        "status":          last_error_type,
        "error_type":      last_error_type,
        "error_detail":    last_error_detail,
        "url":             url,
        "file":            str(file_path),
        "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
        "ssl_mode":        last_ssl_mode,
        "attempt":         RETRIES_PER_PASS,
        "duration_ms":     duration_ms,
    }
 
 
# =========================
# PROCESAMIENTO POR RANGO
# =========================
def _download_and_log(clave: int, pass_no: int) -> dict:
    """Descarga una clave y registra el resultado. Diseñado para ejecutarse en un hilo."""
    result = download_one(clave, pass_no)
    append_manifest(result)
 
    status = result["status"]
    if status == "OK":
        write_runlog(
            f"OK   P{pass_no} {clave} | ssl={result['ssl_mode']} | "
            f"intento={result['attempt']} | bytes={result['file_size_bytes']}"
        )
    elif status == "SKIP_EXISTS":
        write_runlog(f"SKIP P{pass_no} {clave} (ya existe)")
    elif status != "HTTP_404":
        write_runlog(
            f"FAIL P{pass_no} {clave} [{status}] | "
            f"ssl={result['ssl_mode']} | intento={result['attempt']} | "
            f"error={result['error_detail']}"
        )
 
    time.sleep(SLEEP_BETWEEN_CLAVES)
    return result
 
 
def process_range(claves: list[int], pass_no: int) -> list[dict]:
    """
    Descarga las claves en paralelo usando MAX_WORKERS hilos simultáneos.
    Los HTTP 404 no se imprimen en consola pero quedan en el manifiesto.
    """
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_download_and_log, clave, pass_no): clave for clave in claves}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                clave = futures[future]
                write_runlog(f"ERROR inesperado P{pass_no} {clave}: {e}")
    return results
 
 
 
def summarize(final_results: list[dict]) -> list[tuple]:
    total        = STATION_RANGE_END - STATION_RANGE_START + 1
    ok           = sum(1 for r in final_results if r["status"] == "OK")
    skip         = sum(1 for r in final_results if r["status"] == "SKIP_EXISTS")
    not_found    = sum(1 for r in final_results if r["status"] == "HTTP_404")
    fail         = sum(1 for r in final_results if r["status"] not in ("OK", "SKIP_EXISTS", "HTTP_404"))
    discovered   = ok + skip   # claves con archivo válido
    coverage     = round((discovered / total) * 100, 2) if total else 0.0
 
    summary_rows = [
        ("estado",              ESTADO),
        ("project_root",        str(PROJECT_ROOT)),
        ("range_start",         STATION_RANGE_START),
        ("range_end",           STATION_RANGE_END),
        ("claves_escaneadas",   total),
        ("ok",                  ok),
        ("skip_exists",         skip),
        ("discovered",          discovered),
        ("not_found_404",       not_found),
        ("fail",                fail),
        ("coverage_percent",    coverage),
        ("manifest_path",       str(MANIFEST_PATH)),
        ("summary_path",        str(SUMMARY_PATH)),
        ("stations_meta_path",  str(STATIONS_META_PATH)),
    ]
    write_summary(summary_rows)
    return summary_rows
 
 
# =========================
# MAIN
# =========================
def main():
    ensure_dirs()
    init_manifest()
 
    all_claves = list(range(STATION_RANGE_START, STATION_RANGE_END + 1))
 
    write_runlog(
        f"INICIO | Estado={ESTADO} | "
        f"Rango={STATION_RANGE_START}–{STATION_RANGE_END} | "
        f"Claves a escanear={len(all_claves)}"
    )
    write_runlog(f"PROJECT_ROOT={PROJECT_ROOT}")
    write_runlog(
        f"CONFIG | timeout={REQUEST_TIMEOUT}s | retries={RETRIES_PER_PASS} | "
        f"sleep_between={SLEEP_BETWEEN_CLAVES}s"
    )
 
    # Primera pasada: escaneo completo del rango
    final_results = process_range(all_claves, pass_no=1)
 
 
 
    # Guardar catálogo de estaciones descubiertas (solo las que tienen archivo)
    discovered = [
        r for r in final_results
        if r["status"] in ("OK", "SKIP_EXISTS")
    ]
    save_stations_meta(discovered)
 
    summary_rows = summarize(final_results)
 
    write_runlog("FIN")
    for key, value in summary_rows:
        write_runlog(f"SUMMARY | {key}={value}")
 
 
if __name__ == "__main__":
    main()


