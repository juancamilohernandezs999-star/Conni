from __future__ import annotations

import base64
import hashlib
from html import escape
from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from conni.data import ConniData, WorkbookValidationError, load_master, normalize_label  # noqa: E402
from conni.export import analytics_workbook  # noqa: E402
from conni.metrics import (  # noqa: E402
    categorical_count,
    filter_period_and_area,
    gender_by_area,
    plant_by_area,
    plant_metrics,
    quality_summary,
    socio_metrics,
    vacation_by_area,
    vacation_period_distribution,
)


COLORS = {
    "blue": "#005DA8",
    "bright": "#0088C8",
    "navy": "#002F56",
    "cyan": "#00A6CE",
    "yellow": "#FFCF00",
    "green": "#16A36A",
    "red": "#D94A56",
    "muted": "#6D849A",
}
PALETTE = ["#00A6CE", "#005DA8", "#FFCF00", "#16A36A", "#7B61C9", "#F08A5D", "#6D849A"]
WINDOWS = ("Carga de información", "Planta y vacaciones", "Perfil sociodemográfico")
WINDOW_LABELS = {
    "Carga de información": "01  Carga de información",
    "Planta y vacaciones": "02  Planta y vacaciones",
    "Perfil sociodemográfico": "03  Perfil sociodemográfico",
}
WINDOW_SLUGS = {
    "Carga de información": "carga",
    "Planta y vacaciones": "planta",
    "Perfil sociodemográfico": "perfil",
}
SLUG_WINDOWS = {slug: page for page, slug in WINDOW_SLUGS.items()}


def image_data_uri(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mime = "image/png" if suffix == "png" else "image/x-icon"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


st.set_page_config(
    page_title="Conni | Inteligencia de Talento",
    page_icon=str(ROOT / "assets" / "favicon.ico") if (ROOT / "assets" / "favicon.ico").exists() else "📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(f"<style>{(ROOT / 'assets' / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def sync_navigation_from_url() -> None:
    requested = st.query_params.get("view")
    if isinstance(requested, list):
        requested = requested[0] if requested else None
    if requested in SLUG_WINDOWS and requested != st.session_state.get("_last_query_view"):
        st.session_state.page = SLUG_WINDOWS[requested]
        st.session_state._last_query_view = requested
    if st.session_state.get("page") not in WINDOWS:
        st.session_state.page = WINDOWS[0]


def sync_url_from_navigation() -> None:
    page = st.session_state.get("page", WINDOWS[0])
    slug = WINDOW_SLUGS.get(page, "carga")
    st.session_state._last_query_view = slug
    st.query_params["view"] = slug


def topbar() -> None:
    logo = image_data_uri(ROOT / "assets" / "logo_colsubsidio.png")
    st.markdown(
        f"""
        <header class="app-topbar">
          <a class="brand-home-link" href="?view=carga" target="_self" title="Volver a Carga de información">
            <div class="brand-lockup">
              <img class="brand-mark" src="{logo}" alt="Colsubsidio">
              <div class="brand-copy">
                <span class="brand-name">Colsubsidio</span>
                <span class="brand-area">FINANZAS CORPORATIVAS</span>
              </div>
            </div>
          </a>
          <div class="topbar-context">
            <a class="topbar-home" href="?view=carga" target="_self">⌂ Inicio</a>
            <span class="topbar-code">SF_FC_GP_001</span>
            <span class="topbar-label">Inteligencia de Talento</span>
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def window_navigation(data: ConniData | None) -> None:
    readiness = "Archivo validado · ventanas habilitadas" if data is not None else "Carga requerida · sin datos precargados"
    readiness_class = "ready" if data is not None else "waiting"
    st.markdown(
        f"<div class='window-nav-heading'><span>NAVEGACIÓN PRINCIPAL</span><i class='{readiness_class}'>{readiness}</i></div>",
        unsafe_allow_html=True,
    )
    st.radio(
        "Ventanas de la aplicación",
        WINDOWS,
        format_func=lambda page: WINDOW_LABELS[page],
        horizontal=True,
        key="page",
        label_visibility="collapsed",
        on_change=sync_url_from_navigation,
    )


def kpi_cards(items: list[tuple[str, str, str, str]]) -> None:
    cards = "".join(
        f'<div class="kpi-card" style="--accent:{accent}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-note">{note}</div>'
        "</div>"
        for label, value, note, accent in items
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)


def chart_style(fig: go.Figure, height: int = 390) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=22, r=22, t=58, b=28),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Arial", color="#143B62", size=12),
        title_font=dict(size=16, color=COLORS["navy"]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(bgcolor="#FFFFFF", font_color="#143B62"),
    )
    fig.update_xaxes(showgrid=False, linecolor="#DCE8F1")
    fig.update_yaxes(gridcolor="#EAF1F6", zeroline=False)
    return fig


def go_to(page: str) -> None:
    target = page if page in WINDOWS else WINDOWS[0]
    st.session_state.page = target
    slug = WINDOW_SLUGS[target]
    st.session_state._last_query_view = slug
    st.query_params["view"] = slug


def clear_loaded_data() -> None:
    for key in ("uploaded_data", "uploaded_fingerprint", "upload_error"):
        st.session_state.pop(key, None)
    st.session_state.uploader_version = st.session_state.get("uploader_version", 0) + 1
    go_to("Carga de información")


def active_data() -> ConniData | None:
    value = st.session_state.get("uploaded_data")
    return value if isinstance(value, ConniData) else None


def spanish_number(value: int | float, decimals: int = 0) -> str:
    rendered = f"{value:,.{decimals}f}"
    return rendered.replace(",", "_").replace(".", ",").replace("_", ".")


def handle_master_upload() -> None:
    version = st.session_state.get("uploader_version", 0)
    uploaded = st.file_uploader(
        "Selecciona el Maestro Databricks",
        type=["xlsx", "xlsm"],
        key=f"master_upload_{version}",
        help="Debe contener 01_SRC_SOCIODEMO, 02_SRC_PERSONAL y 03_SRC_CORREOS.",
    )
    if uploaded is None:
        return
    content = uploaded.getvalue()
    fingerprint = f"{hashlib.sha256(content).hexdigest()}:{uploaded.name}"
    if st.session_state.get("uploaded_fingerprint") == fingerprint and active_data() is not None:
        return
    try:
        with st.spinner("Validando estructura, períodos y campos del maestro..."):
            validated = load_master(content, uploaded.name)
    except WorkbookValidationError as exc:
        st.session_state.upload_error = str(exc)
        return
    st.session_state.uploaded_data = validated
    st.session_state.uploaded_fingerprint = fingerprint
    st.session_state.pop("upload_error", None)
    st.rerun()


def render_executive_pulse(data: ConniData) -> None:
    periods = sorted(data.personal["period"].dropna().astype(str).unique())
    if not periods:
        st.warning("El archivo fue leído, pero no contiene períodos válidos en la hoja Personal.")
        return
    latest = periods[-1]
    filtered = filter_period_and_area(data, latest)
    plant = plant_metrics(filtered.personal)
    socio = socio_metrics(filtered.sociodemo) if not filtered.sociodemo.empty else None
    coverage = float(plant["coverage"])
    if coverage >= 0.95:
        tone, headline = "stable", "Cobertura en rango alto"
    elif coverage >= 0.90:
        tone, headline = "attention", "Cobertura para seguimiento"
    else:
        tone, headline = "priority", "Brecha de cobertura prioritaria"
    quality = quality_summary(data)
    high_alerts = int(quality.loc[quality["Prioridad"].isin(["Crítico", "Alto"]), "Registros"].sum())
    population = int(socio["population"]) if socio is not None else 0
    st.markdown(
        f"""
        <section class="command-center">
          <div class="command-heading">
            <div><span>PULSO GERENCIAL</span><h2>La primera lectura del archivo ya está lista.</h2></div>
            <i>Actualizado desde {escape(data.source_name)}</i>
          </div>
          <div class="command-grid">
            <article><small>CORTE ACTIVO</small><strong>{latest}</strong><p>Último período disponible</p></article>
            <article><small>COBERTURA DE PLANTA</small><strong>{coverage:.1%}</strong><p>{spanish_number(plant['occupied'])} posiciones ocupadas</p></article>
            <article><small>PASIVO DEPURADO</small><strong>{spanish_number(plant['vacation_days_net'])}</strong><p>Días después de solicitudes</p></article>
            <article><small>POBLACIÓN CARACTERIZADA</small><strong>{spanish_number(population)}</strong><p>Personas en el corte</p></article>
          </div>
          <div class="management-brief {tone}">
            <span class="brief-signal"><i></i></span>
            <div><small>LECTURA GERENCIAL CALCULADA</small><h3>{headline}</h3><p>La planta registra {spanish_number(plant['vacant'])} vacantes y {spanish_number(plant['onc'])} posiciones ONC. Los controles de calidad acumulan {spanish_number(high_alerts)} registros de prioridad alta o crítica para revisión.</p></div>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns(2)
    left.button(
        "Abrir ventana 02 · Planta y vacaciones  →",
        type="primary",
        width="stretch",
        on_click=go_to,
        args=("Planta y vacaciones",),
    )
    right.button(
        "Abrir ventana 03 · Perfil sociodemográfico  →",
        width="stretch",
        on_click=go_to,
        args=("Perfil sociodemográfico",),
    )


def render_quality_panel(data: ConniData) -> None:
    with st.expander("Calidad, privacidad y descarga del modelo agregado"):
        summary = quality_summary(data)
        st.dataframe(summary, width="stretch", hide_index=True)
        st.caption("La descarga excluye nombres, documentos, correos y fechas de nacimiento.")
        try:
            export_bytes = analytics_workbook(data)
            st.download_button(
                "Descargar Conni_Modelo_Analitico.xlsx",
                data=export_bytes,
                file_name="Conni_Modelo_Analitico.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )
        except Exception as exc:
            st.error(f"No fue posible preparar la descarga agregada: {exc}")


def render_intro(data: ConniData | None) -> None:
    logo = image_data_uri(ROOT / "assets" / "logo_colsubsidio.png")
    cif_logo = image_data_uri(ROOT / "assets" / "logo_cif.png")
    if data is None:
        status_class = "waiting"
        status_label = "Esperando archivo"
        period_label = "Sin datos precargados"
    else:
        periods = int(data.personal["period"].nunique())
        status_class = "live"
        status_label = "Maestro validado"
        period_label = f"{periods} cortes habilitados"

    st.markdown(
        f"""
        <section class="intro-hero">
          <div class="hero-mesh" aria-hidden="true"></div>
          <div class="hero-scanline" aria-hidden="true"></div>
          <div class="intro-hero-grid">
            <div class="intro-copy">
              <span class="intro-kicker">CENTRO EJECUTIVO DE PERSONAS</span>
              <h1>Inteligencia<br>de Talento</h1>
              <div class="intro-underline"></div>
              <p>Una experiencia gerencial para leer planta, vacaciones y perfil sociodemográfico desde una única fuente validada y sin información precargada.</p>
              <div class="hero-status-row">
                <span class="hero-status {status_class}"><i></i>{status_label}</span>
                <span class="hero-status periods"><i></i>{period_label}</span>
              </div>
            </div>
            <div class="intro-visual" aria-hidden="true">
              <div class="orbit orbit-one"></div>
              <div class="orbit orbit-two"></div>
              <div class="visual-glow"></div>
              <img class="hero-mark" src="{logo}" alt="">
              <div class="hero-cif-card"><img src="{cif_logo}" alt="CIF"></div>
              <span class="data-node node-one"></span><span class="data-node node-two"></span><span class="data-node node-three"></span>
            </div>
          </div>
        </section>
        <div class="intro-heading">
          <span>VENTANA 01 · FUENTE DE INFORMACIÓN</span>
          <h2>Carga el maestro para activar la experiencia.</h2>
          <p>No hay cifras de ejemplo: cada indicador se construye únicamente con el archivo que asignes en esta sesión.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    upload_col, journey_col = st.columns([1.35, 0.65], gap="large")
    with upload_col:
        st.markdown(
            """
            <div class="upload-panel-anchor">
              <span class="upload-icon">↑</span>
              <div><small>CARGA SEGURA EN MEMORIA</small><h3>Maestro Databricks</h3><p>Arrastra el archivo o selecciónalo desde tu computador.</p></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        handle_master_upload()
        error = st.session_state.get("upload_error")
        if error:
            st.error(error)
            if data is not None:
                st.caption("El último archivo válido continúa activo hasta que cargues uno nuevo o lo retires.")
        current = active_data()
        if current is not None:
            periods = int(current.personal["period"].nunique())
            st.markdown(
                f"<div class='active-file'><span>✓</span><div><small>ARCHIVO ACTIVO</small><b>{escape(current.source_name)}</b><p>{spanish_number(len(current.personal))} filas de planta · {periods} cortes disponibles</p></div></div>",
                unsafe_allow_html=True,
            )
            st.button("Retirar archivo de esta sesión", key="clear_master", on_click=clear_loaded_data)
    current = active_data()
    with journey_col:
        ready = current is not None
        status = "ready" if ready else "locked"
        st.markdown(
            f"""
            <div class="window-journey">
              <small>RUTA DE ANÁLISIS</small><h3>Tres ventanas, una sola lectura.</h3>
              <article class="complete"><span>01</span><div><b>Carga de información</b><p>{'Archivo listo para análisis' if ready else 'Punto de entrada activo'}</p></div><i>●</i></article>
              <article class="{status}"><span>02</span><div><b>Planta y vacaciones</b><p>{'Ventana habilitada' if ready else 'Se habilita con el maestro'}</p></div><i>{'✓' if ready else '⌁'}</i></article>
              <article class="{status}"><span>03</span><div><b>Perfil sociodemográfico</b><p>{'Ventana habilitada' if ready else 'Se habilita con el maestro'}</p></div><i>{'✓' if ready else '⌁'}</i></article>
              <div class="journey-note"><b>Diseñado para gerencia.</b> La lectura prioriza señales, brechas y contexto para apoyar conversaciones de decisión.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if current is None:
        st.markdown(
            """
            <div class="no-data-state">
              <div class="empty-orbit"><i></i></div>
              <h3>La experiencia está lista; falta la fuente.</h3>
              <p>Carga el Maestro Databricks para construir los indicadores. Hasta entonces, las ventanas 02 y 03 permanecen sin cifras.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        render_executive_pulse(current)
        render_quality_panel(current)
    with st.expander("¿Cómo se mantienen los datos durante la sesión?"):
        source = escape(current.source_name) if current is not None else "Ningún archivo activo"
        rows = spanish_number(len(current.personal)) if current is not None else "0"
        st.markdown(
            f"""
            <div class="data-flow-grid">
              <article><span>01</span><h4>Fuente asignada</h4><p><b>{source}</b><br>La app no incorpora una base de ejemplo.</p></article>
              <article><span>02</span><h4>Memoria de sesión</h4><p>Los DataFrames permanecen temporalmente en memoria. Filas activas de planta: {rows}.</p></article>
              <article><span>03</span><h4>Sin persistencia local</h4><p>El Excel no se escribe en GitHub ni en una carpeta del proyecto. Al reiniciar el servicio debe cargarse nuevamente.</p></article>
            </div>
            <div class="privacy-note"><b>Privacidad desde el diseño.</b> Para información real utiliza únicamente un entorno corporativo autorizado. Los tableros y la descarga trabajan con resultados agregados.</div>
            """,
            unsafe_allow_html=True,
        )


def dashboard_filters(data: ConniData, key_prefix: str) -> tuple[str, list[str], list[str]]:
    periods = sorted(data.personal["period"].dropna().astype(str).unique(), reverse=True)
    if not periods:
        st.error("No se encontraron períodos válidos en Personal.")
        st.stop()
    c1, c2, c3 = st.columns([1, 1.5, 1.5])
    period = c1.selectbox("Período", periods, key=f"{key_prefix}_period")
    snapshot = data.personal.loc[data.personal["period"].eq(period)]
    strategies = sorted(snapshot["strategy"].dropna().astype(str).unique())
    selected_strategies = c2.multiselect("Unidad estratégica", strategies, key=f"{key_prefix}_strategy")
    scoped = snapshot if not selected_strategies else snapshot.loc[snapshot["strategy"].isin(selected_strategies)]
    organizations = sorted(scoped["organization"].dropna().astype(str).unique())
    selected_orgs = c3.multiselect("Unidad organizativa", organizations, key=f"{key_prefix}_org")
    return period, selected_strategies, selected_orgs


def dashboard_heading(number: str, title: str, copy: str) -> None:
    back, _ = st.columns([0.24, 0.76])
    back.button(
        "← Volver a Carga de información",
        key=f"back_{number}",
        width="stretch",
        on_click=go_to,
        args=("Carga de información",),
    )
    st.markdown(
        f"<div class='dashboard-heading'><span>VENTANA {number} · LECTURA EJECUTIVA</span><h1>{title}</h1><p>{copy}</p></div>",
        unsafe_allow_html=True,
    )


def render_locked_dashboard(number: str, title: str) -> None:
    dashboard_heading(number, title, "Esta ventana se construye exclusivamente con el maestro asignado en la sesión.")
    st.markdown(
        """
        <div class="locked-dashboard">
          <div class="lock-core"><span></span><i></i></div>
          <small>VENTANA PROTEGIDA</small>
          <h2>Aún no hay información para visualizar.</h2>
          <p>Regresa a la primera ventana y carga el Maestro Databricks. No mostramos cifras simuladas ni valores de ejemplo.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button(
        "Ir a Carga de información  →",
        key=f"locked_{number}",
        type="primary",
        on_click=go_to,
        args=("Carga de información",),
    )


def render_plant_dashboard(data: ConniData) -> None:
    dashboard_heading("02", "Planta y vacaciones", "Una vista ejecutiva de posiciones, cobertura y exposición del pasivo vacacional.")
    period, strategies, orgs = dashboard_filters(data, "plant")
    filtered = filter_period_and_area(data, period, strategies, orgs)
    metrics = plant_metrics(filtered.personal)
    if metrics["authorized"] == 0:
        st.warning("Los filtros seleccionados no tienen posiciones.")
        return
    kpi_cards(
        [
            ("Planta autorizada", spanish_number(metrics["authorized"]), "Posiciones del período", COLORS["blue"]),
            ("Planta ocupada", spanish_number(metrics["occupied"]), f"{metrics['coverage']:.0%} de cobertura", COLORS["green"]),
            ("Vacantes", spanish_number(metrics["vacant"]), "Disponibles para cubrir", COLORS["yellow"]),
            ("ONC", spanish_number(metrics["onc"]), "Orden de no cubrir", COLORS["red"]),
            ("Practicantes", spanish_number(metrics["practitioners"]), "Subgrupo de ocupados", COLORS["cyan"]),
            ("Pasivo depurado", spanish_number(metrics["vacation_days_net"]), "Días después de solicitudes", COLORS["bright"]),
        ]
    )
    area = plant_by_area(filtered.personal)
    gender = gender_by_area(filtered.personal)
    left, right = st.columns([1.45, 1])
    if not gender.empty:
        fig = px.bar(gender, x="Área", y="Personas", color="Género", barmode="group", title="Género por gerencia", color_discrete_sequence=[COLORS["cyan"], COLORS["blue"], COLORS["muted"]])
        fig.update_xaxes(tickangle=-18)
        left.plotly_chart(chart_style(fig, 420), width="stretch")
    composition = pd.DataFrame(
        {
            "Estado": ["Ocupada", "Vacantes", "ONC"],
            "Posiciones": [metrics["occupied"], metrics["vacant"], metrics["onc"]],
        }
    )
    fig = px.pie(composition, names="Estado", values="Posiciones", hole=.55, title="Composición de la planta", color="Estado", color_discrete_map={"Ocupada": COLORS["blue"], "Vacantes": COLORS["yellow"], "ONC": COLORS["red"]})
    fig.update_traces(textposition="inside", textinfo="percent+value")
    right.plotly_chart(chart_style(fig, 420), width="stretch")

    long_area = area.melt(id_vars="Área", value_vars=["Ocupada", "Vacantes", "ONC"], var_name="Estado", value_name="Posiciones")
    fig = px.bar(long_area, y="Área", x="Posiciones", color="Estado", orientation="h", barmode="group", title="Cobertura por gerencia", color_discrete_map={"Ocupada": COLORS["blue"], "Vacantes": COLORS["yellow"], "ONC": COLORS["red"]})
    st.plotly_chart(chart_style(fig, max(390, 92 + len(area) * 58)), width="stretch")

    vacation = vacation_by_area(filtered.personal)
    periods = vacation_period_distribution(filtered.personal)
    left, right = st.columns([1.35, 1])
    if not vacation.empty:
        long_vac = vacation.melt(id_vars="Área", value_vars=["Días pasivo real", "Días pasivo depurado"], var_name="Concepto", value_name="Días")
        fig = px.bar(long_vac, y="Área", x="Días", color="Concepto", orientation="h", barmode="group", title="Pasivo vacacional real vs. depurado", color_discrete_sequence=[COLORS["navy"], COLORS["cyan"]])
        left.plotly_chart(chart_style(fig, 410), width="stretch")
    fig = px.bar(periods, x="Periodos", y="Personas", title="Personas por períodos acumulados", color="Personas", color_continuous_scale=[[0, "#E9F7FC"], [1, COLORS["blue"]]])
    fig.update_layout(coloraxis_showscale=False)
    right.plotly_chart(chart_style(fig, 410), width="stretch")
    st.markdown("### Resumen por área")
    st.dataframe(vacation, width="stretch", hide_index=True)


def render_socio_dashboard(data: ConniData) -> None:
    dashboard_heading("03", "Perfil sociodemográfico", "Características de nuestra gente y su experiencia de movilidad.")
    period, strategies, orgs = dashboard_filters(data, "socio")
    filtered = filter_period_and_area(data, period, strategies, orgs)
    socio = filtered.sociodemo
    if socio.empty:
        st.warning("No hay registros sociodemográficos para los filtros seleccionados.")
        return
    metrics = socio_metrics(socio)
    age_text = "—" if pd.isna(metrics["average_age"]) else f"{metrics['average_age']:.0f}"
    commute_text = "—" if pd.isna(metrics["average_commute"]) else f"{metrics['average_commute']:.0f}"
    kpi_cards(
        [
            ("Población", spanish_number(metrics["population"]), "Personas caracterizadas", COLORS["blue"]),
            ("Edad promedio", age_text, "Años", COLORS["cyan"]),
            ("Edad mínima", "—" if pd.isna(metrics["min_age"]) else f"{metrics['min_age']:.0f}", "Años", COLORS["green"]),
            ("Edad máxima", "—" if pd.isna(metrics["max_age"]) else f"{metrics['max_age']:.0f}", "Años", COLORS["yellow"]),
            ("Transporte público", f"{metrics['public_transport']:.0%}", "Sobre población total", COLORS["bright"]),
            ("Tiempo promedio", commute_text, f"Minutos · {metrics['commute_reported']} registros", COLORS["red"]),
        ]
    )
    age = categorical_count(socio, "age_range", "Rango de edad")
    source_age_label = age["Rango de edad"].map(normalize_label).isin({"18 25", "18 a 25"})
    age.loc[source_age_label, "Rango de edad"] = "Hasta 25"
    gender = categorical_count(socio, "gender", "Género")
    left, right = st.columns([1.35, 1])
    fig = px.bar(age.sort_values("Personas"), x="Personas", y="Rango de edad", orientation="h", title="Distribución por rango etario", color="Personas", color_continuous_scale=[[0, "#BDEAF4"], [1, COLORS["blue"]]])
    fig.update_layout(coloraxis_showscale=False)
    left.plotly_chart(chart_style(fig, 400), width="stretch")
    fig = px.pie(gender, names="Género", values="Personas", hole=.55, title="Distribución por género", color_discrete_sequence=[COLORS["cyan"], COLORS["blue"], COLORS["yellow"]])
    fig.update_traces(textposition="inside", textinfo="percent+value")
    right.plotly_chart(chart_style(fig, 400), width="stretch")

    transport = categorical_count(socio, "transport", "Medio de transporte")
    distance = categorical_count(socio, "distance_range", "Distancia")
    left, right = st.columns(2)
    fig = px.bar(transport.sort_values("Personas"), x="Personas", y="Medio de transporte", orientation="h", title="Medio de transporte", color="Medio de transporte", color_discrete_sequence=PALETTE)
    fig.update_layout(showlegend=False)
    left.plotly_chart(chart_style(fig, 430), width="stretch")
    fig = px.bar(distance, x="Distancia", y="Personas", title="Distancia al lugar de trabajo", color="Distancia", color_discrete_sequence=PALETTE)
    fig.update_layout(showlegend=False)
    fig.update_xaxes(tickangle=-15)
    right.plotly_chart(chart_style(fig, 430), width="stretch")

    commute = categorical_count(socio, "commute_range", "Tiempo de desplazamiento")
    pets = categorical_count(socio, "pet_type", "Mascota")
    left, right = st.columns(2)
    fig = px.bar(commute, x="Tiempo de desplazamiento", y="Personas", title="Tiempo reportado de desplazamiento", color="Personas", color_continuous_scale=[[0, "#FFF2B3"], [1, COLORS["blue"]]])
    fig.update_layout(coloraxis_showscale=False)
    fig.update_xaxes(tickangle=-18)
    left.plotly_chart(chart_style(fig, 410), width="stretch")
    fig = px.bar(pets.sort_values("Personas"), x="Personas", y="Mascota", orientation="h", title="Tipo de mascota", color="Mascota", color_discrete_sequence=PALETTE)
    fig.update_layout(showlegend=False)
    right.plotly_chart(chart_style(fig, 410), width="stretch")
    st.markdown(
        f"<div class='info-banner'><b>Distancia predominante:</b> {escape(str(metrics['predominant_distance']))}. "
        "El promedio de desplazamiento usa el punto medio de cada rango; ‘más de 180 min’ se representa como 180 minutos.</div>",
        unsafe_allow_html=True,
    )


sync_navigation_from_url()
data = active_data()
topbar()
window_navigation(data)
page = st.session_state.page
if page == "Carga de información":
    render_intro(data)
elif data is None:
    number = "02" if page == "Planta y vacaciones" else "03"
    render_locked_dashboard(number, page)
elif page == "Planta y vacaciones":
    render_plant_dashboard(data)
else:
    render_socio_dashboard(data)

st.markdown("<div class='footer'>Conni · Inteligencia de Talento · Prototipo Streamlit 2026</div>", unsafe_allow_html=True)
