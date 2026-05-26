"""
impute.py
=========
Función de imputación generativa final — US 5.2 (RES-34)

Aplica el modelo BiGRU-opt (modelo ganador del proceso CRISP-ML(Q)) para
reconstruir los valores faltantes de un DataFrame hidrometeorológico.

Flujo interno
-------------
1. Carga el modelo ganador (leído de seleccion_ejecutiva.csv) y los scalers.
2. Por estación: escala los valores, genera ventanas deslizantes y ejecuta
   el modelo en modo inferencia (eval, sin dropout).
3. Reconstruye la serie completa promediando predicciones solapadas.
4. Solo rellena posiciones que eran NaN — los valores observados se preservan
   exactamente tal como llegaron.
5. Aplica la transformación inversa de los scalers.
6. Aplica límites físicos (precip [0-500], evap [0-60], tmax [-5,55], tmin [-15,45]).
7. Corrige inversión tmax < tmin cuando ambas fueron imputadas.
8. Exporta el dataset imputado y un reporte de cobertura.

Uso desde línea de comandos
---------------------------
    python "Imputación Generativa/impute.py"
    python "Imputación Generativa/impute.py" --input data/processed/dataset_final.parquet
    python "Imputación Generativa/impute.py" --config path/to/config.yaml

Uso como módulo
---------------
    from pathlib import Path
    import pandas as pd
    from impute import load_pipeline, impute_dataframe

    pipeline = load_pipeline()
    df_raw   = pd.read_parquet("data/processed/dataset_final.parquet")
    df_imp   = impute_dataframe(df_raw, pipeline)
"""

from __future__ import annotations

import argparse
import logging
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import yaml

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent   # Imputación Generativa/
ROOT       = SCRIPT_DIR.parent                 # raíz del proyecto
CONFIG     = SCRIPT_DIR / "config.yaml"


# ---------------------------------------------------------------------------
# Configuración y logging
# ---------------------------------------------------------------------------

def _load_config(config_path: Path = CONFIG) -> dict:
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _setup_logging(cfg: dict) -> logging.Logger:
    log_dir  = ROOT / cfg["output"]["log_dir"]
    log_file = log_dir / cfg["output"]["log_file"]
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_file, mode="w", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("impute")


# ---------------------------------------------------------------------------
# Arquitectura del modelo ganador (BiGRUImputer)
# Debe coincidir exactamente con la definición en Optimización/optimizacion_hiperparametros.ipynb
# ---------------------------------------------------------------------------

class BiGRUImputer(nn.Module):
    """
    GRU bidireccional para imputación de series temporales.

    Input:
        x    : (N, T, F) — valores escalados (NaN → 0)
        mask : (N, T, F) — 1 = observado, 0 = faltante

    Output:
        (N, T, F) — reconstrucción completa.
        Los valores observados se re-inyectan directamente:
            output = mask * x + (1 - mask) * predicción
    """

    def __init__(self, n_features: int = 4, hidden_size: int = 128,
                 n_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.rnn = nn.GRU(
            input_size    = n_features * 2,
            hidden_size   = hidden_size,
            num_layers    = n_layers,
            dropout       = dropout if n_layers > 1 else 0.0,
            batch_first   = True,
            bidirectional = True,
        )
        self.out = nn.Linear(hidden_size * 2, n_features)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        h, _ = self.rnn(torch.cat([x, mask], dim=-1))
        pred  = self.out(h)
        return mask * x + (1 - mask) * pred


# ---------------------------------------------------------------------------
# Carga del pipeline (modelo + scalers)
# ---------------------------------------------------------------------------

class ImputationPipeline:
    """Contenedor del modelo y los scalers listos para inferencia."""

    def __init__(self, model: BiGRUImputer, scalers: dict,
                 variables: list[str], device: str, cfg: dict):
        self.model     = model
        self.scalers   = scalers
        self.variables = variables
        self.device    = device
        self.cfg       = cfg


def _resolve_device(device_cfg: str) -> str:
    if device_cfg == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device_cfg


def _resolve_winner(cfg: dict) -> tuple[str, Path]:
    """
    Lee seleccion_ejecutiva.csv para determinar el modelo ganador.
    Si el CSV no existe, usa el modelo por defecto del config.
    Retorna (nombre_modelo, ruta_checkpoint).
    """
    log = logging.getLogger("impute")
    sel_path = ROOT / cfg["selection"]["report"]

    if sel_path.exists():
        df_sel = pd.read_csv(sel_path)
        winner = str(df_sel["modelo_ganador"].iloc[0]).upper()
        score  = float(df_sel["score_total"].iloc[0])
        log.info(f"Selección ejecutiva  : {winner}  (score={score:.4f})")
        model_paths = cfg["selection"]["model_paths"]
        if winner in model_paths:
            return winner, ROOT / model_paths[winner]
        log.warning(f"Modelo '{winner}' no tiene ruta configurada. Usando default.")
    else:
        log.warning(
            f"seleccion_ejecutiva.csv no encontrado: {sel_path.relative_to(ROOT)}\n"
            "         Usando modelo por defecto del config."
        )

    default = cfg["model"]["default"]
    return default, ROOT / cfg["model"]["path"]


def load_pipeline(config_path: Path = CONFIG) -> ImputationPipeline:
    """
    Carga el modelo ganador (según seleccion_ejecutiva.csv) y los scalers.

    Returns
    -------
    ImputationPipeline
        Objeto listo para pasarlo a `impute_dataframe`.
    """
    cfg    = _load_config(config_path)
    log    = logging.getLogger("impute")
    device = _resolve_device(cfg["inference"]["device"])

    # ── Modelo ganador (leído desde seleccion_ejecutiva.csv) ─────────────────
    winner_name, model_path = _resolve_winner(cfg)

    if not model_path.exists():
        raise FileNotFoundError(
            f"Checkpoint del modelo ganador no encontrado: {model_path}\n"
            "Ejecuta primero los notebooks de Optimización/."
        )

    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    model_cfg  = checkpoint.get("config", {})

    model = BiGRUImputer(
        n_features  = model_cfg.get("n_features",  cfg["model"]["n_features"]),
        hidden_size = model_cfg.get("hidden_size", cfg["model"]["hidden_size"]),
        n_layers    = model_cfg.get("n_layers",    cfg["model"]["n_layers"]),
        dropout     = model_cfg.get("dropout",     cfg["model"]["dropout"]),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device).eval()

    log.info(f"Modelo ganador       : {winner_name}")
    log.info(f"Checkpoint           : {model_path.relative_to(ROOT)}")
    log.info(f"Device               : {device}")
    log.info(f"Config del modelo    : {model_cfg}")

    # ── Scalers ─────────────────────────────────────────────────────────────
    scalers_dir = ROOT / cfg["scalers"]["dir"]
    scalers: dict = {}
    for var, fname in cfg["scalers"]["files"].items():
        pkl = scalers_dir / f"{fname}.pkl"
        if not pkl.exists():
            raise FileNotFoundError(
                f"Scaler no encontrado: {pkl}\n"
                "Ejecuta primero Preprocesamiento/normalize.py."
            )
        with pkl.open("rb") as f:
            scalers[var] = pickle.load(f)
        log.info(f"Scaler cargado : {var} → {pkl.name}")

    return ImputationPipeline(
        model     = model,
        scalers   = scalers,
        variables = cfg["variables"],
        device    = device,
        cfg       = cfg,
    )


# ---------------------------------------------------------------------------
# Lógica de imputación
# ---------------------------------------------------------------------------

def _scale(df_station: pd.DataFrame, scalers: dict, variables: list[str]) -> np.ndarray:
    """Escala las columnas de variables; preserva NaN."""
    result = np.full((len(df_station), len(variables)), np.nan, dtype=np.float32)
    for j, var in enumerate(variables):
        col = df_station[var].values.reshape(-1, 1)
        valid = ~np.isnan(col.ravel())
        if valid.any():
            result[valid, j] = scalers[var].transform(col[valid].reshape(-1, 1)).ravel()
    return result


def _inverse_scale(arr: np.ndarray, scalers: dict,
                   variables: list[str]) -> np.ndarray:
    """Deshace el escalamiento."""
    result = np.full_like(arr, np.nan)
    for j, var in enumerate(variables):
        col = arr[:, j].reshape(-1, 1)
        valid = ~np.isnan(col.ravel())
        if valid.any():
            result[valid, j] = scalers[var].inverse_transform(
                col[valid].reshape(-1, 1)
            ).ravel()
    return result


def _apply_physical_limits(arr: np.ndarray, variables: list[str],
                            cfg: dict) -> np.ndarray:
    """Clips values to physically valid ranges from config.physical_limits."""
    limits = cfg.get("physical_limits", {})
    arr = arr.copy()
    for j, var in enumerate(variables):
        if var not in limits:
            continue
        lo = limits[var].get("min")
        hi = limits[var].get("max")
        col = arr[:, j]
        valid = ~np.isnan(col)
        if lo is not None:
            col = np.where(valid, np.maximum(col, lo), col)
        if hi is not None:
            col = np.where(valid, np.minimum(col, hi), col)
        arr[:, j] = col
    return arr


def _apply_tmax_tmin_constraint(arr: np.ndarray, was_nan_arr: np.ndarray,
                                 variables: list[str]) -> np.ndarray:
    """
    Garantiza tmax >= tmin para posiciones donde ambas variables fueron imputadas.
    Cuando la predicción invierte el orden, intercambia los valores.
    Solo actúa sobre posiciones donde tanto tmax como tmin eran NaN originalmente.
    """
    if "tmax" not in variables or "tmin" not in variables:
        return arr
    j_tmax = variables.index("tmax")
    j_tmin = variables.index("tmin")
    arr = arr.copy()
    both_imputed = was_nan_arr[:, j_tmax] & was_nan_arr[:, j_tmin]
    inverted     = both_imputed & (arr[:, j_tmax] < arr[:, j_tmin])
    if inverted.any():
        tmax_vals = arr[inverted, j_tmax].copy()
        tmin_vals = arr[inverted, j_tmin].copy()
        arr[inverted, j_tmax] = tmin_vals   # el mayor pasa a tmax
        arr[inverted, j_tmin] = tmax_vals   # el menor pasa a tmin
    return arr


def _build_windows(scaled: np.ndarray, dates: np.ndarray,
                   window_size: int, stride: int,
                   max_gap_days: int) -> list[tuple[int, int]]:
    """
    Devuelve lista de (start_idx, end_idx) de ventanas válidas.
    Una ventana es inválida si contiene una brecha temporal > max_gap_days.
    """
    n = len(scaled)
    windows = []
    for s in range(0, n - window_size + 1, stride):
        e = s + window_size
        # Verificar que no haya brechas temporales excesivas en la ventana
        segment_dates = dates[s:e]
        gaps = np.diff(segment_dates.astype("datetime64[D]").astype(int))
        if gaps.max() <= max_gap_days:
            windows.append((s, e))
    return windows


def _impute_station(scaled: np.ndarray, dates: np.ndarray,
                    pipeline: ImputationPipeline) -> np.ndarray:
    """
    Imputa los valores faltantes de una estación usando ventanas deslizantes.

    Estrategia de reconstrucción: para cada posición del tiempo se acumulan
    las predicciones de todas las ventanas que la cubren y se promedia.
    Solo las posiciones originalmente faltantes (mask=0) se reemplazan.
    """
    cfg_seq = pipeline.cfg["sequence"]
    window_size  = cfg_seq["window_size"]
    stride       = cfg_seq["stride"]
    max_gap_days = cfg_seq["max_gap_days"]
    batch_size   = pipeline.cfg["inference"]["batch_size"]
    device       = pipeline.device

    n, f = scaled.shape
    mask_orig = (~np.isnan(scaled)).astype(np.float32)  # 1=obs, 0=faltante

    # Valores con NaN → 0 para la entrada del modelo
    x_clean = np.where(np.isnan(scaled), 0.0, scaled).astype(np.float32)

    windows = _build_windows(scaled, dates, window_size, stride, max_gap_days)
    if not windows:
        return scaled  # sin ventanas válidas, devuelve sin cambios

    # Acumuladores para promediado
    pred_sum   = np.zeros_like(x_clean)
    pred_count = np.zeros((n, f), dtype=np.float32)

    # Procesar en batches
    for batch_start in range(0, len(windows), batch_size):
        batch_wins = windows[batch_start: batch_start + batch_size]

        x_batch = np.stack([x_clean[s:e]       for s, e in batch_wins])
        m_batch = np.stack([mask_orig[s:e]      for s, e in batch_wins])

        x_t = torch.tensor(x_batch, dtype=torch.float32).to(device)
        m_t = torch.tensor(m_batch, dtype=torch.float32).to(device)

        with torch.no_grad():
            pred = pipeline.model(x_t, m_t).cpu().numpy()  # (B, T, F)

        for (s, e), p in zip(batch_wins, pred):
            pred_sum[s:e]   += p
            pred_count[s:e] += 1

    # Promediar donde hay al menos una predicción
    covered = pred_count > 0
    pred_avg = np.where(covered, pred_sum / np.where(covered, pred_count, 1), x_clean)

    # Solo rellenar posiciones faltantes
    imputed = np.where(mask_orig == 0, pred_avg, x_clean)
    # Mantener NaN en posiciones no cubiertas por ninguna ventana
    not_covered = (~covered) & (mask_orig == 0)
    imputed = np.where(not_covered, np.nan, imputed)

    return imputed.astype(np.float32)


def impute_dataframe(df: pd.DataFrame,
                     pipeline: ImputationPipeline) -> pd.DataFrame:
    """
    Imputa los valores faltantes de un DataFrame hidrometeorológico.

    Parámetros
    ----------
    df : pd.DataFrame
        DataFrame con columnas: estacion, date, precip, evap, tmax, tmin.
        Los valores deben estar en escala original (mm, °C).
        Los NaN serán imputados.

    pipeline : ImputationPipeline
        Objeto devuelto por `load_pipeline()`.

    Retorna
    -------
    pd.DataFrame
        Mismo esquema que la entrada. Los NaN están rellenados con las
        predicciones del modelo. Los valores observados se preservan exactamente.
    """
    log = logging.getLogger("impute")
    cfg_col   = pipeline.cfg["columns"]
    variables = pipeline.variables
    col_sta   = cfg_col["station"]
    col_date  = cfg_col["date"]

    df = df.copy()
    df[col_date] = pd.to_datetime(df[col_date])

    # dataset_final.parquet está en escala normalizada (salida de normalize.py).
    # Convertir a escala original antes de procesar para que _scale() pueda
    # re-escalar correctamente y el output quede en unidades físicas.
    for var in variables:
        if var not in df.columns:
            continue
        vals = df[var].values.copy()
        valid = ~np.isnan(vals)
        if valid.any():
            vals[valid] = pipeline.scalers[var].inverse_transform(
                vals[valid].reshape(-1, 1)
            ).ravel()
            df[var] = vals

    stations = df[col_sta].unique()

    log.info(f"Estaciones a imputar : {len(stations)}")
    log.info(f"Registros totales    : {len(df):,}")

    nan_before = df[variables].isna().sum().to_dict()

    t0 = time.time()
    report_rows = []

    for sta in stations:
        mask_sta = df[col_sta] == sta
        sub = df.loc[mask_sta].sort_values(col_date).copy()

        nan_sta_before = sub[variables].isna().sum()
        if nan_sta_before.sum() == 0:
            # Sin faltantes: nada que imputar
            report_rows.append({col_sta: sta, **{v: 0 for v in variables}})
            continue

        dates_arr   = sub[col_date].values
        was_nan_arr = np.stack([sub[v].isna().values for v in variables], axis=1)

        # Escalar → imputar → desescalar
        scaled     = _scale(sub, pipeline.scalers, variables)
        imputed    = _impute_station(scaled, dates_arr, pipeline)
        orig_scale = _inverse_scale(imputed, pipeline.scalers, variables)

        # Post-procesamiento físico: recorte a límites válidos
        orig_scale = _apply_physical_limits(orig_scale, variables, pipeline.cfg)

        # Restricción lógica: tmax >= tmin (solo posiciones imputadas)
        if pipeline.cfg.get("constraints", {}).get("tmax_gte_tmin", False):
            orig_scale = _apply_tmax_tmin_constraint(
                orig_scale, was_nan_arr, variables
            )

        # Escribir de vuelta solo las posiciones que eran NaN
        for j, var in enumerate(variables):
            was_nan = sub[var].isna()
            new_vals = orig_scale[:, j]
            sub.loc[was_nan, var] = new_vals[was_nan.values]

        df.loc[mask_sta, variables] = sub[variables].values

        nan_filled = {v: int(nan_sta_before[v]) for v in variables}
        report_rows.append({col_sta: sta, **nan_filled})

    elapsed = time.time() - t0
    nan_after = df[variables].isna().sum().to_dict()

    log.info(f"Imputación completada en {elapsed:.1f}s")
    for var in variables:
        filled = nan_before[var] - nan_after[var]
        log.info(
            f"  {var:6s}: {nan_before[var]:>7,} NaN antes  →  "
            f"{nan_after[var]:>7,} después  ({filled:,} rellenados)"
        )

    # Guardar reporte
    report_dir = ROOT / pipeline.cfg["output"]["report"]
    report_dir.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(report_rows).to_csv(report_dir, index=False)
    log.info(f"Reporte guardado en  : {report_dir.relative_to(ROOT)}")

    return df


# ---------------------------------------------------------------------------
# Exportación del dataset imputado
# ---------------------------------------------------------------------------

def export_imputed(df: pd.DataFrame, pipeline: ImputationPipeline) -> None:
    """Guarda el DataFrame imputado en Parquet (formato interno del pipeline).
    El CSV para usuarios finales lo genera la Etapa 12 — Análisis y Exportación.
    """
    log = logging.getLogger("impute")
    out_cfg = pipeline.cfg["output"]

    parquet_path = ROOT / out_cfg["parquet"]
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(parquet_path, index=False)

    log.info(f"Dataset imputado guardado:")
    log.info(f"  Parquet : {parquet_path.relative_to(ROOT)}")
    log.info(f"  Filas   : {len(df):,}  |  Columnas: {list(df.columns)}")


# ---------------------------------------------------------------------------
# Punto de entrada por línea de comandos
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Imputación generativa BiGRU-opt — Proyecto CRISP-ML(Q)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", type=Path,
        default=None,
        help="Ruta al parquet de entrada. Por defecto: data/processed/dataset_final.parquet",
    )
    parser.add_argument(
        "--config", type=Path,
        default=CONFIG,
        help=f"Ruta al config.yaml. Por defecto: {CONFIG.relative_to(ROOT)}",
    )
    args = parser.parse_args()

    cfg = _load_config(args.config)
    log = _setup_logging(cfg)

    torch.manual_seed(cfg["reproducibility"]["random_seed"])
    np.random.seed(cfg["reproducibility"]["random_seed"])

    log.info("=" * 60)
    log.info("INICIO — Imputación Generativa BiGRU-opt")
    log.info("=" * 60)
    log.info(f"Raíz del proyecto : {ROOT}")
    log.info(f"Config            : {args.config.relative_to(ROOT)}")

    # Cargar pipeline
    pipeline = load_pipeline(args.config)

    # Cargar datos de entrada
    input_path = args.input or ROOT / cfg["input"]["dataset"]
    if not input_path.exists():
        log.error(f"Archivo de entrada no encontrado: {input_path}")
        log.error("Ejecuta primero el pipeline de datos (etapas 1–7).")
        sys.exit(1)

    log.info(f"Leyendo dataset   : {input_path.relative_to(ROOT)}")
    df_raw = pd.read_parquet(input_path)
    log.info(f"Filas             : {len(df_raw):,}  |  Columnas: {list(df_raw.columns)}")

    # Imputar
    df_imputed = impute_dataframe(df_raw, pipeline)

    # Exportar
    export_imputed(df_imputed, pipeline)

    log.info("=" * 60)
    log.info("FIN — Imputación completada exitosamente")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
