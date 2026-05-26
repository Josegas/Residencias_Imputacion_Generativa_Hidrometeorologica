"""
utils.py — utilidades compartidas entre todas las páginas de la app.
"""

from __future__ import annotations

import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

APP_DIR      = Path(__file__).resolve().parent
ROOT         = APP_DIR.parent
IMPUTE_DIR   = ROOT / "Imputación Generativa"
PIPELINE_DIR = ROOT / "Pipeline Reproducible"
LOGO_PATH    = APP_DIR / "img" / "LOGO_TEC_PNG_OK.png"

sys.path.insert(0, str(IMPUTE_DIR))

from impute import (  # noqa: E402
    ImputationPipeline,
    _apply_physical_limits,
    _apply_tmax_tmin_constraint,
    _impute_station,
    _inverse_scale,
    _scale,
    load_pipeline,
)

logging.basicConfig(level=logging.ERROR)

# ---------------------------------------------------------------------------
# Constantes de dominio
# ---------------------------------------------------------------------------

VARIABLES  = ["precip", "evap", "tmax", "tmin"]
VAR_LABELS = {
    "precip": "Precipitación (mm)",
    "evap":   "Evaporación (mm)",
    "tmax":   "Temp. máxima (°C)",
    "tmin":   "Temp. mínima (°C)",
}
PHYSICAL_DEFAULTS = {
    "precip": {"min": 0.0,   "max": 500.0},
    "evap":   {"min": 0.0,   "max": 60.0},
    "tmax":   {"min": -5.0,  "max": 55.0},
    "tmin":   {"min": -15.0, "max": 45.0},
}
REQUIRED_COLS = ["estacion", "date"] + VARIABLES

# ---------------------------------------------------------------------------
# Carga del modelo (cacheado globalmente)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Cargando modelo BiGRU-opt…")
def get_pipeline() -> ImputationPipeline | None:
    try:
        return load_pipeline(IMPUTE_DIR / "config.yaml")
    except Exception as exc:
        st.error(f"No se pudo cargar el modelo: {exc}")
        return None

# ---------------------------------------------------------------------------
# Imputación sobre datos en escala original
# ---------------------------------------------------------------------------

def impute_original_scale(
    df: pd.DataFrame,
    pipeline: ImputationPipeline,
    progress_bar,
    physical_limits: dict | None = None,
    apply_tmax_tmin: bool = True,
) -> pd.DataFrame:
    """
    Imputa un DataFrame en escala original (mm / °C).
    Acepta límites físicos y restricción tmax≥tmin sobreescritos desde la UI.
    """
    variables = pipeline.variables
    col_sta   = pipeline.cfg["columns"]["station"]
    col_date  = pipeline.cfg["columns"]["date"]

    cfg = dict(pipeline.cfg)
    if physical_limits:
        cfg["physical_limits"] = physical_limits
    cfg.setdefault("constraints", {})["tmax_gte_tmin"] = apply_tmax_tmin

    df = df.copy()
    df[col_date] = pd.to_datetime(df[col_date])
    stations = df[col_sta].unique()

    for i, sta in enumerate(stations):
        mask_sta = df[col_sta] == sta
        sub      = df.loc[mask_sta].sort_values(col_date).copy()

        if sub[variables].isna().sum().sum() == 0:
            progress_bar.progress((i + 1) / len(stations))
            continue

        dates_arr   = sub[col_date].values
        was_nan_arr = np.stack([sub[v].isna().values for v in variables], axis=1)

        scaled     = _scale(sub, pipeline.scalers, variables)
        imputed    = _impute_station(scaled, dates_arr, pipeline)
        orig_scale = _inverse_scale(imputed, pipeline.scalers, variables)
        orig_scale = _apply_physical_limits(orig_scale, variables, cfg)

        if apply_tmax_tmin:
            orig_scale = _apply_tmax_tmin_constraint(
                orig_scale, was_nan_arr, variables
            )

        for j, var in enumerate(variables):
            was_nan = sub[var].isna()
            sub.loc[was_nan, var] = orig_scale[was_nan.values, j]

        df.loc[mask_sta, variables] = sub[variables].values
        progress_bar.progress((i + 1) / len(stations))

    return df

# ---------------------------------------------------------------------------
# Helpers de validación y serialización
# ---------------------------------------------------------------------------

def validate_df(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        errors.append(f"Columnas faltantes: {', '.join(missing)}")
        return errors
    try:
        pd.to_datetime(df["date"], errors="raise")
    except Exception:
        errors.append("La columna 'date' contiene valores no convertibles a fecha.")
    for var in VARIABLES:
        if not pd.api.types.is_numeric_dtype(df[var]):
            errors.append(f"La columna '{var}' debe ser numérica.")
    if df["estacion"].isna().any():
        errors.append("La columna 'estacion' no puede tener valores nulos.")
    return errors


def read_upload(uploaded) -> pd.DataFrame | None:
    name = uploaded.name.lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(uploaded)
        if name.endswith((".xlsx", ".xls")):
            return pd.read_excel(uploaded)
        if name.endswith(".parquet"):
            return pd.read_parquet(uploaded)
    except Exception as exc:
        st.error(f"No se pudo leer el archivo: {exc}")
    return None


def archive_reports(root: Path) -> Path | None:
    """
    Copia quality_gate/, validacion_estadistica/ y monitoreo/ a
    reports/archive/YYYYMMDD_HHMMSS/ antes de una nueva ejecución del pipeline.
    Los originales se conservan en reports/ para que la página de Resultados
    siempre tenga algo que mostrar; la nueva ejecución los sobreescribe.
    Retorna la ruta del archivo creado, o None si no había contenido previo.
    """
    reports_dir = root / "reports"
    subdirs = ["quality_gate", "validacion_estadistica", "monitoreo", "exportacion"]

    existing = [d for d in subdirs if (reports_dir / d).exists()
                and any((reports_dir / d).rglob("*"))]
    if not existing:
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = reports_dir / "archive" / ts
    archive_path.mkdir(parents=True, exist_ok=True)

    for d in existing:
        shutil.copytree(str(reports_dir / d), str(archive_path / d))

    return archive_path


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    import io
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8")
    return buf.getvalue().encode("utf-8")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dataset_imputado")
    return buf.getvalue()
