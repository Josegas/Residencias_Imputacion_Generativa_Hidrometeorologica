"""Configuración — editar parámetros de los módulos del pipeline."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

from utils import ROOT, LOGO_PATH, PHYSICAL_DEFAULTS, VARIABLES, VAR_LABELS, get_pipeline

st.set_page_config(page_title="Configuración · HydroImpute", layout="wide")

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

st.title("Configuración del pipeline")
st.markdown(
    "Ajusta los parámetros relevantes de cada módulo. "
    "Los cambios se guardan en los `config.yaml` correspondientes."
)
st.warning(
    "Ejecuta las etapas afectadas en la página **Pipeline** después de guardar.",
    icon="⚠️",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_yaml(path: Path, cfg: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _limits_editor(cfg_section: dict, key_prefix: str) -> dict:
    new_limits: dict = {}
    cols = st.columns(len(VARIABLES))
    for i, var in enumerate(VARIABLES):
        lim = cfg_section.get(var, PHYSICAL_DEFAULTS[var])
        with cols[i]:
            st.markdown(f"**{VAR_LABELS[var]}**")
            lo = st.number_input(
                "Mínimo", value=float(lim["min"]), step=1.0,
                key=f"{key_prefix}_lo_{var}",
                help="Cualquier valor por debajo de este límite se convierte a NaN.",
            )
            hi = st.number_input(
                "Máximo", value=float(lim["max"]), step=1.0,
                key=f"{key_prefix}_hi_{var}",
                help="Cualquier valor por encima de este límite se convierte a NaN.",
            )
            new_limits[var] = {"min": lo, "max": hi}
    return new_limits


# ---------------------------------------------------------------------------
# Tabs por módulo (orden de etapas del pipeline)
# ---------------------------------------------------------------------------

tab_dl, tab_lim, tab_qg, tab_imp, tab_val, tab_mon, tab_exp = st.tabs([
    "Etapa 1 · Descarga",
    "Etapa 3 · Limpieza",
    "Etapa 8 · Quality Gate",
    "Etapa 9 · Imputación",
    "Etapa 10 · Validación",
    "Etapa 11 · Monitoreo",
    "Etapa 12 · Exportación",
])

# ── Etapa 1 · Descarga de datos ───────────────────────────────────────────────
with tab_dl:
    st.subheader("Descarga de datos — Etapa 1")
    st.caption(
        "Rango de claves de estación que el descargador explorará en SMN/CONAGUA. "
        "Para Sinaloa el rango estándar es 25001–25300."
    )

    cfg_path_dl = ROOT / "Obtencion de Datos Crudos/config.yaml"
    cfg_dl = _read_yaml(cfg_path_dl)

    est = cfg_dl.get("estaciones", {})
    col1, col2 = st.columns(2)
    with col1:
        rango_inicio = st.number_input(
            "Clave inicio", value=int(est.get("rango_inicio", 25001)), step=1,
            help="Primera clave de estación a explorar (ej. 25001 para Sinaloa).",
        )
    with col2:
        rango_fin = st.number_input(
            "Clave fin", value=int(est.get("rango_fin", 25300)), step=1,
            help="Última clave de estación a explorar (ej. 25300 para Sinaloa).",
        )

    if rango_inicio >= rango_fin:
        st.error("La clave de inicio debe ser menor que la clave fin.")

    st.divider()

    st.markdown("#### Conexión")
    st.caption("Ajusta si la descarga es lenta o falla por timeouts.")
    con = cfg_dl.get("conexion", {})
    col1, col2 = st.columns(2)
    with col1:
        timeout_seg = st.number_input(
            "Timeout por request (seg)",
            value=int(con.get("timeout_seg", 25)),
            min_value=5, max_value=120, step=5,
            help="Segundos de espera antes de marcar una estación como FAIL.",
        )
    with col2:
        max_workers = st.number_input(
            "Hilos paralelos",
            value=int(con.get("max_workers", 10)),
            min_value=1, max_value=20, step=1,
            help="Número de descargas simultáneas. No subir de 20 para no sobrecargar el servidor.",
        )

    if rango_inicio < rango_fin:
        if st.button("Guardar — Descarga de datos", type="primary"):
            cfg_dl.setdefault("estaciones", {})
            cfg_dl["estaciones"]["rango_inicio"] = int(rango_inicio)
            cfg_dl["estaciones"]["rango_fin"] = int(rango_fin)
            cfg_dl.setdefault("conexion", {})
            cfg_dl["conexion"]["timeout_seg"] = int(timeout_seg)
            cfg_dl["conexion"]["max_workers"] = int(max_workers)
            _write_yaml(cfg_path_dl, cfg_dl)
            st.success("Guardado en `Obtencion de Datos Crudos/config.yaml`")

# ── Etapa 3 · Limpieza ───────────────────────────────────────────────────────
with tab_lim:
    st.subheader("Limpieza y validación — Etapa 3")
    st.markdown(
        "Límites físicos aplicados durante la limpieza inicial. "
        "Valores fuera de estos rangos se convierten a `NaN` antes de normalizar."
    )
    st.caption(
        "Si trabajas con datos de otra región, ajusta estos límites para que reflejen "
        "los rangos climáticos reales. Deben ser coherentes con los límites del Quality Gate."
    )

    cfg_path_lim = ROOT / "Validacion y limpieza/config.yaml"
    cfg_lim = _read_yaml(cfg_path_lim)

    new_limits_lim = _limits_editor(cfg_lim.get("physical_limits", {}), "lim")

    if st.button("Guardar — Limpieza", type="primary"):
        cfg_lim["physical_limits"] = new_limits_lim
        _write_yaml(cfg_path_lim, cfg_lim)
        st.success("Guardado en `Validacion y limpieza/config.yaml`")

# ── Etapa 8 · Quality Gate ───────────────────────────────────────────────────
with tab_qg:
    st.subheader("Quality Gate — Etapa 8")
    st.markdown(
        "Verifica la calidad de los datos antes de imputar. "
        "Genera un reporte PASS / WARNING / FAIL por criterio."
    )

    cfg_path_qg = ROOT / "Quality Gate/config.yaml"
    cfg_qg = _read_yaml(cfg_path_qg)

    st.markdown("#### Límites físicos")
    st.caption("Registros fuera de estos rangos se marcan como anomalías en el reporte.")
    new_limits_qg = _limits_editor(cfg_qg.get("physical_limits", {}), "qg")

    st.divider()

    st.markdown("#### Umbrales de datos faltantes")
    st.caption(
        "Si una estación supera este porcentaje de faltantes, el Quality Gate emite WARNING. "
        "evap tiene umbral más alto porque su ausencia es estructural en muchas estaciones."
    )
    mr = cfg_qg.get("missing_rate_thresholds", {})
    col1, col2, col3, col4 = st.columns(4)
    new_mr = {
        "precip": col1.slider("Precip.",  0.0, 1.0, float(mr.get("precip", 0.60)), 0.05,
                              help="Umbral de faltantes para precipitación."),
        "evap":   col2.slider("Evap.",    0.0, 1.0, float(mr.get("evap",   0.85)), 0.05,
                              help="Umbral de faltantes para evaporación."),
        "tmax":   col3.slider("T. máx.", 0.0, 1.0, float(mr.get("tmax",   0.60)), 0.05,
                              help="Umbral de faltantes para temperatura máxima."),
        "tmin":   col4.slider("T. mín.", 0.0, 1.0, float(mr.get("tmin",   0.60)), 0.05,
                              help="Umbral de faltantes para temperatura mínima."),
    }

    if st.button("Guardar — Quality Gate", type="primary"):
        cfg_qg["physical_limits"] = new_limits_qg
        cfg_qg["missing_rate_thresholds"] = new_mr
        _write_yaml(cfg_path_qg, cfg_qg)
        st.success("Guardado en `Quality Gate/config.yaml`")

# ── Etapa 9 · Imputación Generativa ──────────────────────────────────────────
with tab_imp:
    st.subheader("Imputación Generativa — Etapa 9")

    cfg_path_imp = ROOT / "Imputación Generativa/config.yaml"
    cfg_imp = _read_yaml(cfg_path_imp)

    st.markdown("#### Límites físicos")
    st.caption(
        "Rango de valores válidos para cada variable. "
        "Ajusta si trabajas con datos de una región distinta a Sinaloa."
    )
    new_limits_imp = _limits_editor(cfg_imp.get("physical_limits", {}), "imp")

    st.divider()

    st.markdown("#### Hardware")
    inf = cfg_imp.get("inference", {})
    col1, col2 = st.columns(2)
    device_options = ["auto", "cpu", "cuda"]
    cur_device = inf.get("device", "auto")
    new_device = col1.selectbox(
        "Dispositivo de cómputo",
        options=device_options,
        index=device_options.index(cur_device) if cur_device in device_options else 0,
        help="'auto' elige GPU si está disponible. Usa 'cpu' si no tienes GPU o 'cuda' para forzar GPU.",
    )
    new_batch = col2.number_input(
        "Tamaño de lote (batch_size)",
        value=int(inf.get("batch_size", 512)),
        min_value=32, max_value=2048, step=32,
        help="Cuántas ventanas procesa el modelo a la vez. "
             "Reduce a 256 o 128 si aparece error de memoria en GPU.",
    )

    st.divider()

    st.markdown("#### Huecos de datos")
    seq = cfg_imp.get("sequence", {})
    new_gap = st.number_input(
        "Máximo hueco a cubrir (días)",
        value=int(seq.get("max_gap_days", 365)),
        min_value=30, max_value=730, step=1,
        help="Huecos consecutivos de faltantes más largos que este valor se dejan como NaN residuales.",
    )

    st.divider()

    st.markdown("#### Información del modelo")
    window_size = int(seq.get("window_size", 30))
    st.info(
        f"**Ventana del modelo:** {window_size} días  —  "
        "Este valor está fijado por el entrenamiento y no puede cambiarse sin reentrenar BiGRU-opt.",
        icon="ℹ️",
    )

    if st.button("Guardar — Imputación Generativa", type="primary"):
        cfg_imp["physical_limits"] = new_limits_imp
        cfg_imp.setdefault("inference", {}).update({"device": new_device, "batch_size": new_batch})
        cfg_imp.setdefault("sequence", {})["max_gap_days"] = new_gap
        _write_yaml(cfg_path_imp, cfg_imp)
        st.success("Guardado en `Imputación Generativa/config.yaml`")
        st.cache_resource.clear()

# ── Etapa 10 · Validación Estadística ────────────────────────────────────────
with tab_val:
    st.subheader("Validación Estadística — Etapa 10")
    st.markdown(
        "Compara estadísticamente los datos antes y después de la imputación "
        "para verificar que los valores imputados sean coherentes con los observados."
    )

    cfg_path_val = ROOT / "Validación Estadística/config.yaml"
    cfg_val = _read_yaml(cfg_path_val)

    st.markdown("#### Límites físicos")
    st.caption(
        "Deben coincidir con los límites del módulo de Imputación Generativa. "
        "Se usan para verificar que los valores post-imputación sean válidos."
    )
    new_limits_val = _limits_editor(cfg_val.get("physical_limits", {}), "val")

    st.divider()

    st.markdown("#### Cobertura mínima esperada")
    new_cov_val = st.slider(
        "Cobertura objetivo (%)", 80, 100,
        int(cfg_val.get("coverage_target_pct", 99)), 1,
        help="Porcentaje mínimo de NaN que deben ser rellenados para que la etapa sea PASS.",
    )

    if st.button("Guardar — Validación Estadística", type="primary"):
        cfg_val["physical_limits"] = new_limits_val
        cfg_val["coverage_target_pct"] = new_cov_val
        _write_yaml(cfg_path_val, cfg_val)
        st.success("Guardado en `Validación Estadística/config.yaml`")

# ── Etapa 11 · Monitoreo ─────────────────────────────────────────────────────
with tab_mon:
    st.subheader("Monitoreo del modelo — Etapa 11")
    st.markdown(
        "Detecta si la distribución de los datos actuales se aleja del período histórico "
        "de referencia. Un drift alto puede indicar que el modelo necesita reentrenamiento."
    )

    cfg_path_mon = ROOT / "Monitoreo/config.yaml"
    cfg_mon = _read_yaml(cfg_path_mon)

    st.markdown("#### Período de referencia climático")
    st.caption(
        "Todas las comparaciones de distribución se hacen contra este rango. "
        "1970–2000 es el período estándar de la OMM. "
        "Cámbialo solo si tienes una justificación climática específica."
    )
    ref = cfg_mon.get("reference_window", {"start": 1970, "end": 2000})
    col1, col2 = st.columns(2)
    new_ref_start = col1.number_input(
        "Año inicio", value=int(ref["start"]),
        min_value=1960, max_value=2010, step=1,
        help="Primer año del período considerado como 'clima normal'. Estándar OMM: 1970.",
    )
    new_ref_end = col2.number_input(
        "Año fin", value=int(ref["end"]),
        min_value=1960, max_value=2020, step=1,
        help="Último año del período de referencia. Estándar OMM: 2000.",
    )

    st.divider()

    st.markdown("#### Cobertura mínima esperada")
    new_cov_target = st.slider(
        "Cobertura objetivo (%)", 80, 100,
        int(cfg_mon.get("coverage_target_pct", 99)), 1,
        help="Porcentaje mínimo de NaN que el modelo debe rellenar para considerar la imputación exitosa.",
    )

    if st.button("Guardar — Monitoreo", type="primary"):
        cfg_mon["reference_window"] = {"start": new_ref_start, "end": new_ref_end}
        cfg_mon["coverage_target_pct"] = new_cov_target
        _write_yaml(cfg_path_mon, cfg_mon)
        st.success("Guardado en `Monitoreo/config.yaml`")

# ── Etapa 12 · Exportación ───────────────────────────────────────────────────
with tab_exp:
    st.subheader("Análisis y Exportación — Etapa 12")
    st.caption("Formato del archivo CSV exportado al finalizar el pipeline.")

    cfg_path_exp = ROOT / "Análisis y Exportación/config.yaml"
    cfg_exp = _read_yaml(cfg_path_exp)

    sep_options = {",": "Coma  ,  (estándar internacional)", ";": "Punto y coma  ;  (Excel europeo)"}
    cur_sep = cfg_exp.get("csv_separator", ",")
    new_sep = st.radio(
        "Separador CSV",
        options=list(sep_options.keys()),
        format_func=lambda x: sep_options[x],
        index=0 if cur_sep == "," else 1,
        help="Usa punto y coma si tu Excel abre los CSV con todas las columnas en una sola celda.",
    )

    if st.button("Guardar — Exportación", type="primary"):
        cfg_exp["csv_separator"] = new_sep
        _write_yaml(cfg_path_exp, cfg_exp)
        st.success("Guardado en `Análisis y Exportación/config.yaml`")
