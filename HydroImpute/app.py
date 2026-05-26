"""
app.py — Página de inicio de HydroImpute.
Ejecutar con: streamlit run "HydroImpute/app.py"
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils import ROOT, LOGO_PATH, get_pipeline

st.set_page_config(
    page_title="HydroImpute",
    page_icon=str(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar común
# ---------------------------------------------------------------------------

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
    if pipeline is not None:
        st.success("Modelo BiGRU-opt listo")
        st.markdown(
            f"- **NSE global:** 0.621  \n"
            f"- **Dispositivo:** {pipeline.device.upper()}  \n"
            f"- **Variables:** {', '.join(pipeline.variables)}"
        )
    else:
        st.error("Modelo no disponible")
    st.divider()
    st.caption("Usa el menú de páginas para navegar.")

# ---------------------------------------------------------------------------
# Página de inicio
# ---------------------------------------------------------------------------

st.title("HydroImpute")
st.markdown(
    "Sistema de imputación de datos hidrometeorológicos basado en el modelo "
    "**BiGRU-opt** entrenado con datos CONAGUA/SMN del estado de Sinaloa "
    "(1960–2026, 173 estaciones climatológicas)."
)

st.divider()

# ── Métricas de portada ──────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

try:
    idx = pd.read_csv(ROOT / "data/processed/_index_processed.csv")
    n_sta = idx["station"].nunique()
    fecha_ini = idx["fecha_inicio"].min()[:7]
    fecha_fin = idx["fecha_fin"].max()[:7]
except Exception:
    n_sta, fecha_ini, fecha_fin = 173, "1960-01", "2026-02"

col1.metric("Estaciones", f"{n_sta}")
col2.metric("Período", f"{fecha_ini} → {fecha_fin}")
col3.metric("NSE global (BiGRU-opt)", "0.621")

try:
    cov = pd.read_csv(ROOT / "reports/validacion_estadistica/metricas_imputacion.csv")
    avg_cov = round(cov["tasa_cobertura"].mean() * 100, 1)
    col4.metric("Cobertura de imputación", f"{avg_cov} %")
except Exception:
    col4.metric("Cobertura de imputación", "≥ 99 %")

st.divider()

# ── Descripción de páginas ───────────────────────────────────────────────────
st.subheader("Páginas disponibles")

p1, p2 = st.columns(2)
with p1:
    st.markdown("#### Dashboard")
    st.markdown(
        "Estado actual del pipeline: qué etapas se han ejecutado, "
        "cuándo fue la última ejecución y métricas clave de cada etapa."
    )
    st.markdown("#### Pipeline")
    st.markdown(
        "Ejecuta el pipeline completo (12 etapas) o etapas individuales "
        "con registro de actividad en tiempo real."
    )
    st.markdown("#### Datos propios")
    st.markdown(
        "Carga tu propio dataset (CSV, Excel, Parquet o archivos .txt de CONAGUA) "
        "y ejecuta el pipeline completo desde la etapa correspondiente."
    )

with p2:
    st.markdown("#### Resultados")
    st.markdown(
        "Visualiza las figuras y reportes generados por el pipeline: "
        "Quality Gate, validación estadística, drift PSI y estadísticas finales."
    )
    st.markdown("#### Configuración")
    st.markdown(
        "Edita los parámetros de cada módulo del pipeline (límites físicos, "
        "ventanas, umbrales) sin necesidad de abrir archivos YAML."
    )

st.divider()

# ── Rendimiento del modelo ───────────────────────────────────────────────────
st.subheader("Rendimiento del modelo BiGRU-opt")
st.markdown("Backtesting 4-fold, mecanismo MCAR 20 %:")

perf = pd.DataFrame({
    "Variable": ["tmax", "tmin", "evap", "precip", "Global"],
    "NSE":      [0.847,  0.931,  0.648,  0.056,    0.621],
})
st.dataframe(perf, hide_index=True, use_container_width=False)

st.caption(
    "El NSE de precip es bajo por el mecanismo MNAR estructural de las "
    "estaciones pluviométricas. tmax y tmin muestran excelente recuperación."
)
