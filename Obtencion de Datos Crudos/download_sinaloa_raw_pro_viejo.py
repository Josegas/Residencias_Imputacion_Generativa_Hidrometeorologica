from pathlib import Path
import csv
import ssl
import socket
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# =========================
# CONFIG
# =========================
ESTADO = "sin"

BASE_URL = (
    "https://smn.conagua.gob.mx/tools/RESOURCES/Normales_Climatologicas/Diarios/"
    "{estado}/dia{clave}.txt"
)

USER_AGENT = "CONAGUA-Downloader/2.0"

# Si el script está en /scripts/descarga_conagua.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_ROOT = PROJECT_ROOT / "data" / "raw" / "conagua_smn" / f"estado={ESTADO}"
RAW_ROOT = DATA_ROOT / "fuente=normales_climatologicas" / "producto=diarios_txt"
LOG_DIR = DATA_ROOT / "_logs"
META_DIR = DATA_ROOT / "_meta"

MANIFEST_PATH = LOG_DIR / "download_manifest.csv"
RUNLOG_PATH = LOG_DIR / "download_run.log"
SUMMARY_PATH = LOG_DIR / "download_summary.csv"
STATIONS_META_PATH = META_DIR / "stations_sin.csv"

REQUEST_TIMEOUT = 25
RETRIES_PER_PASS = 3
SECOND_PASS_ENABLED = True
BASE_WAIT_SECONDS = 2.0
SLEEP_BETWEEN_STATIONS = 1.0
ALLOW_INSECURE_SSL = True
MAX_HTML_PREVIEW = 200

SSL_CONTEXT_DEFAULT = ssl.create_default_context()
SSL_CONTEXT_INSECURE = ssl._create_unverified_context()

socket.setdefaulttimeout(REQUEST_TIMEOUT)

# =========================
# STATIONS (Sinaloa)
# =========================
# (clave, nombre_estacion, municipio, situacion)
STATIONS = [
    (25001, "Acatitan", "San Ignacio", "Operando"),
    (25002, "Agua Caliente", "Choix", "Suspendida"),
    (25003, "Ahome", "Ahome", "Suspendida"),
    (25004, "Angostura (Esda)", "Angostura", "Suspendida"),
    (25005, "Bacubirito", "Sinaloa", "Suspendida"),
    (25006, "Badiraguato (Smn)", "Badiraguato", "Suspendida"),
    (25007, "Bamicori", "El Fuerte", "Suspendida"),
    (25008, "Topolobampo (Smn)", "Ahome", "Suspendida"),
    (25009, "Bocatoma Sufragio", "El Fuerte", "Suspendida"),
    (25010, "Culiacan (Caades)", "Culiacán", "Suspendida"),
    (25011, "Concordia (Cfe)", "Concordia", "Suspendida"),
    (25012, "Cosala", "Cosalá", "Suspendida"),
    (25013, "Corerepe", "Guasave", "Suspendida"),
    (25014, "Culiacan (Obs)", "Culiacán", "Operando"),
    (25015, "Culiacan (Dge)", "Culiacán", "Operando"),
    (25016, "Chapultepec Culiacan", "Culiacán", "Suspendida"),
    (25017, "Choix I (Dge)", "Choix", "Suspendida"),
    (25018, "Choix (Smn)", "Choix", "Suspendida"),
    (25019, "Choix Ii (Dge)", "Choix", "Suspendida"),
    (25020, "Choix (Aglch)", "Choix", "Suspendida"),
    (25021, "Dimas", "San Ignacio", "Operando"),
    (25022, "El Carrizo", "Ahome", "Suspendida"),
    (25023, "El Fuerte", "El Fuerte", "Suspendida"),
    (25024, "El Limon (Cfe)", "San Ignacio", "Suspendida"),
    (25025, "Presa Miguel Hidalgo Y Costilla", "El Fuerte", "Suspendida"),
    (25027, "El Nudo", "Guasave", "Suspendida"),
    (25028, "Elota (Cfe)", "Elota", "Suspendida"),
    (25029, "El Palmito (Cfe)", "Concordia", "Suspendida"),
    (25030, "El Playon", "Angostura", "Operando"),
    (25031, "El Quelite (Cfe)", "Mazatlán", "Suspendida"),
    (25032, "Presa Josefa Ortiz De Dominguez", "El Fuerte", "Suspendida"),
    (25033, "El Varejonal", "Badiraguato", "Operando"),
    (25035, "Francisco", "Ahome", "Suspendida"),
    (25036, "Guadalupe De Los Reyes", "Cosalá", "Operando"),
    (25037, "Guamuchil (Aarsp)", "Salvador Alvarado", "Operando"),
    (25038, "Guasave (Dge)", "Guasave", "Operando"),
    (25039, "Guasave (Smn)", "Guasave", "Suspendida"),
    (25040, "Guasave (Aarsp)", "Guasave", "Suspendida"),
    (25041, "Guatenipa", "Badiraguato", "Operando"),
    (25042, "Higuera De Zaragoza", "Ahome", "Suspendida"),
    (25043, "Huacapas (Cfe)", "Sinaloa", "Suspendida"),
    (25044, "Huites", "Choix", "Suspendida"),
    (25045, "Ixpalino", "San Ignacio", "Operando"),
    (25046, "Jaina", "Sinaloa", "Operando"),
    (25047, "Jocuixtita", "San Ignacio", "Suspendida"),
    (25048, "Juan Jose Rios", "Guasave", "Suspendida"),
    (25049, "La Concha", "Escuinapa", "Operando"),
    (25050, "La Cruz", "Elota", "Operando"),
    (25052, "La Noria (Cfe)", "Mazatlán", "Suspendida"),
    (25053, "La Tina", "El Fuerte", "Suspendida"),
    (25054, "La Vainilla (Cfe)", "Sinaloa", "Suspendida"),
    (25055, "Las Cañas", "El Fuerte", "Suspendida"),
    (25056, "Las Estacas", "El Fuerte", "Suspendida"),
    (25057, "Las Flores (Aarc)", "Culiacán", "Suspendida"),
    (25058, "Las Habitas", "Rosario", "Suspendida"),
    (25059, "Las Isabeles", "El Fuerte", "Suspendida"),
    (25060, "Los Mochis (Aarfs)", "Ahome", "Suspendida"),
    (25061, "Llano De Los Lopez", "El Fuerte", "Suspendida"),
    (25062, "Mazatlan (Obs)", "Mazatlán", "Operando"),
    (25063, "Mocorito (Aglm)", "Mocorito", "Suspendida"),
    (25064, "Mocorito (Dge)", "Mocorito", "Operando"),
    (25065, "Mochicahui", "El Fuerte", "Suspendida"),
    (25066, "Ocoroni (Cfe)", "Sinaloa", "Suspendida"),
    (25068, "Palo Dulce", "Choix", "Suspendida"),
    (25069, "Palos Blancos", "Culiacán", "Suspendida"),
    (25070, "Panuco", "Concordia", "Suspendida"),
    (25071, "Pericos", "Mocorito", "Suspendida"),
    (25072, "Piaxtla (Cfe)", "San Ignacio", "Suspendida"),
    (25073, "Plomosas", "Rosario", "Suspendida"),
    (25074, "Potrerillos", "Concordia", "Operando"),
    (25075, "Presa El Peñon", "Escuinapa", "Suspendida"),
    (25076, "Quila", "Culiacán", "Suspendida"),
    (25077, "Rosa Morada", "Mocorito", "Operando"),
    (25078, "Rosario", "Rosario", "Operando"),
    (25079, "Rosario (Aarb)", "Rosario", "Suspendida"),
    (25080, "Ruiz Cortinez", "Guasave", "Suspendida"),
    (25081, "Sanalona Ii", "Culiacán", "Operando"),
    (25082, "San Blas", "El Fuerte", "Suspendida"),
    (25083, "San Francisco Del Rio", "Choix", "Suspendida"),
    (25084, "San Ignacio", "San Ignacio", "Suspendida"),
    (25085, "San Jose De Gracia (Cfe)", "Sinaloa", "Suspendida"),
    (25086, "San Miguel Zapotitlan", "Ahome", "Suspendida"),
    (25087, "Santa Cruz De Ayala", "Cosalá", "Operando"),
    (25088, "Santa Rosa", "El Fuerte", "Suspendida"),
    (25089, "Sinaloa De Leyva (Aarso)", "Sinaloa", "Suspendida"),
    (25090, "Sinaloa De Leyva", "Sinaloa", "Suspendida"),
    (25091, "Siqueros (Cfe)", "Mazatlán", "Suspendida"),
    (25092, "Soyatita (Cfe)", "Badiraguato", "Suspendida"),
    (25093, "Surutato", "Badiraguato", "Operando"),
    (25094, "Tameapa", "Badiraguato", "Suspendida"),
    (25095, "Tapichahua (Cfe)", "Mazatlán", "Suspendida"),
    (25097, "Tecusiapa (Cfe)", "Badiraguato", "Suspendida"),
    (25098, "Topolobampo (Dge)", "Ahome", "Suspendida"),
    (25099, "Topolobampo (Cfe)", "Ahome", "Suspendida"),
    (25100, "Yecorato (Cfe)", "Choix", "Suspendida"),
    (25101, "Soquititan (Cfe)", "Elota", "Suspendida"),
    (25102, "Escuela De Biologia (Uas)", "Culiacán", "Suspendida"),
    (25103, "El Caiman", "Sinaloa", "Operando"),
    (25105, "El Mezquite", "Sinaloa", "Operando"),
    (25106, "El Tigre", "Navolato", "Operando"),
    (25107, "Saca De Agua", "Badiraguato", "Operando"),
    (25110, "Badiraguato (Dge)", "Badiraguato", "Operando"),
    (25111, "Badiraguato (Aglb)", "Badiraguato", "Suspendida"),
    (25112, "Concordia (Caades)", "Concordia", "Suspendida"),
    (25113, "Cosala (Aglc)", "Cosalá", "Suspendida"),
    (25114, "El Fuerte (Aarfm)", "El Fuerte", "Suspendida"),
    (25115, "Guamuchil (Dge)", "Salvador Alvarado", "Suspendida"),
    (25116, "Los Mochis", "Ahome", "Suspendida"),
    (25117, "Mocorito (Smn)", "Mocorito", "Suspendida"),
    (25118, "San Ignacio (Cfe)", "San Ignacio", "Suspendida"),
    (25119, "Siqueros", "Mazatlán", "Operando"),
    (25121, "Vinoramas", "Culiacán", "Operando"),
    (25122, "Los Alamos", "El Fuerte", "Suspendida"),
    (25123, "Abuya (Ffcc)", "Culiacán", "Suspendida"),
    (25124, "Bamoa (Ffcc)", "Guasave", "Suspendida"),
    (25125, "Caimanero (Ffcc)", "Mocorito", "Suspendida"),
    (25128, "Dimas (Ffcc)", "San Ignacio", "Suspendida"),
    (25129, "El Dorado (Ffcc)", "Guasave", "Suspendida"),
    (25130, "Escuinapa (Ffcc)", "Escuinapa", "Suspendida"),
    (25131, "Guamuchil (Ffcc)", "Salvador Alvarado", "Suspendida"),
    (25132, "La Cruz (Ffcc)", "Elota", "Suspendida"),
    (25133, "Leon Fonseca (Ffcc)", "Guasave", "Suspendida"),
    (25134, "Marmol (Ffcc)", "Mazatlán", "Suspendida"),
    (25135, "Mazatlan (Ffcc)", "Mazatlán", "Suspendida"),
    (25137, "Naranjo (Ffcc)", "Sinaloa", "Suspendida"),
    (25138, "Presidio (Ffcc)", "Mazatlán", "Suspendida"),
    (25139, "Quila (Ffcc)", "Culiacán", "Suspendida"),
    (25142, "San Blas (Ffcc)", "El Fuerte", "Suspendida"),
    (25143, "Sufragio (Ffcc)", "El Fuerte", "Suspendida"),
    (25144, "Ceferino Paredes (Ffcc)", "Sinaloa", "Suspendida"),
    (25148, "E.T.A. 057 Guasave", "Guasave", "Suspendida"),
    (25149, "Las Higueras", "Rosario", "Suspendida"),
    (25150, "Las Tortugas", "Rosario", "Operando"),
    (25151, "Chavez Talamantes", "Ahome", "Suspendida"),
    (25153, "Naranjo", "Sinaloa", "Operando"),
    (25155, "Choix (Obs)", "Choix", "Operando"),
    (25158, "El Palmar De Los Sepulveda", "Sinaloa", "Operando"),
    (25159, "Lateral Cincuenta Y Seis", "Culiacán", "Suspendida"),
    (25160, "Espinoza", "Navolato", "Suspendida"),
    (25161, "El Dorado", "Culiacán", "Operando"),
    (25162, "La Curva", "Culiacán", "Suspendida"),
    (25163, "Andrew Weiss", "Culiacán", "Suspendida"),
    (25164, "Alto De Culiacancito", "Culiacán", "Operando"),
    (25165, "Batauto", "Navolato", "Suspendida"),
    (25166, "Costa Rica", "Culiacán", "Suspendida"),
    (25167, "San Lorenzo", "Culiacán", "Suspendida"),
    (25168, "Pitayal", "Navolato", "Suspendida"),
    (25169, "Sataya", "Navolato", "Suspendida"),
    (25170, "El Tamarindo", "Culiacán", "Operando"),
    (25171, "Navolato", "Navolato", "Operando"),
    (25172, "San Joaquin", "Sinaloa", "Operando"),
    (25173, "Altata", "Navolato", "Operando"),
    (25174, "Hoyancos", "El Fuerte", "Suspendida"),
    (25175, "Ocoroni", "Sinaloa", "Suspendida"),
    (25176, "El Quemado", "Mazatlán", "Operando"),
    (25177, "Santiago De Los Caballeros", "Badiraguato", "Suspendida"),
    (25178, "Zopilote", "Guasave", "Operando"),
    (25179, "Lateral Diez", "Culiacán", "Suspendida"),
    (25180, "Coacuana", "Sinaloa", "Suspendida"),
    (25181, "Nuestra Señora", "Cosalá", "Suspendida"),
    (25183, "Comedero", "Cosalá", "Operando"),
    (25184, "Bacurato", "Sinaloa", "Suspendida"),
    (25185, "Olas Altas", "Ahome", "Suspendida"),
    (25186, "Otatitan", "Rosario", "Operando"),
    (25188, "Los Hornos", "Sinaloa", "Suspendida"),
    (25190, "Tecuxiapa", "Badiraguato", "Suspendida"),
    (25191, "Mazatlan (Cfe)", "Mazatlán", "Suspendida"),
    (25192, "Jose Aceves Pozos (Cfe)", "Mazatlán", "Suspendida"),
]

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
    with RUNLOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def save_stations_meta():
    with STATIONS_META_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clave", "nombre_estacion", "municipio", "situacion", "estado"])
        for clave, nombre, municipio, situacion in STATIONS:
            w.writerow([clave, nombre, municipio, situacion, ESTADO])


def init_manifest():
    if not MANIFEST_PATH.exists():
        with MANIFEST_PATH.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "timestamp",
                "pass_no",
                "estado",
                "clave",
                "station_name",
                "municipio",
                "situacion",
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
    with MANIFEST_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            row["timestamp"],
            row["pass_no"],
            row["estado"],
            row["clave"],
            row["station_name"],
            row["municipio"],
            row["situacion"],
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
        "Accept": "text/plain,*/*",
        "Connection": "close",
    }
    return Request(url, headers=headers, method="GET")


def _download_bytes(url: str, context):
    req = _build_request(url)
    with urlopen(req, timeout=REQUEST_TIMEOUT, context=context) as response:
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
    modes = [("default", SSL_CONTEXT_DEFAULT)]
    if ALLOW_INSECURE_SSL:
        modes.append(("insecure", SSL_CONTEXT_INSECURE))
    return modes


def download_one(clave: int, pass_no: int):
    url = BASE_URL.format(estado=ESTADO, clave=clave)
    file_path = RAW_ROOT / f"dia{clave}.txt"
    tmp_path = RAW_ROOT / f"dia{clave}.txt.part"

    if file_path.exists() and file_path.stat().st_size > 0:
        return {
            "timestamp": datetime.now().isoformat(),
            "pass_no": pass_no,
            "estado": ESTADO,
            "status": "SKIP_EXISTS",
            "error_type": "",
            "error_detail": "",
            "url": url,
            "file": str(file_path),
            "file_size_bytes": file_path.stat().st_size,
            "ssl_mode": "none",
            "attempt": 0,
            "duration_ms": 0,
        }

    last_error_type = "ERROR"
    last_error_detail = ""
    last_ssl_mode = "default"
    start_total = time.perf_counter()

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
                    "timestamp": datetime.now().isoformat(),
                    "pass_no": pass_no,
                    "estado": ESTADO,
                    "status": "OK",
                    "error_type": "",
                    "error_detail": "",
                    "url": url,
                    "file": str(file_path),
                    "file_size_bytes": file_path.stat().st_size,
                    "ssl_mode": ssl_mode,
                    "attempt": attempt,
                    "duration_ms": duration_ms,
                }

            except HTTPError as e:
                last_error_type = _error_type_from_exception(e)
                last_error_detail = str(e)
                _safe_remove(tmp_path)

                if not is_temporary_status(last_error_type):
                    duration_ms = int((time.perf_counter() - start_total) * 1000)
                    return {
                        "timestamp": datetime.now().isoformat(),
                        "pass_no": pass_no,
                        "estado": ESTADO,
                        "status": last_error_type,
                        "error_type": last_error_type,
                        "error_detail": last_error_detail,
                        "url": url,
                        "file": str(file_path),
                        "file_size_bytes": 0,
                        "ssl_mode": ssl_mode,
                        "attempt": attempt,
                        "duration_ms": duration_ms,
                    }

            except Exception as e:
                last_error_type = _error_type_from_exception(e)
                last_error_detail = f"{type(e).__name__}: {e}"
                _safe_remove(tmp_path)

        if attempt < RETRIES_PER_PASS:
            time.sleep(BASE_WAIT_SECONDS * attempt)

    _safe_remove(tmp_path)
    duration_ms = int((time.perf_counter() - start_total) * 1000)

    return {
        "timestamp": datetime.now().isoformat(),
        "pass_no": pass_no,
        "estado": ESTADO,
        "status": last_error_type,
        "error_type": last_error_type,
        "error_detail": last_error_detail,
        "url": url,
        "file": str(file_path),
        "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
        "ssl_mode": last_ssl_mode,
        "attempt": RETRIES_PER_PASS,
        "duration_ms": duration_ms,
    }


def process_stations(stations_subset, pass_no: int):
    results = []

    for clave, nombre, municipio, situacion in stations_subset:
        result = download_one(clave, pass_no)
        result["clave"] = clave
        result["station_name"] = nombre
        result["municipio"] = municipio
        result["situacion"] = situacion

        append_manifest(result)
        results.append(result)

        if result["status"] == "OK":
            write_runlog(
                f"OK   P{pass_no} {clave} | {nombre} | ssl={result['ssl_mode']} | "
                f"intento={result['attempt']} | bytes={result['file_size_bytes']}"
            )
        elif result["status"] == "SKIP_EXISTS":
            write_runlog(f"SKIP P{pass_no} {clave} | {nombre} (ya existe)")
        else:
            write_runlog(
                f"FAIL P{pass_no} {clave} | {nombre} [{result['status']}] | "
                f"ssl={result['ssl_mode']} | intento={result['attempt']} | "
                f"error={result['error_detail']}"
            )

        time.sleep(SLEEP_BETWEEN_STATIONS)

    return results


def build_second_pass_subset(first_pass_results):
    failed_keys = {
        r["clave"] for r in first_pass_results if is_temporary_status(r["status"])
    }
    return [item for item in STATIONS if item[0] in failed_keys]


def summarize(final_results):
    total = len(STATIONS)
    ok = sum(1 for r in final_results if r["status"] == "OK")
    skip = sum(1 for r in final_results if r["status"] == "SKIP_EXISTS")
    fail = sum(1 for r in final_results if r["status"] not in ("OK", "SKIP_EXISTS"))
    temp_fail = sum(1 for r in final_results if is_temporary_status(r["status"]))
    definite_fail = sum(
        1 for r in final_results
        if r["status"] not in ("OK", "SKIP_EXISTS") and not is_temporary_status(r["status"])
    )
    coverage = round(((ok + skip) / total) * 100, 2) if total else 0.0

    summary_rows = [
        ("estado", ESTADO),
        ("project_root", str(PROJECT_ROOT)),
        ("total_stations", total),
        ("ok", ok),
        ("skip_exists", skip),
        ("fail_total", fail),
        ("fail_temporary", temp_fail),
        ("fail_definitive", definite_fail),
        ("coverage_percent", coverage),
        ("manifest_path", str(MANIFEST_PATH)),
        ("summary_path", str(SUMMARY_PATH)),
        ("stations_meta_path", str(STATIONS_META_PATH)),
    ]
    write_summary(summary_rows)
    return summary_rows


def main():
    ensure_dirs()
    save_stations_meta()
    init_manifest()

    write_runlog(f"INICIO | Estado={ESTADO} | Total estaciones={len(STATIONS)}")
    write_runlog(f"PROJECT_ROOT={PROJECT_ROOT}")
    write_runlog(
        f"CONFIG | timeout={REQUEST_TIMEOUT}s | retries={RETRIES_PER_PASS} | "
        f"sleep_between={SLEEP_BETWEEN_STATIONS}s | second_pass={SECOND_PASS_ENABLED} | "
        f"allow_insecure_ssl={ALLOW_INSECURE_SSL}"
    )

    first_pass_results = process_stations(STATIONS, pass_no=1)
    final_results_by_key = {r["clave"]: r for r in first_pass_results}

    if SECOND_PASS_ENABLED:
        second_subset = build_second_pass_subset(first_pass_results)
        write_runlog(f"SEGUNDA_PASADA | estaciones_temporales={len(second_subset)}")

        if second_subset:
            second_pass_results = process_stations(second_subset, pass_no=2)
            for r in second_pass_results:
                final_results_by_key[r["clave"]] = r

    final_results = list(final_results_by_key.values())
    summary_rows = summarize(final_results)

    write_runlog("FIN")
    for key, value in summary_rows:
        write_runlog(f"SUMMARY | {key}={value}")


if __name__ == "__main__":
    main()