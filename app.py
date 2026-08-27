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

from conni.data import ConniData, WorkbookValidationError, demo_data, load_master, normalize_label  # noqa: E402
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


def image_data_uri(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mime = "image/png" if suffix == "png" else "image/x-icon"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


st.set_page_config(
    page_title="Conni | Gestión de Personas",
    page_icon=str(ROOT / "assets" / "favicon.ico") if (ROOT / "assets" / "favicon.ico").exists() else "📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(f"<style>{(ROOT / 'assets' / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_demo() -> ConniData:
    return demo_data()


def topbar() -> None:
    logo = image_data_uri(ROOT / "assets" / "logo_colsubsidio.png")
    st.markdown(
        f"""
        <header class="app-topbar">
          <div class="brand-lockup">
            <img class="brand-mark" src="{logo}" alt="Colsubsidio">
            <div class="brand-copy">
              <span class="brand-name">Colsubsidio</span>
              <span class="brand-area">FINANZAS CORPORATIVAS</span>
            </div>
          </div>
          <div class="topbar-context">
            <span class="topbar-code">SF_FC_GP_001</span>
            <span class="topbar-label">Gestión de Personas</span>
          </div>
        </header>
        """,
        unsafe_allow_html=True,
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
    st.session_state.page = page


def source_sidebar() -> ConniData:
    logo = image_data_uri(ROOT / "assets" / "logo_colsubsidio.png")
    with st.sidebar:
        st.markdown(
            f"<div class='sidebar-brand'><img src='{logo}' alt='Colsubsidio'><div class='product'>Gestión de Personas</div></div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div class='sidebar-eyebrow'>Fuente de información</div>", unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "Cargar Maestro Databricks",
            type=["xlsx"],
            help="El archivo se procesa en memoria y no se guarda en el repositorio.",
        )
        if uploaded is None:
            st.session_state.pop("uploaded_data", None)
            st.session_state.pop("uploaded_fingerprint", None)
            data = cached_demo()
            st.markdown("<div class='source-chip'>● Modo demostración<br>Datos 100 % sintéticos</div>", unsafe_allow_html=True)
        else:
            try:
                content = uploaded.getvalue()
                fingerprint = f"{hashlib.sha256(content).hexdigest()}:{uploaded.name}"
                if (
                    st.session_state.get("uploaded_fingerprint") != fingerprint
                    or "uploaded_data" not in st.session_state
                ):
                    with st.spinner("Validando y preparando el maestro..."):
                        st.session_state.uploaded_data = load_master(content, uploaded.name)
                        st.session_state.uploaded_fingerprint = fingerprint
                data = st.session_state.uploaded_data
                st.markdown(
                    f"<div class='source-chip'>● Archivo validado<br>{escape(uploaded.name)}</div>",
                    unsafe_allow_html=True,
                )
            except WorkbookValidationError as exc:
                st.session_state.pop("uploaded_data", None)
                st.session_state.pop("uploaded_fingerprint", None)
                st.error(str(exc))
                data = cached_demo()
                st.caption("Se mantiene la demostración para que puedas seguir navegando.")
        st.divider()
        pages = {
            "Inicio": "Inicio",
            "Planta y vacaciones": "Planta y vacaciones",
            "Perfil sociodemográfico": "Perfil sociodemográfico",
            "Calidad y descarga": "Calidad y descarga",
        }
        if "page" not in st.session_state:
            st.session_state.page = "Inicio"
        st.radio("Navegación", list(pages), key="page", label_visibility="collapsed")
        st.divider()
        st.caption("Prototipo local / GitHub · Preparado para una futura Databricks App")
    return data


def render_intro(data: ConniData) -> None:
    logo = image_data_uri(ROOT / "assets" / "logo_colsubsidio.png")
    periods = int(data.personal["period"].nunique())
    position_rows = f"{len(data.personal):,}".replace(",", ".")
    if data.is_demo:
        status_class = "demo"
        status_label = "Demo sintética activa"
        source_label = "Generada automáticamente desde el código"
    else:
        status_class = "live"
        status_label = "Maestro validado"
        source_label = escape(data.source_name)

    st.markdown("<div class='intro-shell' aria-hidden='true'></div>", unsafe_allow_html=True)
    topbar()
    st.markdown(
        f"""
        <section class="intro-hero">
          <div class="hero-mesh" aria-hidden="true"></div>
          <div class="intro-hero-grid">
            <div class="intro-copy">
              <span class="intro-kicker">ANALÍTICA DE PERSONAS</span>
              <h1>Gestión de<br>Personas</h1>
              <div class="intro-underline"></div>
              <p>Integra la planta, el pasivo vacacional y el perfil sociodemográfico en una experiencia ejecutiva, clara y preparada para evolucionar hacia Databricks.</p>
              <div class="hero-status-row">
                <span class="hero-status {status_class}"><i></i>{status_label}</span>
                <span class="hero-status periods"><i></i>{periods} períodos disponibles</span>
              </div>
            </div>
            <div class="intro-visual" aria-hidden="true">
              <div class="orbit orbit-one"></div>
              <div class="orbit orbit-two"></div>
              <div class="visual-glow"></div>
              <img class="hero-mark" src="{logo}" alt="">
              <div class="hero-monogram">
                <span><b>G</b>P</span>
                <small>CONNI</small>
              </div>
            </div>
          </div>
        </section>
        <div class="intro-heading">
          <span>EXPLORA LA EXPERIENCIA</span>
          <h2>Dos lecturas, una sola fuente confiable.</h2>
        </div>
        <div class="module-grid">
          <article class="module-card plant-module">
            <div class="module-top"><span class="module-number">01</span><span class="module-arrow">↗</span></div>
            <h3>Planta y vacaciones</h3>
            <p>Ocupación, vacantes, ONC, cobertura por gerencia y exposición del pasivo vacacional.</p>
          </article>
          <article class="module-card socio-module">
            <div class="module-top"><span class="module-number">02</span><span class="module-arrow">↗</span></div>
            <h3>Perfil sociodemográfico</h3>
            <p>Edad, género, movilidad, distancia y tiempos de desplazamiento de nuestra gente.</p>
          </article>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    cols[0].button(
        "Entrar a Planta y vacaciones  →",
        type="primary",
        width="stretch",
        on_click=go_to,
        args=("Planta y vacaciones",),
    )
    cols[1].button(
        "Entrar al Perfil sociodemográfico  →",
        width="stretch",
        on_click=go_to,
        args=("Perfil sociodemográfico",),
    )
    with st.expander("¿Cómo aparecen los datos y cuánto tiempo se conservan?"):
        st.markdown(
            f"""
            <div class="data-flow-grid">
              <article><span>01</span><h4>Fuente activa</h4><p><b>{status_label}</b><br>{source_label}</p></article>
              <article><span>02</span><h4>Memoria de sesión</h4><p>La app trabaja con DataFrames en memoria. Tiene {position_rows} filas históricas de planta y {periods} períodos disponibles.</p></article>
              <article><span>03</span><h4>Sin persistencia local</h4><p>El código no guarda el Excel cargado en el repositorio ni en una carpeta del proyecto. Al terminar la sesión o reiniciar el servicio debe cargarse otra vez.</p></article>
            </div>
            <div class="privacy-note"><b>Privacidad desde el diseño.</b> Los dashboards presentan agregados. Para una prueba pública usa la demostración sintética; el maestro real debe permanecer en un entorno corporativo autorizado.</div>
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


def render_plant_dashboard(data: ConniData) -> None:
    topbar()
    st.markdown("<h1 class='section-title'>Planta y vacaciones</h1><p class='section-copy'>Una vista ejecutiva de posiciones, cobertura y pasivo vacacional.</p>", unsafe_allow_html=True)
    period, strategies, orgs = dashboard_filters(data, "plant")
    filtered = filter_period_and_area(data, period, strategies, orgs)
    metrics = plant_metrics(filtered.personal)
    if metrics["authorized"] == 0:
        st.warning("Los filtros seleccionados no tienen posiciones.")
        return
    kpi_cards(
        [
            ("Planta autorizada", f"{metrics['authorized']:,}", "Posiciones del período", COLORS["blue"]),
            ("Planta ocupada", f"{metrics['occupied']:,}", f"{metrics['coverage']:.0%} de cobertura", COLORS["green"]),
            ("Vacantes", f"{metrics['vacant']:,}", "Disponibles para cubrir", COLORS["yellow"]),
            ("ONC", f"{metrics['onc']:,}", "Orden de no cubrir", COLORS["red"]),
            ("Practicantes", f"{metrics['practitioners']:,}", "Subgrupo de ocupados", COLORS["cyan"]),
            ("Pasivo depurado", f"{metrics['vacation_days_net']:,.0f}", "Días después de solicitudes", COLORS["bright"]),
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
    topbar()
    st.markdown("<h1 class='section-title'>Perfil sociodemográfico</h1><p class='section-copy'>Características de nuestra gente y su experiencia de movilidad.</p>", unsafe_allow_html=True)
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
            ("Población", f"{metrics['population']:,}", "Personas caracterizadas", COLORS["blue"]),
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


def render_quality(data: ConniData) -> None:
    topbar()
    st.markdown("<h1 class='section-title'>Calidad y descarga</h1><p class='section-copy'>Controles previos a la publicación y paquete agregado para análisis.</p>", unsafe_allow_html=True)
    summary = quality_summary(data)
    critical = int(summary.loc[summary["Prioridad"].isin(["Crítico", "Alto"]), "Registros"].sum())
    kpi_cards(
        [
            ("Personal", f"{len(data.personal):,}", "Filas históricas", COLORS["blue"]),
            ("Sociodemo", f"{len(data.sociodemo):,}", "Filas históricas", COLORS["cyan"]),
            ("Encuesta", f"{len(data.encuesta):,}", "Respuestas", COLORS["green"]),
            ("Períodos", f"{data.personal['period'].nunique():,}", "Disponibles", COLORS["yellow"]),
            ("Alertas altas", f"{critical:,}", "Registros por revisar", COLORS["red"]),
            ("Modo", "Demo" if data.is_demo else "Real", "Fuente activa", COLORS["bright"]),
        ]
    )
    st.dataframe(summary, width="stretch", hide_index=True)
    st.markdown("### Descargar modelo analítico agregado")
    st.write("Genera un Excel sin nombres, documentos, correos ni fechas de nacimiento; contiene resúmenes por período y área.")
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


data = source_sidebar()
page = st.session_state.page
if page == "Inicio":
    render_intro(data)
elif page == "Planta y vacaciones":
    render_plant_dashboard(data)
elif page == "Perfil sociodemográfico":
    render_socio_dashboard(data)
else:
    render_quality(data)

st.markdown("<div class='footer'>Conni · Gestión de Personas · Prototipo Streamlit 2026</div>", unsafe_allow_html=True)
