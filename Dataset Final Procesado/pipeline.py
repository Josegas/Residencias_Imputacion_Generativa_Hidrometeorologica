"""
pipeline.py
===========
Pipeline unificado — Dataset Final Procesado (Actividad 3.3)

Actividad  : 3.3 Dataset final procesado
Subtareas  : RES-105 (consolidar pipeline), RES-106 (exportar CSV/Parquet)
Responsable: Data engineer / Data scientist
Entregable : processed_data/ con archivos por estación + dataset_final + índice + reporte

Integra las transformaciones de limpieza (3.1) y escalamiento (3.2) en un
único flujo reproducible y exporta el dataset final a processed_data/ en
formatos CSV y Parquet, compatibles con el pipeline de ML.

Pipeline
--------
1. Carga _index_scaled.csv (salida de normalize.py, etapa 3.2)
2. Por cada estación: fusiona todas las particiones anuales en un DataFrame
   wide (filas=fechas, columnas=variables escaladas)
3. Exporta archivo por estación en processed_data/parquet/ y processed_data/csv/
4. Genera dataset_final.parquet / dataset_final.csv (todas las estaciones)
5. Genera _index_processed.csv y pipeline_report.csv

Todos los parámetros se configuran en config.yaml.
"""

import argparse
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

SCALED_DIR   = PROJECT_ROOT.joinpath(*_p["index_scaled_subpath"])
INDEX_SCALED = SCALED_DIR / _p["index_scaled_filename"]
OUTPUT_DIR   = PROJECT_ROOT.joinpath(*_p["output_subpath"])
REPORTS_DIR  = PROJECT_ROOT.joinpath(*_p["reports_subpath"])
LOG_DIR      = PROJECT_ROOT.joinpath(*_p["log_subpath"])

PARQUET_DIR  = OUTPUT_DIR / _o["parquet_subdir"]
CSV_DIR      = OUTPUT_DIR / _o["csv_subdir"]

VARIABLES      = CFG["variables"]
STATION_ZFILL  = _o["station_id_zfill"]
VALUE_COL      = _o["value_column"]
STATION_COL    = _o["station_col"]
PROGRESS_EVERY = _o["progress_log_interval"]
SEG_DATA       = CFG["path_segments"]["data"]

# ─────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────

LOG_DIR.mkdir(parents=True, exist_ok=True)
PARQUET_DIR.mkdir(parents=True, exist_ok=True)
CSV_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

_log_file = LOG_DIR / _o["pipeline_log_filename"]

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
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _resolve_path(raw_path: str) -> Path:
    """
    Resuelve una ruta desde el índice escalado.
    normalize.py guarda rutas absolutas; si el archivo no existe en la
    ruta original (p.e. el proyecto fue movido), busca el segmento
    'data/' y lo reconstruye desde PROJECT_ROOT — mismo patrón que
    cleaning.py y normalize.py.
    """
    p = Path(raw_path)
    if p.exists():
        return p
    parts = p.parts
    try:
        idx = next(i for i, part in enumerate(parts) if part == SEG_DATA)
        return PROJECT_ROOT / Path(*parts[idx:])
    except StopIteration:
        return p


def _load_index() -> pd.DataFrame:
    """Carga y valida el índice de particiones escaladas."""
    if not INDEX_SCALED.exists():
        raise FileNotFoundError(
            f"Índice escalado no encontrado: {INDEX_SCALED}\n"
            "Ejecuta Preprocesamiento/normalize.py antes de correr este script."
        )
    idx = pd.read_csv(INDEX_SCALED, dtype={"station": str})
    required = {"station", "year", "variable", "path_parquet"}
    missing = required - set(idx.columns)
    if missing:
        raise ValueError(f"_index_scaled.csv no tiene columnas requeridas: {missing}")
    log.info(
        "Índice cargado: %d particiones | %d estaciones | %d variables",
        len(idx), idx["station"].nunique(), idx["variable"].nunique(),
    )
    return idx


def _load_partition(path: Path) -> pd.Series | None:
    """
    Carga una partición parquet (columnas: date, value).
    Retorna pd.Series con índice de fechas, o None si el archivo no existe.
    """
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if df.empty or "date" not in df.columns or VALUE_COL not in df.columns:
        return None
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    series = df.set_index("date")[VALUE_COL].astype(float)
    return series


def _build_station_df(station: str, index: pd.DataFrame) -> pd.DataFrame:
    """
    Construye DataFrame wide para una estación:
    filas = fechas únicas ordenadas, columnas = variables escaladas.
    """
    station_rows = index[index["station"] == station]
    series_map: dict[str, pd.Series] = {}

    for var in VARIABLES:
        var_rows = station_rows[station_rows["variable"] == var]
        if var_rows.empty:
            continue

        year_series: list[pd.Series] = []
        for _, row in var_rows.iterrows():
            path = _resolve_path(str(row["path_parquet"]))
            s = _load_partition(path)
            if s is not None and not s.empty:
                year_series.append(s)

        if year_series:
            combined = pd.concat(year_series).sort_index()
            combined = combined[~combined.index.duplicated(keep="first")]
            series_map[var] = combined

    if not series_map:
        return pd.DataFrame()

    wide = pd.DataFrame(series_map)
    wide.index.name = "date"
    wide.sort_index(inplace=True)

    # Garantizar que las columnas sigan el orden definido en config
    ordered_cols = [v for v in VARIABLES if v in wide.columns]
    return wide[ordered_cols]


def _export_station(station: str, df: pd.DataFrame) -> tuple[Path, Path]:
    """Exporta el DataFrame de estación a Parquet y CSV."""
    prefix = _o["station_file_prefix"]
    df_out = df.reset_index()  # date pasa a ser columna

    parquet_path = PARQUET_DIR / f"{prefix}{station}.parquet"
    csv_path     = CSV_DIR     / f"{prefix}{station}.csv"

    df_out.to_parquet(parquet_path, index=False)
    df_out.to_csv(csv_path, index=False, date_format="%Y-%m-%d")

    return parquet_path, csv_path


def _station_metrics(station: str, df: pd.DataFrame,
                     parquet_path: Path, csv_path: Path) -> dict:
    """Calcula métricas de reporte para una estación procesada."""
    row: dict = {
        "station":       station,
        "filas":         len(df),
        "fecha_inicio":  df.index.min().strftime("%Y-%m-%d"),
        "fecha_fin":     df.index.max().strftime("%Y-%m-%d"),
        "path_parquet":  str(parquet_path.relative_to(PROJECT_ROOT)),
        "path_csv":      str(csv_path.relative_to(PROJECT_ROOT)),
    }
    for var in VARIABLES:
        if var in df.columns:
            row[f"missing_pct_{var}"] = round(df[var].isna().mean() * 100, 2)
            row[f"min_scaled_{var}"]  = round(df[var].min(skipna=True), 6)
            row[f"max_scaled_{var}"]  = round(df[var].max(skipna=True), 6)
        else:
            row[f"missing_pct_{var}"] = 100.0
            row[f"min_scaled_{var}"]  = np.nan
            row[f"max_scaled_{var}"]  = np.nan
    return row


# ─────────────────────────────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────

def run_pipeline() -> None:
    parser = argparse.ArgumentParser(
        description="Etapa 5 — Dataset final procesado (consolidación y exportación)."
    )
    parser.add_argument(
        "--input-dir", type=str, default=None,
        help=(
            "Directorio con el índice de particiones escaladas (_index_scaled.csv). "
            "Por defecto usa data/scaled/ (datos CONAGUA). "
            "Pasar 'data/scaled_external' en modo --external para usar datos externos."
        ),
    )
    args = parser.parse_args()

    # Sobreescribir directorio de entrada si se indica --input-dir.
    # La salida (dataset_final.parquet) siempre va a data/processed/
    # para que las etapas 8-12 no necesiten cambios.
    global SCALED_DIR, INDEX_SCALED
    if args.input_dir:
        SCALED_DIR = (
            PROJECT_ROOT / args.input_dir
            if not Path(args.input_dir).is_absolute()
            else Path(args.input_dir)
        )
        INDEX_SCALED = SCALED_DIR / _p["index_scaled_filename"]

    log.info("=" * 65)
    log.info("PIPELINE 3.3 — Dataset Final Procesado")
    log.info("Inicio : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Output : %s", OUTPUT_DIR)
    log.info("=" * 65)

    index    = _load_index()
    stations = sorted(index["station"].unique())
    total    = len(stations)
    log.info("Estaciones a procesar: %d", total)

    report_rows: list[dict] = []
    index_rows:  list[dict] = []
    failed:      list[str]  = []
    master_dfs:  list[pd.DataFrame] = []

    for i, station in enumerate(stations, 1):
        try:
            df = _build_station_df(station, index)

            if df.empty:
                log.warning("  [%s] Sin datos válidos — omitida", station)
                failed.append(station)
                continue

            parquet_path, csv_path = _export_station(station, df)

            metrics = _station_metrics(station, df, parquet_path, csv_path)
            report_rows.append(metrics)
            index_rows.append({
                "station":      station,
                "filas":        metrics["filas"],
                "fecha_inicio": metrics["fecha_inicio"],
                "fecha_fin":    metrics["fecha_fin"],
                "path_parquet": metrics["path_parquet"],
                "path_csv":     metrics["path_csv"],
            })

            # Acumular para dataset consolidado
            df_master = df.copy()
            df_master.insert(0, STATION_COL, station)
            master_dfs.append(df_master.reset_index())

            if i % PROGRESS_EVERY == 0 or i == total:
                log.info("  Procesadas %d / %d estaciones", i, total)

        except Exception as exc:
            log.error("  [%s] Error inesperado: %s", station, exc, exc_info=True)
            failed.append(station)

    # ── Dataset consolidado (todas las estaciones) ────────────────────
    if master_dfs:
        log.info("Generando dataset_final consolidado…")
        master = pd.concat(master_dfs, ignore_index=True)
        col_order = [STATION_COL, "date"] + [v for v in VARIABLES if v in master.columns]
        master = master[col_order]

        master_parquet = OUTPUT_DIR / _o["master_parquet_filename"]
        master_csv     = OUTPUT_DIR / _o["master_csv_filename"]
        master.to_parquet(master_parquet, index=False)
        master.to_csv(master_csv, index=False, date_format="%Y-%m-%d")
        log.info(
            "dataset_final: %d filas | %d estaciones | %d variables",
            len(master), master[STATION_COL].nunique(), len(VARIABLES),
        )
    else:
        log.warning("No se generó dataset_final: ninguna estación produjo datos.")

    # ── Índice de archivos generados ──────────────────────────────────
    index_df = pd.DataFrame(index_rows)
    index_path = OUTPUT_DIR / _o["index_filename"]
    index_df.to_csv(index_path, index=False)
    log.info("Índice guardado: %s", index_path)

    # ── Reporte por estación ──────────────────────────────────────────
    report_df = pd.DataFrame(report_rows)
    report_path = REPORTS_DIR / _o["pipeline_report_filename"]
    report_df.to_csv(report_path, index=False)
    log.info("Reporte guardado: %s", report_path)

    # ── Resumen final ─────────────────────────────────────────────────
    log.info("=" * 65)
    log.info("RESUMEN")
    log.info("  Estaciones procesadas : %d", len(report_rows))
    log.info("  Estaciones fallidas   : %d  %s",
             len(failed), failed if failed else "")
    log.info("  Archivos por estación : %d Parquet + %d CSV",
             len(report_rows), len(report_rows))
    log.info("  Dataset consolidado   : dataset_final.parquet / .csv")
    log.info("Fin     : %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 65)


if __name__ == "__main__":
    run_pipeline()
