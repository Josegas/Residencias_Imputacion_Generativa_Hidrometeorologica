"""
normalize.py
============
Normalización y escalamiento del dataset hidrometeorológico de Sinaloa.

Actividad  : 3.2 Normalización y escalamiento
Responsable: Data scientist
Entregable : Script normalize.py + capa data/scaled/ + scalers guardados + reporte CSV

Todos los parámetros (rutas, semilla, tipo de scaler por variable) se
configuran en config.yaml — no es necesario editar este script para
adaptar el pipeline a otro estado, fuente o conjunto de variables.

Pipeline (modo normal)
----------------------
1. Carga _index_cleaned.csv de la capa cleaned
2. Por cada variable: lee todos los parquet, extrae valores válidos y ajusta
   el scaler global
3. Por cada partición: aplica la transformación y guarda en data/scaled/
4. Guarda los scalers en models/scalers/
5. Genera _index_scaled.csv y scaling_report.csv

Modo datos externos (--transform-only)
---------------------------------------
Usa --transform-only para procesar datos externos sin re-ajustar los scalers.
El modelo BiGRU-opt fue entrenado con los scalers ajustados sobre las 173
estaciones de Sinaloa; re-ajustarlos con datos de una estación distinta
cambiaría la escala y degradaría la calidad de imputación.

Argumentos adicionales:
  --transform-only   Carga scalers existentes de models/scalers/ sin re-ajustar
  --input-dir DIR    Directorio de particiones limpias (por defecto: data/cleaned/)
  --output-dir DIR   Directorio de salida escalada (por defecto: data/scaled/)

Uso con datos externos:
    python "Preprocesamiento/normalize.py" \
        --input-dir data/cleaned_external \
        --output-dir data/scaled_external \
        --transform-only
"""

import argparse
import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.preprocessing import MinMaxScaler, StandardScaler

# ─────────────────────────────────────────────
# CONFIGURACIÓN DESDE YAML
# ─────────────────────────────────────────────

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

with CONFIG_PATH.open("r", encoding="utf-8") as _f:
    CFG = yaml.safe_load(_f)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_p = CFG["paths"]
CLEANED_DIR  = PROJECT_ROOT.joinpath(*_p["cleaned_subpath"])
SCALED_DIR   = PROJECT_ROOT.joinpath(*_p["scaled_subpath"])
SCALERS_DIR  = PROJECT_ROOT.joinpath(*_p["scalers_subpath"])
INDEX_IN     = CLEANED_DIR / _p["index_in_filename"]
INDEX_OUT    = SCALED_DIR  / _p["index_out_filename"]
LOG_PATH     = PROJECT_ROOT.joinpath(*_p["log_subpath"]) / _p["log_filename"]
REPORT_PATH  = PROJECT_ROOT.joinpath(*_p["reports_subpath"]) / _p["report_filename"]
META_PATH    = SCALERS_DIR / _p["scalers_metadata_filename"]

_s = CFG["path_segments"]
SEG_DATA    = _s["data"]
SEG_CLEANED = _s["cleaned"]
SEG_SCALED  = _s["scaled"]

_o = CFG["output"]
VALUE_COL            = _o["value_column"]
STATION_ZFILL        = _o["station_id_zfill"]
SCALER_FILE_PREFIX   = _o["scaler_filename_prefix"]
PROGRESS_INTERVAL    = _o["progress_log_interval"]

RANDOM_SEED = CFG["reproducibility"]["random_seed"]
np.random.seed(RANDOM_SEED)

# Construir SCALER_CONFIG desde YAML
_scaler_builders = {
    "MinMaxScaler":  lambda cfg: MinMaxScaler(feature_range=tuple(cfg.get("feature_range", [0, 1]))),
    "StandardScaler": lambda _: StandardScaler(),
}

SCALER_CONFIG = {}
for _var, _cfg in CFG["scalers"].items():
    _tipo = _cfg["tipo"]
    SCALER_CONFIG[_var] = {
        "scaler": _scaler_builders[_tipo](_cfg),
        "tipo":   _tipo,
    }

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
# FUNCIONES
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


def build_scaled_path(cleaned_parquet: Path) -> Path:
    """
    Construye la ruta de salida en SCALED_DIR manteniendo la estructura
    relativa a CLEANED_DIR. Usa los globals actuales para soportar tanto
    el modo CONAGUA (scaled/) como el modo externo (scaled_external/).
    """
    try:
        rel = cleaned_parquet.relative_to(CLEANED_DIR)
        return SCALED_DIR / rel
    except ValueError:
        # Fallback para rutas que no están bajo CLEANED_DIR
        parts = cleaned_parquet.parts
        try:
            idx = next(i for i, part in enumerate(parts) if part == SEG_CLEANED)
            rel = Path(*parts[idx + 1:])
            return PROJECT_ROOT / SEG_DATA / SEG_SCALED / rel
        except StopIteration:
            return SCALED_DIR / cleaned_parquet.name


def load_existing_scalers() -> dict:
    """
    Carga los scalers pre-entrenados desde SCALERS_DIR sin re-ajustarlos.

    Se usa con --transform-only cuando se procesan datos externos: el modelo
    BiGRU-opt fue entrenado con los scalers ajustados sobre las 173 estaciones
    de Sinaloa; re-ajustar con datos de una sola estación cambiaría la escala
    y degradaría la calidad de imputación. Los scalers originales se mantienen
    intactos en models/scalers/.
    """
    loaded: dict = {}
    for var in SCALER_CONFIG:
        scaler_path = SCALERS_DIR / f"{SCALER_FILE_PREFIX}{var}.pkl"
        if not scaler_path.exists():
            raise FileNotFoundError(
                f"Scaler no encontrado: {scaler_path}\n"
                "Ejecuta el pipeline completo al menos una vez para generar "
                "los scalers antes de usar --transform-only."
            )
        with open(scaler_path, "rb") as f:
            scaler = pickle.load(f)
        loaded[var] = {"scaler": scaler, "tipo": type(scaler).__name__}
        log.info(f"  Scaler cargado (sin re-ajuste): {scaler_path.name}")
    return loaded


def fit_global_scalers(index_df: pd.DataFrame) -> dict:
    """
    Ajusta un scaler global por variable usando TODOS los valores
    válidos de todas las estaciones y años.

    Retorna el diccionario SCALER_CONFIG con los scalers ya ajustados.
    """
    variables = sorted(index_df["variable"].unique())

    for var in variables:
        if var not in SCALER_CONFIG:
            log.warning(
                f"Variable '{var}' no tiene scaler configurado, se omite.")
            continue

        log.info(f"  Ajustando scaler global para {var.upper()}...")

        particiones = index_df[index_df["variable"] == var]
        valores_validos = []

        for _, row in particiones.iterrows():
            p = Path(row["path_parquet"])
            if not p.exists():
                continue
            try:
                df = pd.read_parquet(p, columns=[VALUE_COL])
                vals = df[VALUE_COL].dropna().values
                if len(vals) > 0:
                    valores_validos.append(vals)
            except Exception:
                continue

        if not valores_validos:
            log.warning(
                f"  No se encontraron valores válidos para {var.upper()}")
            continue

        todos = np.concatenate(valores_validos).reshape(-1, 1)
        SCALER_CONFIG[var]["scaler"].fit(todos)

        cfg = SCALER_CONFIG[var]
        tipo = cfg["tipo"]
        if tipo == "MinMaxScaler":
            log.info(
                f"    {tipo} ajustado — "
                f"min={float(cfg['scaler'].data_min_[0]):.4f}  "
                f"max={float(cfg['scaler'].data_max_[0]):.4f}  "
                f"n={len(todos):,}"
            )
        else:
            log.info(
                f"    {tipo} ajustado — "
                f"mean={float(cfg['scaler'].mean_[0]):.4f}  "
                f"std={float(cfg['scaler'].scale_[0]):.4f}  "
                f"n={len(todos):,}"
            )

    return SCALER_CONFIG


def save_scalers(scaler_config: dict) -> None:
    """Guarda cada scaler como archivo .pkl para reproducibilidad futura."""
    SCALERS_DIR.mkdir(parents=True, exist_ok=True)

    for var, cfg in scaler_config.items():
        scaler_path = SCALERS_DIR / f"{SCALER_FILE_PREFIX}{var}.pkl"
        with open(scaler_path, "wb") as f:
            pickle.dump(cfg["scaler"], f)
        log.info(f"  Scaler guardado: {scaler_path.name}")

    meta_rows = []
    for var, cfg in scaler_config.items():
        sc = cfg["scaler"]
        tipo = cfg["tipo"]
        row = {"variable": var, "tipo_scaler": tipo, "pkl": f"{SCALER_FILE_PREFIX}{var}.pkl"}
        if tipo == "MinMaxScaler":
            row["param_min"]  = round(float(sc.data_min_[0]), 6)
            row["param_max"]  = round(float(sc.data_max_[0]), 6)
            row["param_mean"] = None
            row["param_std"]  = None
        else:
            row["param_min"]  = None
            row["param_max"]  = None
            row["param_mean"] = round(float(sc.mean_[0]),  6)
            row["param_std"]  = round(float(sc.scale_[0]), 6)
        meta_rows.append(row)

    meta_df = pd.DataFrame(meta_rows)
    meta_df.to_csv(META_PATH, index=False, encoding="utf-8")
    log.info(f"  Metadatos de scalers guardados: {META_PATH.name}")


def scale_partition(
    df: pd.DataFrame,
    variable: str,
    scaler_config: dict,
) -> pd.DataFrame:
    """
    Aplica la transformación al dataframe de una partición.
    Los NaN se preservan: el scaler solo transforma valores válidos.
    """
    df = df.copy()

    if variable not in scaler_config:
        return df

    scaler = scaler_config[variable]["scaler"]
    mask_valid = df[VALUE_COL].notna()

    if mask_valid.sum() == 0:
        return df

    df.loc[mask_valid, VALUE_COL] = scaler.transform(
        df.loc[mask_valid, VALUE_COL].values.reshape(-1, 1)
    ).flatten()

    return df


# ─────────────────────────────────────────────
# PIPELINE PRINCIPAL
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Etapa 4 — Normalización y escalamiento del dataset hidrometeorológico."
    )
    parser.add_argument(
        "--transform-only", action="store_true",
        help=(
            "Aplica los scalers existentes sin re-ajustarlos. "
            "Obligatorio con datos externos: garantiza que el modelo BiGRU-opt "
            "reciba datos en la misma escala que durante su entrenamiento. "
            "Los archivos .pkl en models/scalers/ no se modifican."
        ),
    )
    parser.add_argument(
        "--input-dir", type=str, default=None,
        help=(
            "Directorio de entrada con particiones limpias e índice. "
            "Por defecto usa data/cleaned/ (datos CONAGUA). "
            "Pasar 'data/cleaned_external' en modo --external."
        ),
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help=(
            "Directorio de salida para particiones escaladas e índice. "
            "Por defecto usa data/scaled/ (datos CONAGUA). "
            "Pasar 'data/scaled_external' en modo --external."
        ),
    )
    args = parser.parse_args()

    # Sobreescribir rutas globales si se indican directorios alternativos.
    # Permite escalar datos externos en scaled_external/ sin tocar scaled/
    # (datos CONAGUA) ni los scalers entrenados en models/scalers/.
    global CLEANED_DIR, SCALED_DIR, INDEX_IN, INDEX_OUT
    if args.input_dir:
        CLEANED_DIR = (
            PROJECT_ROOT / args.input_dir
            if not Path(args.input_dir).is_absolute()
            else Path(args.input_dir)
        )
        INDEX_IN = CLEANED_DIR / _p["index_in_filename"]
    if args.output_dir:
        SCALED_DIR = (
            PROJECT_ROOT / args.output_dir
            if not Path(args.output_dir).is_absolute()
            else Path(args.output_dir)
        )
        INDEX_OUT = SCALED_DIR / _p["index_out_filename"]

    log.info("=" * 60)
    log.info("INICIO DE NORMALIZACIÓN — dataset hidrometeorológico Sinaloa")
    log.info("=" * 60)
    log.info(f"Config cargada desde: {CONFIG_PATH}")
    log.info(f"Semilla de reproducibilidad : {RANDOM_SEED}")
    log.info(f"Scalers configurados:")
    for var, cfg in SCALER_CONFIG.items():
        log.info(f"  {var.upper():<8} → {cfg['tipo']}")

    SCALED_DIR.mkdir(parents=True, exist_ok=True)
    SCALERS_DIR.mkdir(parents=True, exist_ok=True)

    if not INDEX_IN.exists():
        log.error(f"No se encontró el índice cleaned: {INDEX_IN}")
        log.error("Asegúrate de ejecutar cleaning.py antes de normalize.py")
        return

    index_df = pd.read_csv(INDEX_IN)
    index_df["path_parquet"] = index_df["path_parquet"].apply(
        lambda x: normalize_path(x, PROJECT_ROOT)
    )
    index_df = index_df.drop_duplicates(
        subset=["station", "year", "variable"]
    ).reset_index(drop=True)

    log.info(f"Particiones en el índice cleaned : {len(index_df):,}")
    log.info(
        f"Estaciones                       : {index_df['station'].nunique()}")
    log.info(
        f"Variables                        : {sorted(index_df['variable'].unique())}")

    log.info("")
    if args.transform_only:
        # --transform-only: carga scalers pre-entrenados sin re-ajustar.
        # Garantiza que datos externos se normalicen con la misma escala
        # que usó el modelo BiGRU-opt durante el entrenamiento.
        log.info("PASO 1 — Cargando scalers pre-entrenados (--transform-only)...")
        scaler_config = load_existing_scalers()
    else:
        log.info("PASO 1 — Ajustando scalers globales...")
        scaler_config = fit_global_scalers(index_df)
        log.info("")
        log.info("PASO 2 — Guardando scalers...")
        save_scalers(scaler_config)

    log.info("")
    log.info("PASO 3 — Escalando particiones...")

    report_rows = []
    index_rows = []
    total_ok = 0
    total_fail = 0

    for i, row in index_df.iterrows():
        station  = str(row["station"]).zfill(STATION_ZFILL)
        year     = int(row["year"])
        variable = str(row["variable"]).lower()
        src_path = Path(row["path_parquet"])

        if not src_path.exists():
            log.warning(f"[SKIP] {src_path.name} — archivo no encontrado")
            total_fail += 1
            continue

        try:
            df_clean = pd.read_parquet(src_path)
        except Exception as e:
            log.warning(f"[FAIL] {src_path.name} — error al leer: {e}")
            total_fail += 1
            continue

        df_scaled = scale_partition(df_clean, variable, scaler_config)
        n_validos_after = int(df_scaled[VALUE_COL].notna().sum())

        dst_path = build_scaled_path(src_path)
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            df_scaled.to_parquet(dst_path, index=False)
        except Exception as e:
            log.warning(f"[FAIL] {dst_path.name} — error al guardar: {e}")
            total_fail += 1
            continue

        vals_scaled = df_scaled[VALUE_COL].dropna()
        v_min  = round(float(vals_scaled.min()),  6) if len(vals_scaled) > 0 else None
        v_max  = round(float(vals_scaled.max()),  6) if len(vals_scaled) > 0 else None
        v_mean = round(float(vals_scaled.mean()), 6) if len(vals_scaled) > 0 else None

        missing_pct = round(
            float(df_scaled[VALUE_COL].isna().mean() * 100), 3
        ) if len(df_scaled) > 0 else 100.0

        report_rows.append({
            "station":          station,
            "year":             year,
            "variable":         variable,
            "tipo_scaler":      scaler_config.get(variable, {}).get("tipo", "N/A"),
            "filas":            len(df_scaled),
            "valores_validos":  n_validos_after,
            "missing_pct":      missing_pct,
            "valor_min_scaled": v_min,
            "valor_max_scaled": v_max,
            "valor_mean_scaled": v_mean,
            "path_parquet_scaled": str(dst_path),
        })

        index_rows.append({
            "station":     station,
            "year":        year,
            "variable":    variable,
            "path_parquet": str(dst_path),
            "rows":        len(df_scaled),
            "missing_pct": missing_pct,
        })

        total_ok += 1

        if (i + 1) % PROGRESS_INTERVAL == 0:
            log.info(
                f"  Procesadas {i+1:,} / {len(index_df):,} particiones...")

    log.info("")
    log.info("PASO 4 — Guardando reporte e índice...")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report_df = pd.DataFrame(report_rows)
    report_df.to_csv(REPORT_PATH, index=False, encoding="utf-8")
    log.info(f"  Reporte guardado: {REPORT_PATH}")

    index_scaled_df = pd.DataFrame(index_rows)
    index_scaled_df.to_csv(INDEX_OUT, index=False, encoding="utf-8")
    log.info(f"  Índice escalado guardado: {INDEX_OUT}")

    log.info("")
    log.info("=" * 60)
    log.info("RESUMEN FINAL")
    log.info("=" * 60)
    log.info(f"Particiones escaladas OK  : {total_ok:,}")
    log.info(f"Particiones con error     : {total_fail:,}")

    if not report_df.empty:
        log.info("")
        log.info("Rango de valores escalados por variable:")
        for var in scaler_config:
            sub = report_df[report_df["variable"] == var]
            if sub.empty:
                continue
            tipo = scaler_config[var]["tipo"]
            vmin  = sub["valor_min_scaled"].min()
            vmax  = sub["valor_max_scaled"].max()
            vmean = sub["valor_mean_scaled"].mean()
            log.info(
                f"  {var.upper():<8} [{tipo}]  "
                f"min={vmin:.4f}  max={vmax:.4f}  mean={vmean:.4f}"
            )

    log.info("")
    log.info("Archivos generados:")
    log.info(f"  {SCALED_DIR.relative_to(PROJECT_ROOT)}/  → {total_ok:,} parquet escalados")
    log.info(f"  {SCALERS_DIR.relative_to(PROJECT_ROOT)}/  → {len(SCALER_CONFIG)} archivos .pkl + {_p['scalers_metadata_filename']}")
    log.info(f"  {REPORT_PATH.relative_to(PROJECT_ROOT)}  → reporte por partición")
    log.info(f"  {LOG_PATH.relative_to(PROJECT_ROOT)}  → log completo de ejecución")
    log.info("=" * 60)
    log.info("NORMALIZACIÓN COMPLETADA")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
