"""
validate_imputation.py
======================
Validación Estadística post-imputación — Etapa 10 del pipeline (RES-36 / RES-135 / RES-138)

Compara el dataset original (con NaN) contra el dataset imputado para verificar
que la imputación preserve las propiedades estadísticas de las series.

Métricas calculadas
-------------------
- Cobertura        : NaN rellenados vs. NaN originales por variable/estación
- KS-test          : Kolmogorov-Smirnov entre distribución observada e imputada (RES-135)
- Correlaciones    : Pearson inter-variable antes y después (RES-138)
- Límites físicos  : ningún valor imputado fuera de rango (CRÍTICO)
- tmax >= tmin     : sin inversiones tras imputación (CRÍTICO)
- KPSS             : preservación de estacionariedad post-imputación (WARNING)
- Estadísticos básicos: media, std, min, max antes/después por variable

Uso
---
    python "Validación Estadística/validate_imputation.py"
    python "Validación Estadística/validate_imputation.py" --config ruta/config.yaml
"""

from __future__ import annotations

import argparse
import logging
import pickle
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import ks_2samp
from statsmodels.tsa.stattools import kpss

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
    return logging.getLogger("validate_imputation")


# ---------------------------------------------------------------------------
# Métricas de cobertura
# ---------------------------------------------------------------------------

def compute_coverage(df_orig: pd.DataFrame, df_imp: pd.DataFrame,
                     variables: list[str], col_sta: str,
                     log: logging.Logger) -> pd.DataFrame:
    """Calcula NaN originales, rellenados y residuales por variable y estación."""
    rows = []
    for var in variables:
        nan_orig  = df_orig[var].isna().sum()
        nan_after = df_imp[var].isna().sum()
        filled    = nan_orig - nan_after
        rate      = filled / nan_orig if nan_orig > 0 else 1.0
        log.info(
            f"  {var:6s}: {nan_orig:>8,} NaN originales → "
            f"{nan_after:>8,} residuales  ({filled:,} rellenados, {rate:.1%})"
        )
        rows.append({
            "variable": var, "estacion": "_GLOBAL_",
            "nan_original": nan_orig, "nan_rellenados": filled,
            "nan_residual": nan_after, "tasa_cobertura": round(rate, 4),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# KS-test (RES-135)
# ---------------------------------------------------------------------------

def compute_ks_test(df_orig: pd.DataFrame, df_imp: pd.DataFrame,
                    variables: list[str], significance: float,
                    log: logging.Logger) -> pd.DataFrame:
    """
    Compara la distribución de los valores imputados (posiciones que eran NaN)
    contra los valores observados originales mediante KS de dos muestras.
    Un p-value bajo indica que los imputados tienen una distribución distinta.
    """
    rows = []
    for var in variables:
        was_nan    = df_orig[var].isna()
        observed   = df_orig[var].dropna().values
        imputed    = df_imp.loc[was_nan, var].dropna().values

        if len(imputed) < 10:
            log.info(f"  {var:6s}: KS-test omitido (< 10 valores imputados)")
            rows.append({
                "variable": var, "n_observed": len(observed),
                "n_imputed": len(imputed), "ks_statistic": None,
                "p_value": None, "resultado": "OMITIDO",
            })
            continue

        stat, p = ks_2samp(observed, imputed)
        ok    = p > significance
        level = "OK     " if ok else "WARNING"
        log.info(
            f"  [{level}] KS-test {var}: D={stat:.4f}, p={p:.4f} "
            f"({'similar' if ok else 'distribución distinta'})"
        )
        rows.append({
            "variable": var, "n_observed": len(observed),
            "n_imputed": len(imputed), "ks_statistic": round(stat, 6),
            "p_value": round(p, 6),
            "resultado": "PASS" if ok else "WARNING",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Correlaciones inter-variable (RES-138)
# ---------------------------------------------------------------------------

def compute_correlations(df_orig: pd.DataFrame, df_imp: pd.DataFrame,
                         variables: list[str],
                         log: logging.Logger) -> pd.DataFrame:
    """Calcula correlaciones Pearson entre variables antes y después de imputar."""
    rows = []
    vars_present = [v for v in variables if v in df_orig.columns]
    for i, v1 in enumerate(vars_present):
        for v2 in vars_present[i + 1:]:
            corr_orig = df_orig[v1].corr(df_orig[v2])
            corr_imp  = df_imp[v1].corr(df_imp[v2])
            delta     = corr_imp - corr_orig
            log.info(
                f"  corr({v1},{v2}): "
                f"antes={corr_orig:.4f}  después={corr_imp:.4f}  Δ={delta:+.4f}"
            )
            rows.append({
                "par": f"{v1}-{v2}",
                "corr_original": round(corr_orig, 6),
                "corr_imputado": round(corr_imp, 6),
                "delta": round(delta, 6),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Estadísticos descriptivos
# ---------------------------------------------------------------------------

def compute_basic_stats(df_orig: pd.DataFrame, df_imp: pd.DataFrame,
                        variables: list[str],
                        log: logging.Logger) -> pd.DataFrame:
    """Media, std, min, max antes y después de la imputación por variable."""
    rows = []
    for var in variables:
        o = df_orig[var].dropna()
        i = df_imp[var].dropna()
        log.info(
            f"  {var:6s}: mean {o.mean():.3f}→{i.mean():.3f}  "
            f"std {o.std():.3f}→{i.std():.3f}  "
            f"min {o.min():.3f}→{i.min():.3f}  "
            f"max {o.max():.3f}→{i.max():.3f}"
        )
        rows.append({
            "variable": var,
            "mean_orig": round(o.mean(), 4),  "mean_imp": round(i.mean(), 4),
            "std_orig":  round(o.std(), 4),   "std_imp":  round(i.std(), 4),
            "min_orig":  round(o.min(), 4),   "min_imp":  round(i.min(), 4),
            "max_orig":  round(o.max(), 4),   "max_imp":  round(i.max(), 4),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Verificaciones críticas post-imputación
# ---------------------------------------------------------------------------

def check_physical_limits_imputed(df_imp: pd.DataFrame, variables: list[str],
                                   limits: dict,
                                   log: logging.Logger) -> tuple[bool, list[dict]]:
    rows = []
    passed = True
    for var in variables:
        if var not in limits or var not in df_imp.columns:
            continue
        lo, hi = limits[var].get("min"), limits[var].get("max")
        col    = df_imp[var].dropna()
        n_low  = int((col < lo).sum()) if lo is not None else 0
        n_high = int((col > hi).sum()) if hi is not None else 0
        ok = (n_low + n_high) == 0
        if not ok:
            passed = False
            log.error(
                f"[CRÍTICO] physical_limits post-imputación {var}: "
                f"{n_low} < {lo}, {n_high} > {hi}"
            )
        else:
            log.info(f"[OK]      physical_limits post-imputación {var}: sin violaciones")
        rows.append({
            "criterio": "physical_limits_imputed", "variable": var,
            "resultado": "PASS" if ok else "FAIL",
            "detalle": f"n_below={n_low}, n_above={n_high}",
        })
    return passed, rows


def check_tmax_gte_tmin_imputed(df_imp: pd.DataFrame,
                                 log: logging.Logger) -> tuple[bool, list[dict]]:
    if "tmax" not in df_imp.columns or "tmin" not in df_imp.columns:
        return True, []
    both     = df_imp[["tmax", "tmin"]].dropna()
    inverted = int((both["tmax"] < both["tmin"]).sum())
    passed   = inverted == 0
    if not passed:
        log.error(
            f"[CRÍTICO] tmax_gte_tmin post-imputación: {inverted} pares invertidos."
        )
    else:
        log.info("[OK]      tmax_gte_tmin post-imputación: sin inversiones")
    return passed, [{
        "criterio": "tmax_gte_tmin_imputed", "variable": "tmax/tmin",
        "resultado": "PASS" if passed else "FAIL",
        "detalle": f"pares_invertidos={inverted}",
    }]


def check_kpss_post(df_imp: pd.DataFrame, col_sta: str, variables: list[str],
                    significance: float, station_threshold: float,
                    log: logging.Logger) -> list[dict]:
    rows = []
    for var in variables:
        if var not in df_imp.columns:
            continue
        preserved, total = 0, 0
        for _, grp in df_imp.groupby(col_sta):
            series = grp[var].dropna()
            if len(series) < 30:
                continue
            try:
                _, p_val, _, _ = kpss(series.values, regression="c", nlags="auto")
                total += 1
                if p_val > significance:
                    preserved += 1
            except Exception:
                pass
        rate  = preserved / total if total > 0 else 0.0
        ok    = rate >= station_threshold
        level = "OK     " if ok else "WARNING"
        log.info(
            f"  [{level}] KPSS post-imputación {var}: "
            f"{preserved}/{total} estacionarias ({rate:.1%})"
        )
        rows.append({
            "criterio": "kpss_post_imputation", "variable": var,
            "resultado": "PASS" if ok else "WARNING",
            "detalle": f"preserved={preserved}, total={total}, rate={rate:.4f}",
        })
    return rows


# ---------------------------------------------------------------------------
# Visualizaciones
# ---------------------------------------------------------------------------

def plot_validation(df_orig: pd.DataFrame, df_imp: pd.DataFrame,
                    df_cov: pd.DataFrame, df_ks: pd.DataFrame,
                    df_corr: pd.DataFrame, variables: list[str],
                    out_dir: Path, log: logging.Logger, cfg: dict) -> None:
    """Genera figuras de validación estadística y las guarda en out_dir/figuras/."""
    if not _HAS_MPL:
        log.warning("matplotlib no disponible — figuras omitidas.")
        return

    fig_dir = out_dir / "figuras"
    fig_dir.mkdir(parents=True, exist_ok=True)

    # ── Fig 1: Cobertura de imputación ───────────────────────────────────────
    cov_pct = df_cov["tasa_cobertura"] * 100
    target  = cfg.get("coverage_target_pct", 99)
    colors  = ["#2e7d32" if v >= target else "#ef6c00" if v >= target - 4 else "#c62828"
               for v in cov_pct]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars    = ax.bar(df_cov["variable"].tolist(), cov_pct, color=colors)
    ax.axhline(target, color="#c62828", linestyle="--", linewidth=1.2,
               label=f"Objetivo {target}%")
    ax.set_ylabel("Cobertura de imputación (%)")
    ax.set_title("Cobertura de imputación por variable")
    ax.set_ylim(target - 5, target + 2)
    ax.legend()
    for bar, val in zip(bars, cov_pct):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                f"{val:.2f}%", ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    fig.savefig(fig_dir / "val_cobertura.png", dpi=150)
    plt.close(fig)
    log.info(f"  figura: {(fig_dir / 'val_cobertura.png').relative_to(ROOT)}")

    # ── Fig 2: Distribución observada vs imputada (KDE) ─────────────────────
    from scipy.stats import gaussian_kde

    n_vars = len(variables)
    fig, axes = plt.subplots(1, n_vars, figsize=(4.5 * n_vars, 4))
    if n_vars == 1:
        axes = [axes]
    for ax, var in zip(axes, variables):
        if var not in df_orig.columns:
            continue
        was_nan  = df_orig[var].isna()
        observed = df_orig[var].dropna().values
        imputed  = df_imp.loc[was_nan, var].dropna().values

        if len(observed) < 2:
            ax.set_title(var, fontsize=11, fontweight="bold")
            ax.text(0.5, 0.5, "Sin datos observados", ha="center", va="center",
                    transform=ax.transAxes, color="gray")
            ax.set_axis_off()
            continue

        # rango común para el eje x
        candidates = [observed] + ([imputed] if len(imputed) > 0 else [])
        x_min = min(a.min() for a in candidates)
        x_max = max(a.max() for a in candidates)
        if x_min == x_max:
            x_min -= 0.5; x_max += 0.5
        x_grid = np.linspace(x_min, x_max, 400)

        # KDE observados
        kde_obs = gaussian_kde(observed, bw_method="scott")
        ax.fill_between(x_grid, kde_obs(x_grid), alpha=0.35, color="#1565c0")
        ax.plot(x_grid, kde_obs(x_grid), color="#1565c0", linewidth=1.5,
                label=f"Observado (μ={observed.mean():.1f})")
        ax.axvline(observed.mean(), color="#1565c0", linestyle="--",
                   linewidth=1, alpha=0.8)

        # KDE imputados
        if len(imputed) >= 10:
            kde_imp = gaussian_kde(imputed, bw_method="scott")
            ax.fill_between(x_grid, kde_imp(x_grid), alpha=0.35, color="#ef6c00")
            ax.plot(x_grid, kde_imp(x_grid), color="#ef6c00", linewidth=1.5,
                    label=f"Imputado (μ={imputed.mean():.1f})")
            ax.axvline(imputed.mean(), color="#ef6c00", linestyle="--",
                       linewidth=1, alpha=0.8)

        ax.set_title(var, fontsize=11, fontweight="bold")
        ax.set_xlabel("Valor")
        ax.set_ylabel("Densidad")
        ax.legend(fontsize=7.5)
        ax.set_xlim(x_min, x_max)

    fig.suptitle("Distribución KDE: observado vs imputado\n"
                 "(líneas punteadas = media; diferencias esperadas por mecanismo MNAR)",
                 fontsize=11)
    plt.tight_layout()
    fig.savefig(fig_dir / "val_distribucion.png", dpi=150)
    plt.close(fig)
    log.info(f"  figura: {(fig_dir / 'val_distribucion.png').relative_to(ROOT)}")

    # ── Fig 3: Correlaciones antes/después ──────────────────────────────────
    if not df_corr.empty:
        x   = list(range(len(df_corr)))
        w   = 0.35
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar([i - w / 2 for i in x], df_corr["corr_original"], w,
               label="Original", color="#1565c0", alpha=0.85)
        ax.bar([i + w / 2 for i in x], df_corr["corr_imputado"], w,
               label="Imputado", color="#ef6c00", alpha=0.85)
        ax.set_xticks(x)
        ax.set_xticklabels(df_corr["par"].tolist(), rotation=30, ha="right")
        ax.set_ylabel("Correlación de Pearson")
        ax.set_title("Correlaciones inter-variable antes/después de imputar")
        ax.axhline(0, color="gray", linewidth=0.8)
        ax.legend()
        plt.tight_layout()
        fig.savefig(fig_dir / "val_correlaciones.png", dpi=150)
        plt.close(fig)
        log.info(f"  figura: {(fig_dir / 'val_correlaciones.png').relative_to(ROOT)}")

    # ── Fig 4: KS-statistic por variable ────────────────────────────────────
    if not df_ks.empty and "ks_statistic" in df_ks.columns:
        df_ks_plot = df_ks.dropna(subset=["ks_statistic"])
        if not df_ks_plot.empty:
            COLOR = {"PASS": "#2e7d32", "WARNING": "#ef6c00", "FAIL": "#c62828"}
            colors_ks = [COLOR.get(r["resultado"], "#90a4ae")
                         for _, r in df_ks_plot.iterrows()]
            fig, ax = plt.subplots(figsize=(7, 4))
            bars = ax.bar(df_ks_plot["variable"].tolist(),
                          df_ks_plot["ks_statistic"], color=colors_ks)
            ax.set_ylabel("Estadístico KS (D)")
            ax.set_title("KS-test: distancia distribución observada vs imputada\n"
                         "(menor es mejor; WARNING esperado por mecanismo MNAR)")
            ax.set_ylim(0, 1.05)
            for bar in bars:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                        f"{bar.get_height():.3f}", ha="center", va="bottom", fontsize=9)
            plt.tight_layout()
            fig.savefig(fig_dir / "val_ks_test.png", dpi=150)
            plt.close(fig)
            log.info(f"  figura: {(fig_dir / 'val_ks_test.png').relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validación estadística post-imputación — CRISP-ML(Q)"
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args()

    cfg = _load_config(args.config)
    log = _setup_logging(cfg)

    log.info("=" * 60)
    log.info("INICIO — Validación Estadística post-imputación")
    log.info("=" * 60)

    orig_path = ROOT / cfg["input"]["original"]
    imp_path  = ROOT / cfg["input"]["imputed"]

    for p, label in [(orig_path, "original"), (imp_path, "imputado")]:
        if not p.exists():
            log.error(f"Dataset {label} no encontrado: {p}")
            sys.exit(1)

    df_orig = pd.read_parquet(orig_path)
    df_imp  = pd.read_parquet(imp_path)
    log.info(f"Dataset original : {orig_path.relative_to(ROOT)}  ({len(df_orig):,} filas)")
    log.info(f"Dataset imputado : {imp_path.relative_to(ROOT)}  ({len(df_imp):,} filas)")

    # dataset_final.parquet está normalizado — invertir escala para comparar
    # en unidades físicas (las mismas que usa dataset_imputado.parquet)
    scalers_dir = ROOT / cfg["scalers"]["dir"]
    scalers: dict = {}
    for var in cfg["variables"]:
        pkl = scalers_dir / f"{cfg['scalers']['prefix']}{var}.pkl"
        if pkl.exists():
            with pkl.open("rb") as f:
                scalers[var] = pickle.load(f)
    if scalers:
        log.info(f"Scalers cargados para inverse-transform: {list(scalers.keys())}")
        for var in cfg["variables"]:
            if var not in scalers or var not in df_orig.columns:
                continue
            vals = df_orig[var].values.copy()
            valid = ~np.isnan(vals)
            if valid.any():
                vals[valid] = scalers[var].inverse_transform(
                    vals[valid].reshape(-1, 1)
                ).ravel()
                df_orig[var] = vals

    variables  = cfg["variables"]
    col_sta    = cfg["columns"]["station"]
    out_dir    = ROOT / cfg["output"]["report_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    critical_failures = 0

    # ── Cobertura ────────────────────────────────────────────────────────────
    log.info("-" * 40)
    log.info("Cobertura de imputación")
    log.info("-" * 40)
    df_cov = compute_coverage(df_orig, df_imp, variables, col_sta, log)
    df_cov.to_csv(ROOT / cfg["output"]["metrics"], index=False)

    # ── KS-test (RES-135) ───────────────────────────────────────────────────
    log.info("-" * 40)
    log.info("KS-test: distribución observada vs. imputada")
    log.info("-" * 40)
    df_ks = compute_ks_test(
        df_orig, df_imp, variables, cfg["ks_significance"], log
    )
    df_ks.to_csv(ROOT / cfg["output"]["ks_report"], index=False)

    # ── Correlaciones (RES-138) ─────────────────────────────────────────────
    log.info("-" * 40)
    log.info("Correlaciones inter-variable antes/después")
    log.info("-" * 40)
    df_corr = compute_correlations(df_orig, df_imp, variables, log)
    df_corr.to_csv(ROOT / cfg["output"]["corr_report"], index=False)

    # ── Figuras ──────────────────────────────────────────────────────────────
    log.info("-" * 40)
    log.info("Generando figuras")
    log.info("-" * 40)
    plot_validation(df_orig, df_imp, df_cov, df_ks, df_corr, variables, out_dir, log, cfg)

    # ── Estadísticos descriptivos ────────────────────────────────────────────
    log.info("-" * 40)
    log.info("Estadísticos descriptivos antes/después")
    log.info("-" * 40)
    compute_basic_stats(df_orig, df_imp, variables, log)

    # ── Criterios CRÍTICOS ───────────────────────────────────────────────────
    log.info("-" * 40)
    log.info("Criterios CRÍTICOS post-imputación")
    log.info("-" * 40)
    passed, _ = check_physical_limits_imputed(
        df_imp, variables, cfg["physical_limits"], log
    )
    if not passed:
        critical_failures += 1

    passed, _ = check_tmax_gte_tmin_imputed(df_imp, log)
    if not passed:
        critical_failures += 1

    # ── KPSS post-imputación (WARNING) ───────────────────────────────────────
    log.info("-" * 40)
    log.info("KPSS post-imputación (WARNING)")
    log.info("-" * 40)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        check_kpss_post(df_imp, col_sta, variables, cfg["kpss_significance"],
                        cfg["kpss_station_threshold"], log)

    # ── Resultado final ──────────────────────────────────────────────────────
    log.info("=" * 60)
    if critical_failures > 0:
        log.error(
            f"VALIDACIÓN FALLIDA — {critical_failures} criterio(s) crítico(s). "
            "Revisa impute.py o los scalers."
        )
        log.info("=" * 60)
        sys.exit(1)
    else:
        log.info("VALIDACIÓN SUPERADA — dataset imputado estadísticamente válido.")
        log.info(f"Reportes en: {out_dir.relative_to(ROOT)}")
        log.info("=" * 60)


if __name__ == "__main__":
    main()
