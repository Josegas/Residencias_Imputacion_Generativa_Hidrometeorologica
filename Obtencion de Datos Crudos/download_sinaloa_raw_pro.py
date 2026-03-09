import os
import csv
import time
import urllib.request
from urllib.error import HTTPError, URLError
from datetime import datetime

# =========================
# CONFIG
# =========================
ESTADO = "sin"
BASE_URL = (
    "https://smn.conagua.gob.mx/tools/RESOURCES/Normales_Climatologicas/Diarios/"
    "{estado}/dia{clave}.txt"
)

# Elegir Ruta de la carpeta Raiz
PROJECT_ROOT = r"C:\Users\Jose Garcia\Documents\10_SEMESTRE_TEC\RESIDENCIAS\Reconstruccion_de_Base_de_Datos_Nuestro"

RAW_ROOT = os.path.join(
    PROJECT_ROOT,
    "data", "raw", "conagua_smn", f"estado={ESTADO}",
    "fuente=normales_climatologicas", "producto=diarios_txt"
)

LOG_DIR = os.path.join(
    PROJECT_ROOT,
    "data", "raw", "conagua_smn", f"estado={ESTADO}", "_logs"
)

META_DIR = os.path.join(
    PROJECT_ROOT,
    "data", "raw", "conagua_smn", f"estado={ESTADO}", "_meta"
)

MANIFEST_PATH = os.path.join(LOG_DIR, "download_manifest.csv")
RUNLOG_PATH = os.path.join(LOG_DIR, "download_run.log")
STATIONS_META_PATH = os.path.join(META_DIR, "stations_sin.csv")

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
    (25164, "Alto De Culiacancito", "Culiacán", "Suspendida"),
    (25165, "Batauto", "Navolato", "Suspendida"),
    (25166, "Costa Rica", "Culiacán", "Suspendida"),
    (25167, "San Lorenzo", "Culiacán", "Suspendida"),
    (25168, "Pitayal", "Navolato", "Suspendida"),
    (25169, "Sataya", "Navolato", "Suspendida"),
    (25170, "El Tamarindo", "Culiacán", "Suspendida"),
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
    os.makedirs(RAW_ROOT, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(META_DIR, exist_ok=True)


def write_runlog(line: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{ts}] {line}"
    print(msg)
    with open(RUNLOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def save_stations_meta():
    with open(STATIONS_META_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clave", "nombre_estacion",
                   "municipio", "situacion", "estado"])
        for clave, nombre, municipio, situacion in STATIONS:
            w.writerow([clave, nombre, municipio, situacion, ESTADO])


def init_manifest():
    if not os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "estado", "clave",
                       "status", "url", "file", "error"])


def download_one(clave: int):
    url = BASE_URL.format(estado=ESTADO, clave=clave)
    file_path = os.path.join(RAW_ROOT, f"dia{clave}.txt")

    # Evitar re-descargar
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return "SKIP_EXISTS", url, file_path, ""

    try:
        urllib.request.urlretrieve(url, file_path)
        return "OK", url, file_path, ""
    except HTTPError as e:
        return f"HTTP_{e.code}", url, file_path, str(e)
    except URLError as e:
        return "URL_ERROR", url, file_path, str(e.reason)
    except Exception as e:
        return "ERROR", url, file_path, f"{type(e).__name__}: {e}"


def append_manifest(clave: int, status: str, url: str, file_path: str, err: str):
    with open(MANIFEST_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([datetime.now().isoformat(), ESTADO,
                   clave, status, url, file_path, err])

# =========================
# MAIN
# =========================


def main():
    ensure_dirs()
    save_stations_meta()
    init_manifest()

    write_runlog(
        f"INICIO | Estado={ESTADO} | Total estaciones={len(STATIONS)}")
    write_runlog(f"RAW_ROOT={RAW_ROOT}")

    ok = skip = fail = 0

    for clave, nombre, municipio, situacion in STATIONS:
        status, url, file_path, err = download_one(clave)

        if status == "OK":
            ok += 1
            write_runlog(f"OK   {clave} | {nombre} -> {file_path}")
        elif status == "SKIP_EXISTS":
            skip += 1
            write_runlog(f"SKIP {clave} | {nombre} (ya existe)")
        else:
            fail += 1
            write_runlog(f"FAIL {clave} | {nombre} [{status}]")

        append_manifest(clave, status, url, file_path, err)

        time.sleep(0.2)  # amable con el servidor

    write_runlog("FIN")
    write_runlog(f"RESUMEN | OK={ok} | SKIP={skip} | FAIL={fail}")
    write_runlog(f"Manifest: {MANIFEST_PATH}")
    write_runlog(f"Meta estaciones: {STATIONS_META_PATH}")


if __name__ == "__main__":
    main()


