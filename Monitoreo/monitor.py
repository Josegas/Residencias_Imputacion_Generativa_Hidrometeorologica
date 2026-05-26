"""
monitor.py
==========
Monitoreo del modelo — Etapa 11 del pipeline

Detecta drift distribucional en el dataset imputado comparando cada ventana
temporal decadal contra una ventana de referencia (1970–2000 por defecto).
Genera alertas de reentrenamiento si el PSI supera el umbral crítico.

Métricas calculadas
-------------------
- PSI (Population Stability Index) por década y variable
- KS-test entre cada década y la ventana de referencia
- Cobertura temporal: tasa de NaN residual por período
- Alerta de reentrenamiento: PSI > umbral en ventana más reciente

Uso
---
    python "Monitoreo/monitor.py"
    python "Monitoreo/monitor.py" --config ruta/config.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import ks_2samp

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT       = SCRIPT_DIR.parent
CONFIG     = SCRIPT_DIR / "config.yaml"


# ---------------------------------------------------------------------------
# Config y logging
# ---------------------------------------------------------------------------

def _load_config(path: Path = CONFIG) -> dict:
    with path.open(encoding="utf-8") as f:
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
    return logging.getLogger("monitor")


# ---------------------------------------------------------------------------
# PSI (Population Stability Index)
# ---------------------------------------------------------------------------

def _psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """
    PSI = Σ (actual% - expected%) × ln(actual% / expected%)
    < 0.10 : sin cambio  |  0.10–0.20 : moderado  |  > 0.20 : significativo
    """
    if len(expected) < 20 or len(actual) < 20:
        return np.nan
    breaks = np.nanpercentile(expected, np.linspace(0, 100, bins + 1))
    breaks = np.unique(breaks)
    if len(breaks) < 3:
        return np.nan
    breaks[0]  -= 1e-6
    breaks[-1] += 1e-6
    exp_cnt, _ = np.histogram(expected, bins=breaks)
    act_cnt, _ = np.histogram(actual,   bins=breaks)
    exp_pct = exp_cnt / len(expected) + 1e-8
    act_pct = act_cnt / len(actual)   + 1e-8
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


# ---------------------------------------------------------------------------
# Drift por décadas
# ---------------------------------------------------------------------------

def compute_drift(df_imp: pd.DataFrame, cfg: dict,
                  log: logging.Logger) -> pd.DataFrame:
    """PSI y KS-test de cada ventana decadal contra la ventana de referencia."""
    variables    = cfg["variables"]
    col_date     = cfg["columns"]["date"]
    window_years = cfg["window_years"]
    ref_start    = cfg["reference_window"]["start"]
    ref_end      = cfg["reference_window"]["end"]
    ks_alpha     = cfg["ks_significance"]

    df_imp[col_date] = pd.to_datetime(df_imp[col_date], errors="coerce")
    df_imp["_year"]  = df_imp[col_date].dt.year

    year_min = int(df_imp["_year"].min())
    year_max = int(df_imp["_year"].max())

    rows = []
    for var in variables:
        ref_mask = (df_imp["_year"] >= ref_start) & (df_imp["_year"] <= ref_end)
        ref_vals = df_imp.loc[ref_mask, var].dropna().values
        log.info(f"  {var}: referencia {ref_start}–{ref_end}  (n={len(ref_vals):,})")

        for w_start in range(year_min, year_max + 1, window_years):
            w_end  = min(w_start + window_years - 1, year_max)
            w_mask = (df_imp["_year"] >= w_start) & (df_imp["_year"] <= w_end)
            w_vals = df_imp.loc[w_mask, var].dropna().values

            if len(w_vals) < 20:
                continue

            psi_val = _psi(ref_vals, w_vals)
            if len(ref_vals) >= 10 and len(w_vals) >= 10:
                ks_stat, ks_p = ks_2samp(ref_vals, w_vals)
            else:
                ks_stat, ks_p = np.nan, np.nan

            psi_level = (
                "CRITICAL" if (not np.isnan(psi_val) and psi_val > cfg["psi_critical"]) else
                "WARNING"  if (not np.isnan(psi_val) and psi_val > cfg["psi_warning"])  else
                "OK"
            )
            ks_result = (
                "WARNING" if (not np.isnan(ks_p) and ks_p < ks_alpha) else "OK"
            )
            log.info(
                f"    {var} {w_start}–{w_end}: "
                f"PSI={psi_val:.4f} [{psi_level}]  "
                f"KS={ks_stat:.4f} p={ks_p:.4f} [{ks_result}]"
            )
            rows.append({
                "variable":   var,
                "ventana":    f"{w_start}–{w_end}",
                "w_start":    w_start,
                "w_end":      w_end,
                "n":          len(w_vals),
                "psi":        round(float(psi_val), 6) if not np.isnan(psi_val) else None,
                "psi_nivel":  psi_level,
                "ks_stat":    round(float(ks_stat), 6) if not np.isnan(ks_stat) else None,
                "ks_p":       round(float(ks_p), 6) if not np.isnan(ks_p) else None,
                "ks_result":  ks_result,
            })

    df_imp.drop(columns=["_year"], inplace=True)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Cobertura temporal
# ---------------------------------------------------------------------------

def compute_temporal_coverage(df_orig: pd.DataFrame, df_imp: pd.DataFrame,
                               cfg: dict, log: logging.Logger) -> pd.DataFrame:
    """Tasa de NaN residual por década y variable."""
    variables    = cfg["variables"]
    col_date     = cfg["columns"]["date"]
    window_years = cfg["window_years"]

    for df in (df_orig, df_imp):
        df[col_date] = pd.to_datetime(df[col_date], errors="coerce")
        df["_year"]  = df[col_date].dt.year

    year_min = int(df_imp["_year"].min())
    year_max = int(df_imp["_year"].max())

    rows = []
    for var in variables:
        for w_start in range(year_min, year_max + 1, window_years):
            w_end   = min(w_start + window_years - 1, year_max)
            o_mask  = (df_orig["_year"] >= w_start) & (df_orig["_year"] <= w_end)
            i_mask  = (df_imp["_year"]  >= w_start) & (df_imp["_year"]  <= w_end)
            nan_o   = df_orig.loc[o_mask, var].isna().sum()
            nan_i   = df_imp.loc[i_mask,  var].isna().sum()
            filled  = nan_o - nan_i
            rate    = filled / nan_o if nan_o > 0 else 1.0
            rows.append({
                "variable":       var,
                "ventana":        f"{w_start}–{w_end}",
                "w_start":        w_start,
                "nan_original":   int(nan_o),
                "nan_residual":   int(nan_i),
                "rellenados":     int(filled),
                "tasa_cobertura": round(rate, 4),
            })
        log.info(f"  {var}: cobertura temporal calculada")

    for df in (df_orig, df_imp):
        df.drop(columns=["_year"], inplace=True)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------

def _plot_drift(df_drift: pd.DataFrame, variables: list[str],
                fig_dir: Path, cfg: dict) -> None:
    if not _HAS_MPL or df_drift.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    colors = {"OK": "#2e7d32", "WARNING": "#f57f17", "CRITICAL": "#c62828"}

    for ax, var in zip(axes.flatten(), variables):
        sub = df_drift[df_drift["variable"] == var].dropna(subset=["psi"])
        if sub.empty:
            ax.set_title(var, fontweight="bold")
            ax.text(0.5, 0.5, "Sin datos suficientes\npara calcular PSI",
                    ha="center", va="center", transform=ax.transAxes,
                    color="gray", fontsize=10)
            ax.set_axis_off()
            continue
        bar_colors = [colors.get(lvl, "#90a4ae") for lvl in sub["psi_nivel"]]
        ax.bar(sub["w_start"], sub["psi"], width=8, color=bar_colors, edgecolor="white")
        ax.axhline(cfg["psi_warning"],  color="#f57f17", linestyle="--",
                   linewidth=1, label=f"WARNING ({cfg['psi_warning']})")
        ax.axhline(cfg["psi_critical"], color="#c62828", linestyle="--",
                   linewidth=1, label=f"CRITICAL ({cfg['psi_critical']})")
        ax.set_title(var, fontweight="bold")
        ax.set_xlabel("Inicio de ventana decadal")
        ax.set_ylabel("PSI")
        ax.legend(fontsize=7)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    ref_s = cfg["reference_window"]["start"]
    ref_e = cfg["reference_window"]["end"]
    fig.suptitle(
        f"Drift distribucional — PSI por década vs. referencia {ref_s}–{ref_e}",
        fontsize=13, fontweight="bold",
    )
    plt.tight_layout()
    out = fig_dir / "drift_decadal.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_coverage(df_cov: pd.DataFrame, variables: list[str],
                   fig_dir: Path, cfg: dict) -> None:
    if not _HAS_MPL or df_cov.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))

    for ax, var in zip(axes.flatten(), variables):
        sub = df_cov[df_cov["variable"] == var].sort_values("w_start")
        ax.bar(sub["w_start"], sub["tasa_cobertura"] * 100,
               width=8, color="#1565c0", edgecolor="white", alpha=0.8)
        target = cfg.get("coverage_target_pct", 99)
        ax.axhline(target, color="#ef6c00", linestyle="--",
                   linewidth=1, label=f"Objetivo {target}%")
        ax.set_ylim(0, 105)
        ax.set_title(var, fontweight="bold")
        ax.set_xlabel("Inicio de ventana decadal")
        ax.set_ylabel("Cobertura de imputación (%)")
        ax.legend(fontsize=7)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.suptitle("Cobertura de imputación por década",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    out = fig_dir / "cobertura_temporal.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Monitoreo del modelo — Etapa 11")
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()

    cfg = _load_config(args.config)
    log = _setup_logging(cfg)

    report_dir = ROOT / cfg["output"]["report_dir"]
    fig_dir    = report_dir / "figuras"
    report_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    # --- Carga de datos ---
    orig_path = ROOT / cfg["input"]["original"]
    imp_path  = ROOT / cfg["input"]["imputed"]
    log.info(f"Cargando dataset original : {orig_path.name}")
    df_orig = pd.read_parquet(orig_path)
    log.info(f"Cargando dataset imputado : {imp_path.name}")
    df_imp  = pd.read_parquet(imp_path)

    # --- Drift distribucional (PSI + KS) ---
    log.info("=== Drift distribucional (PSI + KS-test) ===")
    df_drift = compute_drift(df_imp.copy(), cfg, log)

    # --- Cobertura temporal ---
    log.info("=== Cobertura temporal por década ===")
    df_cov = compute_temporal_coverage(df_orig.copy(), df_imp.copy(), cfg, log)

    # --- Guardar reportes ---
    drift_path = ROOT / cfg["output"]["drift_report"]
    cov_path   = ROOT / cfg["output"]["coverage_report"]
    df_drift.to_csv(drift_path, index=False)
    df_cov.to_csv(cov_path,   index=False)
    log.info(f"Reporte drift    → {drift_path.relative_to(ROOT)}")
    log.info(f"Reporte cobertura→ {cov_path.relative_to(ROOT)}")

    # --- Figuras ---
    if _HAS_MPL:
        _plot_drift(df_drift, cfg["variables"], fig_dir, cfg)
        _plot_coverage(df_cov, cfg["variables"], fig_dir, cfg)
        log.info(f"Figuras → {fig_dir.relative_to(ROOT)}/")

    # --- Evaluación de criterios ---
    warnings_found  = []
    criticals_found = []

    last_decade = df_drift[df_drift["w_start"] == df_drift["w_start"].max()]
    for _, row in last_decade.iterrows():
        psi = row["psi"]
        if psi is None:
            continue
        if psi > cfg["psi_critical"]:
            criticals_found.append(
                f"{row['variable']} ventana {row['ventana']}: PSI={psi:.4f} > {cfg['psi_critical']}"
            )
        elif psi > cfg["psi_warning"]:
            warnings_found.append(
                f"{row['variable']} ventana {row['ventana']}: PSI={psi:.4f} > {cfg['psi_warning']}"
            )

    log.info("=== Resumen de monitoreo ===")
    if criticals_found:
        for msg in criticals_found:
            log.warning(f"  [RETRAIN ALERT] {msg} → revisar reentrenamiento del modelo")
        log.info("Monitoreo completado con alertas de reentrenamiento (revisar drift_report.csv).")
    elif warnings_found:
        for msg in warnings_found:
            log.warning(f"  [WARNING]  {msg}")
        log.info("Monitoreo completado con advertencias.")
    else:
        log.info("Monitoreo completado. Sin drift significativo detectado.")
    # El monitoreo es informacional — siempre exit 0.
    # Las alertas quedan en el reporte para revisión humana.


if __name__ == "__main__":
    main()
