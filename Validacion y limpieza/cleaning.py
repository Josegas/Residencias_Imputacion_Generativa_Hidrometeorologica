"""
cleaning.py
===========
Limpieza inicial del dataset hidrometeorológico de Sinaloa.

Actividad  : 3.1 Limpieza inicial
Responsable: Data engineer
Entregable : Script cleaning.py + capa data/cleaned/ + reporte CSV

Hallazgos de los notebooks incorporados
-----------------------------------------
Los límites, criterios y decisiones de limpieza se basan directamente
en los resultados de tres análisis previos:

  · Actividad 2.4 — EDA general (eda_general_sinaloa.ipynb)
  · Actividad 2.5 — Análisis de valores faltantes (analisis_valores_faltantes.ipynb)
  · Actividad 2.6 — Análisis temporal y estacional (analisis_temporal_estacional.ipynb)

Todos los parámetros de limpieza (rutas, límites físicos y umbrales IQR)
se configuran en config.yaml — no es necesario editar este script para
adaptar el pipeline a otro estado, fuente o conjunto de variables.

PASOS DEL PIPELINE
  1. Corrige tipos (date -> datetime, value -> float)
  2. Elimina filas con fecha duplicada (conserva primera ocurrencia)
  3. Documenta outliers IQR del EDA (se conservan — posibles registros reales)
  4. Aplica límites físicos por variable (errores extremos -> NaN)
  5. Guarda en data/cleaned/ con la misma estructura jerárquica
  6. Genera _index_cleaned.csv y cleaning_report.csv
  7. Valida los archivos limpios para confirmar el AC de RES-96
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# ─────────────────────────────────────────────
# CONFIGURACIÓN DESDE YAML
# ─────────────────────────────────────────────

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

with CONFIG_PATH.open("r", encoding="utf-8") as _f:
    CFG = yaml.safe_load(_f)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_p = CFG["paths"]
INTERIM_DIR     = PROJECT_ROOT.joinpath(*_p["interim_subpath"])
CLEANED_DIR     = PROJECT_ROOT.joinpath(*_p["cleaned_subpath"])
INDEX_PATH      = INTERIM_DIR / _p["index_filename"]
INDEX_OUT       = CLEANED_DIR / _p["index_out_filename"]
LOG_PATH        = PROJECT_ROOT.joinpath(*_p["log_subpath"]) / _p["log_filename"]
REPORT_PATH     = PROJECT_ROOT.joinpath(*_p["reports_subpath"]) / _p["report_filename"]
VAL_REPORT_PATH = PROJECT_ROOT.joinpath(*_p["reports_subpath"]) / _p["validation_report_filename"]

PHYSICAL_LIMITS = CFG["physical_limits"]
IQR_THRESHOLDS  = CFG["iqr_thresholds"]

_s = CFG["path_segments"]
SEG_DATA    = _s["data"]
SEG_INTERIM = _s["interim"]
SEG_CLEANED = _s["cleaned"]

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# FUNCIONES DE LIMPIEZA
# ─────────────────────────────────────────────

def fix_types(df: pd.DataFrame) -> tuple:
    """
    Corrige los tipos de columnas date y value.
    - date  -> datetime64
    - value -> float64
    Filas con date no convertible se eliminan.
    """
    df = df.copy()
    df["date"]  = pd.to_datetime(df["date"],  errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    n_before = len(df)
    df = df.dropna(subset=["date"])
    n_dropped = n_before - len(df)
    return df, n_dropped


def remove_duplicates(df: pd.DataFrame) -> tuple:
    """
    Elimina filas con fecha duplicada, conservando la primera ocurrencia.
    Hallazgo EDA: el dataset no tenia duplicados tras la organizacion,
    pero se verifica como medida de seguridad ante reprocesamientos.
    """
    n_before = len(df)
    df = df.drop_duplicates(subset=["date"], keep="first")
    n_dupes = n_before - len(df)
    return df, n_dupes


def document_iqr_outliers(df: pd.DataFrame, variable: str) -> tuple:
    """
    Cuenta los valores fuera de los umbrales IQR del EDA.
    Estos valores se CONSERVAN — solo se cuentan para el reporte.

    Decision basada en EDA actividad 2.4 y analisis territorial:
    - TMAX <20.25C y TMIN <-3.75C pueden ser reales en la sierra
    - PRECIP >0 son dias lluviosos, no errores
    - EVAP >12.18mm son dias de alta evaporacion posiblemente reales
    """
    if variable not in IQR_THRESHOLDS:
        return 0, 0

    thresh = IQR_THRESHOLDS[variable]
    lower  = thresh["lower"]
    upper  = thresh["upper"]

    mask_low  = df["value"].notna() & (df["value"] < lower)
    mask_high = df["value"].notna() & (df["value"] > upper)

    return int(mask_low.sum()), int(mask_high.sum())


def apply_physical_limits(df: pd.DataFrame, variable: str) -> tuple:
    """
    Convierte a NaN los valores fuera de los limites fisicos.
    Solo elimina errores extremos que no tienen explicacion fisica posible.
    Los valores dentro del rango IQR que son atipicos se conservan.
    """
    if variable not in PHYSICAL_LIMITS:
        return df, 0, 0

    df   = df.copy()
    lim  = PHYSICAL_LIMITS[variable]
    vmin = lim["min"]
    vmax = lim["max"]

    mask_low  = df["value"].notna() & (df["value"] < vmin)
    mask_high = df["value"].notna() & (df["value"] > vmax)

    n_low  = int(mask_low.sum())
    n_high = int(mask_high.sum())

    df.loc[mask_low | mask_high, "value"] = np.nan

    return df, n_low, n_high


def sort_and_reset(df: pd.DataFrame) -> pd.DataFrame:
    """Ordena por fecha y reinicia el indice."""
    return df.sort_values("date").reset_index(drop=True)


def clean_partition(df: pd.DataFrame, variable: str) -> tuple:
    """
    Aplica el pipeline completo de limpieza a una particion.
    Retorna el dataframe limpio y un dict con las metricas de cambios.
    """
    metrics = {
        "filas_originales"      : len(df),
        "fechas_invalidas"      : 0,
        "duplicados"            : 0,
        "outliers_iqr_bajo"     : 0,
        "outliers_iqr_alto"     : 0,
        "outliers_fisicos_bajo" : 0,
        "outliers_fisicos_alto" : 0,
        "valores_nulos_antes"   : int(df["value"].isna().sum()) if "value" in df.columns else 0,
        "valores_nulos_despues" : 0,
        "filas_finales"         : 0,
        "limite_fisico_min"     : PHYSICAL_LIMITS.get(variable, {}).get("min"),
        "limite_fisico_max"     : PHYSICAL_LIMITS.get(variable, {}).get("max"),
        "umbral_iqr_lower"      : IQR_THRESHOLDS.get(variable, {}).get("lower"),
        "umbral_iqr_upper"      : IQR_THRESHOLDS.get(variable, {}).get("upper"),
        "nota_iqr"              : IQR_THRESHOLDS.get(variable, {}).get("nota", ""),
    }

    # Paso 1: corregir tipos
    df, n_invalid = fix_types(df)
    metrics["fechas_invalidas"] = n_invalid

    # Paso 2: eliminar filas con fecha duplicada
    df, n_dupes = remove_duplicates(df)
    metrics["duplicados"] = n_dupes

    # Paso 3: documentar outliers IQR (antes de aplicar limites fisicos)
    n_iqr_low, n_iqr_high = document_iqr_outliers(df, variable)
    metrics["outliers_iqr_bajo"] = n_iqr_low
    metrics["outliers_iqr_alto"] = n_iqr_high

    # Paso 4: aplicar limites fisicos (solo errores extremos -> NaN)
    df, n_phys_low, n_phys_high = apply_physical_limits(df, variable)
    metrics["outliers_fisicos_bajo"] = n_phys_low
    metrics["outliers_fisicos_alto"] = n_phys_high

    # Paso 5: ordenar cronologicamente
    df = sort_and_reset(df)

    metrics["valores_nulos_despues"] = int(df["value"].isna().sum())
    metrics["filas_finales"]         = len(df)

    return df, metrics


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────

def normalize_path(raw_path: str, root: Path) -> Path:
    """Reconstruye rutas absolutas desde la carpeta data/ si no existen."""
    p = Path(str(raw_path))
    if p.exists():
        return p
    parts = p.parts
    try:
        idx = next(i for i, part in enumerate(parts) if part == SEG_DATA)
        return root / Path(*parts[idx:])
    except StopIteration:
        return p


def build_output_path(interim_parquet: Path) -> Path:
    """
    Construye la ruta de salida en CLEANED_DIR manteniendo la estructura
    relativa a INTERIM_DIR. Usa los globals actuales para soportar tanto
    el modo CONAGUA (cleaned/) como el modo externo (cleaned_external/).
    """
    try:
        rel = interim_parquet.relative_to(INTERIM_DIR)
        return CLEANED_DIR / rel
    except ValueError:
        # Fallback para rutas que no están bajo INTERIM_DIR
        parts = interim_parquet.parts
        try:
            idx = next(i for i, part in enumerate(parts) if part == SEG_INTERIM)
            rel = Path(*parts[idx + 1:])
            return PROJECT_ROOT / SEG_DATA / SEG_CLEANED / rel
        except StopIteration:
            return CLEANED_DIR / interim_parquet.name


# ─────────────────────────────────────────────
# VALIDACIÓN POST-LIMPIEZA (RES-96)
# ─────────────────────────────────────────────

def validate_cleaned_partition(df: pd.DataFrame, variable: str) -> dict:
    """
    Verifica que una partición limpia cumple todos los criterios de calidad.
    Retorna un dict con los hallazgos; 'valido' es False si hay algún problema.
    """
    result = {
        "tipo_date_invalido"    : 0,
        "tipo_value_invalido"   : 0,
        "fechas_duplicadas"     : 0,
        "valores_fuera_limites" : 0,
        "valido"                : True,
    }

    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        result["tipo_date_invalido"] = 1
        result["valido"] = False

    if not pd.api.types.is_float_dtype(df["value"]):
        result["tipo_value_invalido"] = 1
        result["valido"] = False

    n_dupes = int(df["date"].duplicated().sum())
    if n_dupes > 0:
        result["fechas_duplicadas"] = n_dupes
        result["valido"] = False

    if variable in PHYSICAL_LIMITS:
        lim = PHYSICAL_LIMITS[variable]
        mask_out = df["value"].notna() & (
            (df["value"] < lim["min"]) | (df["value"] > lim["max"])
        )
        n_out = int(mask_out.sum())
        if n_out > 0:
            result["valores_fuera_limites"] = n_out
            result["valido"] = False

    return result


def run_validation(index_clean_df: pd.DataFrame) -> bool:
    """
    Pasa de validación post-limpieza sobre todos los archivos guardados.
    Verifica tipos, duplicados y límites físicos para cumplir el AC de RES-96.
    Retorna True si todos los archivos son válidos.
    """
    log.info("=" * 65)
    log.info("VALIDACION POST-LIMPIEZA (RES-96)")
    log.info("Criterio: no quedan valores inconsistentes en los datos limpios")
    log.info("=" * 65)

    total_valid   = 0
    total_invalid = 0
    issue_rows    = []

    for _, row in index_clean_df.iterrows():
        path     = Path(row["path_parquet"])
        variable = str(row["variable"]).lower()

        if not path.exists():
            log.warning(f"[VAL-SKIP] station={row['station']} year={row['year']} "
                        f"var={variable} — archivo no encontrado")
            total_invalid += 1
            continue

        try:
            df = pd.read_parquet(path)
        except Exception as e:
            log.warning(f"[VAL-FAIL] station={row['station']} year={row['year']} "
                        f"var={variable} — error al leer: {e}")
            total_invalid += 1
            continue

        result = validate_cleaned_partition(df, variable)

        if result["valido"]:
            total_valid += 1
        else:
            total_invalid += 1
            issue_rows.append({
                "station"               : row["station"],
                "year"                  : row["year"],
                "variable"              : variable,
                "tipo_date_invalido"    : result["tipo_date_invalido"],
                "tipo_value_invalido"   : result["tipo_value_invalido"],
                "fechas_duplicadas"     : result["fechas_duplicadas"],
                "valores_fuera_limites" : result["valores_fuera_limites"],
            })
            log.warning(
                f"[VAL-FAIL] station={row['station']} year={row['year']} "
                f"var={variable} — {result}"
            )

    log.info(f"Particiones validas      : {total_valid:,}")
    log.info(f"Particiones con problemas: {total_invalid:,}")

    if issue_rows:
        pd.DataFrame(issue_rows).to_csv(VAL_REPORT_PATH, index=False, encoding="utf-8")
        log.warning(f"Reporte de problemas guardado en: {VAL_REPORT_PATH}")
        log.warning("ADVERTENCIA: existen particiones que no cumplen los criterios de calidad")
        return False
    else:
        log.info("VALIDACION EXITOSA: todos los datos limpios cumplen los criterios de calidad")
        log.info("AC RES-96 cumplido: no quedan valores inconsistentes")
        return True


# ─────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Etapa 3 — Limpieza y validación del dataset hidrometeorológico."
    )
    parser.add_argument(
        "--input-dir", type=str, default=None,
        help=(
            "Directorio de entrada con particiones parquet e índice "
            "(ruta relativa a la raíz del proyecto o absoluta). "
            "Por defecto usa el configurado en config.yaml (datos CONAGUA). "
            "Pasar 'data/interim/organized_external/estado=sin' en modo --external."
        ),
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help=(
            "Directorio de salida para particiones limpias e índice. "
            "Por defecto usa data/cleaned/ (datos CONAGUA). "
            "Pasar 'data/cleaned_external' en modo --external."
        ),
    )
    args = parser.parse_args()

    # Sobreescribir rutas globales si se indican directorios alternativos.
    # Permite que datos externos sean limpiados en cleaned_external/ sin
    # tocar cleaned/ (datos CONAGUA del pipeline original).
    global INTERIM_DIR, CLEANED_DIR, INDEX_PATH, INDEX_OUT
    if args.input_dir:
        INTERIM_DIR = (
            PROJECT_ROOT / args.input_dir
            if not Path(args.input_dir).is_absolute()
            else Path(args.input_dir)
        )
        INDEX_PATH = INTERIM_DIR / _p["index_filename"]
    if args.output_dir:
        CLEANED_DIR = (
            PROJECT_ROOT / args.output_dir
            if not Path(args.output_dir).is_absolute()
            else Path(args.output_dir)
        )
        INDEX_OUT = CLEANED_DIR / _p["index_out_filename"]

    log.info("=" * 65)
    log.info("INICIO DE LIMPIEZA — dataset hidrometeorologico Sinaloa")
    log.info("=" * 65)
    log.info(f"Config cargada desde: {CONFIG_PATH}")
    log.info("Criterios basados en EDA, analisis de faltantes y temporal:")
    for var, lim in PHYSICAL_LIMITS.items():
        thresh = IQR_THRESHOLDS.get(var, {})
        log.info(
            f"  {var.upper():<8}: limites [{lim['min']} - {lim['max']}] | "
            f"IQR [{thresh.get('lower', '-')} - {thresh.get('upper', '-')}] documentado"
        )
    log.info("  Outliers IQR temperatura: CONSERVADOS (posibles registros de sierra)")

    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INDEX_PATH.exists():
        log.error(f"No se encontro el indice: {INDEX_PATH}")
        return

    index_df = pd.read_csv(INDEX_PATH)
    index_df["path_parquet"] = index_df["path_parquet"].apply(
        lambda x: normalize_path(x, PROJECT_ROOT)
    )
    index_df = index_df.drop_duplicates(
        subset=["station", "year", "variable"]
    ).reset_index(drop=True)

    log.info(f"Particiones en el indice : {len(index_df):,}")
    log.info(f"Estaciones               : {index_df['station'].nunique()}")
    log.info(f"Variables                : {sorted(index_df['variable'].unique())}")

    report_rows = []
    index_rows  = []
    total_ok    = 0
    total_fail  = 0

    for i, row in index_df.iterrows():
        station  = str(row["station"]).zfill(5)
        year     = int(row["year"])
        variable = str(row["variable"]).lower()
        src_path = Path(row["path_parquet"])

        if not src_path.exists():
            log.warning(f"[SKIP] {src_path.name} — archivo no encontrado")
            total_fail += 1
            continue

        try:
            df_raw = pd.read_parquet(src_path)
        except Exception as e:
            log.warning(f"[FAIL] {src_path.name} — error al leer: {e}")
            total_fail += 1
            continue

        df_clean, metrics = clean_partition(df_raw, variable)

        dst_path = build_output_path(src_path)
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            df_clean.to_parquet(dst_path, index=False)
        except Exception as e:
            log.warning(f"[FAIL] {dst_path.name} — error al guardar: {e}")
            total_fail += 1
            continue

        missing_pct_clean = round(
            float(df_clean["value"].isna().mean() * 100), 3
        ) if len(df_clean) > 0 else 100.0

        report_rows.append({
            "station"               : station,
            "year"                  : year,
            "variable"              : variable,
            "filas_originales"      : metrics["filas_originales"],
            "fechas_invalidas"      : metrics["fechas_invalidas"],
            "duplicados"            : metrics["duplicados"],
            "outliers_iqr_bajo"     : metrics["outliers_iqr_bajo"],
            "outliers_iqr_alto"     : metrics["outliers_iqr_alto"],
            "outliers_fisicos_bajo" : metrics["outliers_fisicos_bajo"],
            "outliers_fisicos_alto" : metrics["outliers_fisicos_alto"],
            "limite_fisico_min"     : metrics["limite_fisico_min"],
            "limite_fisico_max"     : metrics["limite_fisico_max"],
            "umbral_iqr_lower"      : metrics["umbral_iqr_lower"],
            "umbral_iqr_upper"      : metrics["umbral_iqr_upper"],
            "nota_iqr"              : metrics["nota_iqr"],
            "nulos_antes"           : metrics["valores_nulos_antes"],
            "nulos_despues"         : metrics["valores_nulos_despues"],
            "filas_finales"         : metrics["filas_finales"],
            "missing_pct_clean"     : missing_pct_clean,
            "path_parquet_clean"    : str(dst_path),
        })

        index_rows.append({
            "station"      : station,
            "year"         : year,
            "variable"     : variable,
            "path_parquet" : str(dst_path),
            "rows"         : metrics["filas_finales"],
            "missing_pct"  : missing_pct_clean,
        })

        total_ok += 1

        if (i + 1) % 500 == 0:
            log.info(f"  Procesadas {i+1:,} / {len(index_df):,} particiones...")

    # Guardar reporte de limpieza
    report_df = pd.DataFrame(report_rows)
    report_df.to_csv(REPORT_PATH, index=False, encoding="utf-8")
    log.info(f"Reporte guardado en: {REPORT_PATH}")

    index_clean_df = pd.DataFrame(index_rows)
    index_clean_df.to_csv(INDEX_OUT, index=False, encoding="utf-8")
    log.info(f"Indice limpio guardado en: {INDEX_OUT}")

    # ── RESUMEN DE LIMPIEZA ──
    log.info("=" * 65)
    log.info("RESUMEN DE LIMPIEZA")
    log.info("=" * 65)
    log.info(f"Particiones procesadas OK : {total_ok:,}")
    log.info(f"Particiones con error     : {total_fail:,}")

    if not report_df.empty:
        log.info(f"Total fechas invalidas    : {report_df['fechas_invalidas'].sum():,}")
        log.info(f"Total duplicados          : {report_df['duplicados'].sum():,}")
        log.info(f"Total nulos antes         : {report_df['nulos_antes'].sum():,}")
        log.info(f"Total nulos despues       : {report_df['nulos_despues'].sum():,}")
        log.info("")
        log.info("Outliers fisicos eliminados (convertidos a NaN):")
        for var, lim in PHYSICAL_LIMITS.items():
            sub  = report_df[report_df["variable"] == var]
            if sub.empty:
                continue
            bajo = sub["outliers_fisicos_bajo"].sum()
            alto = sub["outliers_fisicos_alto"].sum()
            log.info(
                f"  {var.upper():<8}: bajo={bajo:,}  alto={alto:,}  "
                f"(limites fisicos: {lim['min']} - {lim['max']})"
            )
        log.info("")
        log.info("Outliers IQR documentados (CONSERVADOS en los datos):")
        for var, thresh in IQR_THRESHOLDS.items():
            sub  = report_df[report_df["variable"] == var]
            if sub.empty:
                continue
            bajo = sub["outliers_iqr_bajo"].sum()
            alto = sub["outliers_iqr_alto"].sum()
            log.info(
                f"  {var.upper():<8}: bajo={bajo:,}  alto={alto:,}  — {thresh.get('nota', '')}"
            )

    # ── VALIDACIÓN POST-LIMPIEZA (RES-96) ──
    run_validation(index_clean_df)

    log.info("=" * 65)
    log.info("LIMPIEZA COMPLETADA")
    log.info("=" * 65)


if __name__ == "__main__":
    main()
