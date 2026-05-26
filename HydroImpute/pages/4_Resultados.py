"""Resultados — figuras y reportes generados por el pipeline."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from utils import ROOT, LOGO_PATH, get_pipeline

st.set_page_config(page_title="Resultados · HydroImpute", layout="wide")

with st.sidebar:
    st.image(str(LOGO_PATH), width=110)
    st.title("HydroImpute")
    st.caption(
        "Imputación Generativa Hidrometeorológica\n"
        "Laboratorio de Geomática y Teledetección\n"
        "TECNM Campus Culiacán"
    )
    st.divider()
    pipeline = get_pipeline()
    if pipeline:
        st.success("Modelo BiGRU-opt listo")
    else:
        st.error("Modelo no disponible")

st.title("Resultados del pipeline")
st.markdown("Figuras y reportes generados por cada etapa.")


def _show_figure(path: Path, caption: str = "") -> None:
    if path.exists():
        st.image(str(path), caption=caption, use_container_width=True)
    else:
        st.info(f"Figura no disponible: `{path.relative_to(ROOT)}`")


def _show_csv(path: Path, label: str = "") -> None:
    if path.exists():
        df = pd.read_csv(path)
        if label:
            st.markdown(f"**{label}**")
        st.dataframe(df, hide_index=True, use_container_width=True)
    else:
        st.info(f"Reporte no disponible: `{path.relative_to(ROOT)}`")


# ---------------------------------------------------------------------------
# Tabs por etapa
# ---------------------------------------------------------------------------

tab_qg, tab_val, tab_mon, tab_exp = st.tabs([
    "Etapa 8 · Quality Gate",
    "Etapa 10 · Validación",
    "Etapa 11 · Monitoreo",
    "Etapa 12 · Exportación",
])

# ── Quality Gate ─────────────────────────────────────────────────────────────
with tab_qg:
    st.subheader("Quality Gate CRISP-ML(Q)")
    fig_dir = ROOT / "reports/quality_gate/figuras"

    col1, col2 = st.columns(2)
    with col1:
        _show_figure(fig_dir / "qg_criterios.png",    "Estado por criterio")
        _show_figure(fig_dir / "qg_missing_rate.png", "Tasa de faltantes vs umbral")
    with col2:
        _show_figure(fig_dir / "qg_kpss.png", "Estacionariedad KPSS por variable")

    st.divider()
    _show_csv(ROOT / "reports/quality_gate/quality_gate_report.csv",
              "Reporte completo del Quality Gate")

# ── Validación estadística ───────────────────────────────────────────────────
with tab_val:
    st.subheader("Validación estadística post-imputación")
    fig_dir = ROOT / "reports/validacion_estadistica/figuras"

    col1, col2 = st.columns(2)
    with col1:
        _show_figure(fig_dir / "val_cobertura.png",    "Cobertura de imputación")
        _show_figure(fig_dir / "val_correlaciones.png","Correlaciones antes/después")
    with col2:
        _show_figure(fig_dir / "val_distribucion.png", "Distribución KDE observado vs imputado")
        _show_figure(fig_dir / "val_ks_test.png",      "KS-test por variable")

    st.divider()
    rep = ROOT / "reports/validacion_estadistica"
    _show_csv(rep / "metricas_imputacion.csv",         "Cobertura de imputación")
    _show_csv(rep / "ks_test_report.csv",              "KS-test")
    _show_csv(rep / "correlaciones_comparativas.csv",  "Correlaciones inter-variable")

    st.divider()
    st.subheader("Rendimiento del modelo — referencia de backtesting")
    st.caption(
        "Métricas fijas del modelo BiGRU-opt evaluadas durante el entrenamiento "
        "(backtesting 4 folds, MCAR 20 %). No varían entre ejecuciones del pipeline."
    )
    _show_figure(
        ROOT / "reports/optimizacion/figuras/mae_nse_unidades_reales.png",
        "NSE y MAE en unidades reales por variable",
    )
    _show_csv(
        ROOT / "reports/optimizacion/mae_unidades_reales.csv",
        "MAE en unidades originales (mm/día · °C)",
    )

# ── Monitoreo ────────────────────────────────────────────────────────────────
with tab_mon:
    st.subheader("Monitoreo — Drift distribucional PSI")
    fig_dir = ROOT / "reports/monitoreo/figuras"

    col1, col2 = st.columns(2)
    with col1:
        _show_figure(fig_dir / "drift_decadal.png",      "PSI por década vs referencia 1970–2000")
    with col2:
        _show_figure(fig_dir / "cobertura_temporal.png", "Cobertura de imputación por década")

    st.divider()
    rep = ROOT / "reports/monitoreo"
    _show_csv(rep / "drift_report.csv",       "Reporte de drift PSI + KS-test")
    _show_csv(rep / "cobertura_temporal.csv", "Cobertura temporal por década")

# ── Exportación ──────────────────────────────────────────────────────────────
with tab_exp:
    st.subheader("Análisis y Exportación — Estadísticas del dataset imputado")
    rep = ROOT / "reports/exportacion"
    _show_csv(rep / "export_report.csv", "Manifiesto de exportación")

    st.divider()
    excel_path = ROOT / "data/export/resumen_estadistico.xlsx"
    if excel_path.exists():
        try:
            xl = pd.ExcelFile(excel_path)
            for sheet in xl.sheet_names:
                with st.expander(f"Hoja: {sheet}"):
                    df_sheet = xl.parse(sheet)
                    st.dataframe(df_sheet, hide_index=True, use_container_width=True)
        except Exception as exc:
            st.warning(f"No se pudo leer el Excel: {exc}")
    else:
        st.info("Ejecuta la Etapa 12 para ver el resumen estadístico Excel.")

    st.divider()
    st.markdown("**Descarga**")
    import io, zipfile
    export_dir = ROOT / "data/export"
    csv_path   = export_dir / "dataset_imputado.csv"
    xlsx_path  = export_dir / "resumen_estadistico.xlsx"
    sta_dir    = export_dir / "por_estacion"

    col1, col2, col3, col4 = st.columns(4)

    if csv_path.exists():
        with open(csv_path, "rb") as f:
            col1.download_button(
                label="dataset_imputado.csv",
                data=f,
                file_name="dataset_imputado.csv",
                mime="text/csv",
                use_container_width=True,
            )
    else:
        col1.info("CSV no disponible")

    if xlsx_path.exists():
        with open(xlsx_path, "rb") as f:
            col2.download_button(
                label="resumen_estadistico.xlsx",
                data=f,
                file_name="resumen_estadistico.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    else:
        col2.info("Excel no disponible")

    if export_dir.exists() and any(export_dir.rglob("*")):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in export_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(export_dir))
        buf.seek(0)
        col3.download_button(
            label="export/ completo (.zip)",
            data=buf,
            file_name="export_completo.zip",
            mime="application/zip",
            use_container_width=True,
        )
    else:
        col3.info("ZIP no disponible")

    if sta_dir.exists() and any(sta_dir.iterdir()):
        buf_sta = io.BytesIO()
        with zipfile.ZipFile(buf_sta, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sta_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(sta_dir))
        buf_sta.seek(0)
        col4.download_button(
            label="por_estacion/ (.zip)",
            data=buf_sta,
            file_name="por_estacion.zip",
            mime="application/zip",
            use_container_width=True,
        )
    else:
        col4.info("por_estacion/ no disponible")
