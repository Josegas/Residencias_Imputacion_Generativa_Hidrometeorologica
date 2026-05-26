"""
validate.py
===========
Verificación de integridad y consistencia del dataset final (Actividad 3.3)

Actividad  : 3.3 Dataset final procesado
Subtarea   : RES-107 (verificar integridad y consistencia)
Responsable: Data engineer / Data scientist
Entregable : validation_report.csv con resultado por estación + resumen en consola

Valida que processed_data/ cumpla los criterios de aceptación:
  ✓ Sin valores inconsistentes ni errores de formato
  ✓ Todas las variables escaladas dentro del rango esperado (definido en 3.2)
  ✓ Estructura de columnas compatible con el pipeline de ML
  ✓ Sin fechas duplicadas por estación
  ✓ Tipos de datos correctos (datetime, float)

Ejecutar DESPUÉS de pipeline.py.
"""

import logging
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DESDE YAML
# ─────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

with CONFIG_PATH.open("r", encoding="utf-8") as _f:
    CFG = yaml.safe_load(_f)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_p = CFG["paths"]
_o = CFG["output"]
_v = CFG["validation"]

OUTPUT_DIR  = PROJECT_ROOT.joinpath(*_p["output_subpath"])
REPORTS_DIR = PROJECT_ROOT.joinpath(*_p["reports_subpath"])
LOG_DIR     = PROJECT_ROOT.joinpath(*_p["log_subpath"])

INDEX_PROCESSED = OUTPUT_DIR / _o["index_filename"]
PARQUET_DIR     = OUTPUT_DIR / _o["parquet_subdir"]

VARIABLES        = CFG["variables"]
STATION_COL      = _o["station_col"]
SCALED_RANGES    = _v["scaled_ranges"]
MIN_ROWS         = _v["min_rows_per_station"]
MISSING_WARN_PCT = _v["max_missing_pct_warning"]

# ─────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────

LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

_log_file = LOG_DIR / _o["validation_log_filename"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_log_file, mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# CHECKS INDIVIDUALES
# ─────────────────────────────────────────────────────────────────────

def _check_schema(df: pd.DataFrame, station: str) -> list[str]:
    """Verifica que existan las columnas esperadas con tipos correctos."""
    issues = []

    if "date" not in df.columns:
        issues.append("columna 'date' ausente")
        return issues  # Sin date no se puede continuar

    # Tipo de date
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        issues.append(f"'date' no es datetime — dtype={df['date'].dtype}")

    # Variables presentes y numéricas
    for var in VARIABLES:
        if var not in df.columns:
            issues.append(f"columna '{var}' ausente")
        elif not pd.api.types.is_float_dtype(df[var]):
            issues.append(f"'{var}' no es float — dtype={df[var].dtype}")

    return issues


def _check_date_duplicates(df: pd.DataFrame) -> int:
    """Retorna el número de fechas duplicadas."""
    return int(df["date"].duplicated().sum())


def _check_date_nulls(df: pd.DataFrame) -> int:
    """Retorna el número de fechas nulas o inválidas."""
    return int(df["date"].isna().sum())


def _check_value_ranges(df: pd.DataFrame) -> dict[str, int]:
    """
    Por cada variable, cuenta valores que exceden el rango escalado esperado
    (sin contar NaN, que son valores faltantes legítimos).
    """
    out_of_range: dict[str, int] = {}
    for var in VARIABLES:
        if var not in df.columns:
            continue
        rng = SCALED_RANGES.get(var, {})
        lo  = rng.get("min", -np.inf)
        hi  = rng.get("max",  np.inf)
        series = df[var].dropna()
        n_bad  = int(((series < lo) | (series > hi)).sum())
        if n_bad > 0:
            out_of_range[var] = n_bad
    return out_of_range


def _check_missing(df: pd.DataFrame) -> dict[str, float]:
    """Calcula porcentaje de missing por variable."""
    result = {}
    for var in VARIABLES:
        if var in df.columns:
            result[var] = round(df[var].isna().mean() * 100, 2)
        else:
            result[var] = 100.0
    return result


def _check_min_rows(df: pd.DataFrame) -> bool:
    """Verifica que la estación tenga suficientes registros."""
    return len(df) >= MIN_ROWS


# ─────────────────────────────────────────────────────────────────────
# VALIDACIÓN POR ESTACIÓN
# ─────────────────────────────────────────────────────────────────────

def validate_station(station: str, parquet_path: Path) -> dict:
    """
    Ejecuta todos los checks sobre el archivo de una estación.
    Retorna un dict con los resultados para el reporte.
    """
    row: dict = {"station": station, "estado": "OK", "issues": ""}
    issues: list[str] = []

    # Existencia del archivo
    if not parquet_path.exists():
        row["estado"] = "ERROR"
        row["issues"] = f"Archivo no encontrado: {parquet_path}"
        return row

    # Carga
    try:
        df = pd.read_parquet(parquet_path)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    except Exception as exc:
        row["estado"] = "ERROR"
        row["issues"] = f"Error al leer parquet: {exc}"
        return row

    # ── Checks ────────────────────────────────────────────────────────
    schema_issues = _check_schema(df, station)
    issues.extend(schema_issues)

    n_dup_dates  = _check_date_duplicates(df)
    n_null_dates = _check_date_nulls(df)

    if n_dup_dates > 0:
        issues.append(f"fechas duplicadas={n_dup_dates}")
    if n_null_dates > 0:
        issues.append(f"fechas nulas/inválidas={n_null_dates}")

    out_of_range = _check_value_ranges(df)
    for var, n_bad in out_of_range.items():
        issues.append(f"fuera_de_rango_{var}={n_bad}")

    if not _check_min_rows(df):
        issues.append(f"filas_insuficientes={len(df)} (mín={MIN_ROWS})")

    missing_pct = _check_missing(df)
    for var, pct in missing_pct.items():
        if pct >= MISSING_WARN_PCT:
            issues.append(f"missing_alto_{var}={pct}%")

    # ── Métricas siempre presentes ────────────────────────────────────
    row["filas"]        = len(df)
    row["fecha_inicio"] = df["date"].min().strftime("%Y-%m-%d") if not df["date"].isna().all() else "N/A"
    row["fecha_fin"]    = df["date"].max().strftime("%Y-%m-%d") if not df["date"].isna().all() else "N/A"

    for var in VARIABLES:
        row[f"missing_pct_{var}"] = missing_pct.get(var, 100.0)
        if var in df.columns:
            row[f"min_{var}"] = round(df[var].min(skipna=True), 6)
            row[f"max_{var}"] = round(df[var].max(skipna=True), 6)
        else:
            row[f"min_{var}"] = np.nan
            row[f"max_{var}"] = np.nan

    row["fecha_duplicadas"]  = n_dup_dates
    row["fecha_nulas"]       = n_null_dates

    if issues:
        row["estado"] = "WARNING" if row["estado"] == "OK" else row["estado"]
        row["issues"] = " | ".join(issues)

    return row


# ─────────────────────────────────────────────────────────────────────
# VALIDACIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────────────

def run_validation() -> None:
    log.info("=" * 65)
    log.info("VALIDACIÓN 3.3 — Integridad del Dataset Final")
    log.info("Inicio : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 65)

    if not INDEX_PROCESSED.exists():
        raise FileNotFoundError(
            f"Índice de archivos procesados no encontrado: {INDEX_PROCESSED}\n"
            "Ejecuta pipeline.py antes de validate.py."
        )

    idx = pd.read_csv(INDEX_PROCESSED, dtype={"station": str})
    log.info("Estaciones a validar: %d", len(idx))

    report_rows: list[dict] = []
    n_ok      = 0
    n_warning = 0
    n_error   = 0

    for _, meta_row in idx.iterrows():
        station      = str(meta_row["station"])
        parquet_path = PARQUET_DIR / f"{_o['station_file_prefix']}{station}.parquet"

        result = validate_station(station, parquet_path)
        report_rows.append(result)

        estado = result["estado"]
        if estado == "OK":
            n_ok += 1
        elif estado == "WARNING":
            n_warning += 1
            log.warning("  [%s] %s", station, result["issues"])
        else:
            n_error += 1
            log.error("  [%s] %s", station, result["issues"])

    # ── Validación del dataset consolidado ────────────────────────────
    master_path = OUTPUT_DIR / _o["master_parquet_filename"]
    log.info("Validando dataset_final.parquet…")
    if master_path.exists():
        master = pd.read_parquet(master_path)
        log.info(
            "  dataset_final: %d filas | %d estaciones | columnas=%s",
            len(master), master[STATION_COL].nunique() if STATION_COL in master.columns else "?",
            list(master.columns),
        )
        # Verificar columnas requeridas
        expected_cols = {STATION_COL, "date"} | set(VARIABLES)
        missing_cols  = expected_cols - set(master.columns)
        if missing_cols:
            log.error("  dataset_final: columnas faltantes=%s", missing_cols)
        else:
            log.info("  dataset_final: esquema correcto")
    else:
        log.warning("  dataset_final.parquet no encontrado.")

    # ── Reporte ───────────────────────────────────────────────────────
    report_df   = pd.DataFrame(report_rows)
    report_path = REPORTS_DIR / _o["validation_report_filename"]
    report_df.to_csv(report_path, index=False)
    log.info("Reporte guardado: %s", report_path)

    # ── Resumen ───────────────────────────────────────────────────────
    log.info("=" * 65)
    log.info("RESUMEN DE VALIDACIÓN")
    log.info("  ✓ OK      : %d estaciones", n_ok)
    log.info("  ⚠ WARNING : %d estaciones", n_warning)
    log.info("  ✗ ERROR   : %d estaciones", n_error)
    log.info("  Total     : %d estaciones", len(report_rows))
    if n_error == 0 and n_warning == 0:
        log.info("  Criterios de aceptación: CUMPLIDOS")
    elif n_error == 0:
        log.info("  Criterios de aceptación: CUMPLIDOS CON ADVERTENCIAS")
    else:
        log.info("  Criterios de aceptación: NO CUMPLIDOS — revisa los errores")
    log.info("Fin     : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 65)


if __name__ == "__main__":
    run_validation()
