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
    classify_quality_controls,
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
WINDOWS = ("Inicio", "Carga de información", "Planta y vacaciones", "Perfil sociodemográfico")
WINDOW_LABELS = {
    "Inicio": "⌂  Inicio",
    "Carga de información": "01  Carga de información",
    "Planta y vacaciones": "02  Planta y vacaciones",
    "Perfil sociodemográfico": "03  Perfil sociodemográfico",
}
WINDOW_SLUGS = {
    "Inicio": "inicio",
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
    slug = WINDOW_SLUGS.get(page, "inicio")
    st.session_state._last_query_view = slug
    st.query_params["view"] = slug


def topbar() -> None:
    logo = image_data_uri(ROOT / "assets" / "logo_colsubsidio.png")
    with st.container(key="app_topbar"):
        brand, context = st.columns([0.68, 0.32], vertical_alignment="center", gap="small")
        with brand:
            st.markdown(
                f"""
                <a class="brand-lockup" href="?view=inicio" target="_self" title="Volver al inicio">
                  <img class="brand-mark" src="{logo}" alt="Colsubsidio">
                  <div class="brand-copy">
                    <span class="brand-name">Colsubsidio</span>
                    <span class="brand-area">FINANZAS CORPORATIVAS</span>
                  </div>
                </a>
                """,
                unsafe_allow_html=True,
            )
        with context:
            st.markdown(
                """
                <div class="topbar-context">
                  <span class="topbar-code">SF_FC_GP_001</span>
                  <span class="topbar-label">Inteligencia de Talento</span>
                </div>
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


def kpi_cards(items: list[tuple[str, str, str, str, str]]) -> None:
    cards_list: list[str] = []
    for label, value, note, accent, icon in items:
        if icon.startswith("data:"):
            icon_markup = f'<img src="{icon}" alt="" loading="eager">'
            icon_class = "kpi-icon kpi-icon-art"
        else:
            icon_markup = escape(icon)
            icon_class = "kpi-icon"
        cards_list.append(
            f'<div class="kpi-card" style="--accent:{accent}">'
            f'<div class="kpi-content"><div class="kpi-label">{escape(label)}</div>'
            f'<div class="kpi-value">{escape(value)}</div>'
            f'<div class="kpi-note">{escape(note)}</div></div>'
            f'<span class="{icon_class}" aria-hidden="true">{icon_markup}</span>'
            "</div>"
        )
    cards = "".join(cards_list)
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
        transition=dict(duration=520, easing="cubic-in-out"),
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


def wrapped_label(value: object, width: int = 19) -> str:
    """Wrap long executive-area labels without losing their full wording."""
    words = str(value).split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "<br>".join(lines)


def executive_area_label(value: object) -> str:
    """Readable executive abbreviations for narrow comparison charts."""
    original = str(value)
    normalized = normalize_label(original)
    rules = (
        ("operacion de subsid", "G. SUBSIDIOS"),
        ("operaciones y tesorer", "G. OP. Y<br>TESORERÍA"),
        ("finanzas corpor", "G. FIN.<br>CORPORATIVAS"),
        ("departamento impuestos", "DPTO. IMP.<br>Y SEGUROS"),
        ("staff subdireccion", "STAFF<br>SUBDIRECCIÓN"),
        ("subdireccion financiera", "SUBD.<br>FINANCIERA"),
    )
    for token, label in rules:
        if token in normalized:
            return label
    return wrapped_label(original, width=14)


def gender_bucket(value: object) -> str:
    normalized = normalize_label(value)
    if normalized in {"f", "fem"} or any(token in normalized for token in ("femen", "mujer", "female")):
        return "Mujeres"
    if normalized in {"m", "masc"} or any(token in normalized for token in ("mascul", "hombre", "male")):
        return "Hombres"
    return "Sin información"


def gender_totals(personal: pd.DataFrame) -> dict[str, int]:
    occupied = personal.loc[personal["is_occupied"] & personal["person_id"].notna()].copy()
    occupied = occupied.drop_duplicates("person_id", keep="last")
    buckets = occupied["gender"].map(gender_bucket).value_counts()
    return {
        "Mujeres": int(buckets.get("Mujeres", 0)),
        "Hombres": int(buckets.get("Hombres", 0)),
        "Sin información": int(buckets.get("Sin información", 0)),
    }


def executive_chart_style(fig: go.Figure) -> go.Figure:
    chart_style(fig, 326)
    fig.update_layout(
        title=None,
        margin=dict(l=42, r=10, t=42, b=64),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=.5, title=None),
        uniformtext_minsize=8,
        uniformtext_mode="hide",
    )
    return fig


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


def executive_snapshot(data: ConniData) -> dict[str, object] | None:
    periods = sorted(data.personal["period"].dropna().astype(str).unique())
    if not periods:
        return None
    latest = periods[-1]
    filtered = filter_period_and_area(data, latest)
    plant = plant_metrics(filtered.personal)
    socio = socio_metrics(filtered.sociodemo) if not filtered.sociodemo.empty else None
    area = plant_by_area(filtered.personal)
    genders = gender_totals(filtered.personal)
    quality = classify_quality_controls(quality_summary(data))
    return {
        "latest": latest,
        "filtered": filtered,
        "plant": plant,
        "socio": socio,
        "area": area,
        "genders": genders,
        "quality": quality,
    }


def render_executive_explanation(data: ConniData) -> None:
    snapshot = executive_snapshot(data)
    if snapshot is None:
        st.warning("El archivo fue leído, pero no contiene períodos válidos en la hoja Personal.")
        return
    latest = str(snapshot["latest"])
    plant = snapshot["plant"]
    socio = snapshot["socio"]
    area = snapshot["area"].copy()
    genders = snapshot["genders"]
    quality = snapshot["quality"]

    gap = max(int(plant["authorized"]) - int(plant["occupied"]), 0)
    reduction = max(float(plant["vacation_days"]) - float(plant["vacation_days_net"]), 0)
    reduction_pct = reduction / float(plant["vacation_days"]) if plant["vacation_days"] else 0.0
    area_focus = "Sin área disponible"
    gap_focus = "Sin área disponible"
    if not area.empty:
        area["Cobertura"] = area["Ocupada"] / area["Autorizada"].replace(0, pd.NA)
        area["Brecha"] = area["Autorizada"] - area["Ocupada"]
        coverage_rows = area.dropna(subset=["Cobertura"])
        if not coverage_rows.empty:
            lowest = coverage_rows.sort_values(["Cobertura", "Brecha"], ascending=[True, False]).iloc[0]
            area_focus = f"{lowest['Área']} · {lowest['Cobertura']:.1%}"
        widest = area.sort_values(["Brecha", "Autorizada"], ascending=[False, False]).iloc[0]
        gap_focus = f"{widest['Área']} · {spanish_number(int(widest['Brecha']))} posiciones"

    gender_total = int(genders["Mujeres"]) + int(genders["Hombres"]) + int(genders["Sin información"])
    women_share = int(genders["Mujeres"]) / gender_total if gender_total else 0.0
    people_copy = "No hay caracterización sociodemográfica en el último corte."
    if socio is not None:
        people_copy = (
            f"{spanish_number(int(socio['population']))} personas caracterizadas; "
            f"{women_share:.0%} mujeres y {int(genders['Hombres']) / gender_total if gender_total else 0:.0%} hombres. "
            f"{float(socio['public_transport']):.1%} reporta transporte público y el tiempo promedio es "
            f"{spanish_number(float(socio['average_commute']), 1) if not pd.isna(socio['average_commute']) else '—'} min."
        )

    st.markdown(
        f"""
        <section class="executive-explanation">
          <header><span>LECTURA AUTOMÁTICA DEL ARCHIVO</span><h2>¿Qué se puede comprender de estos datos?</h2><p>Esta lectura resume el último corte disponible y separa los hallazgos operativos de los controles históricos de calidad.</p></header>
          <div class="explanation-grid">
            <article><i>01</i><div><small>PLANTA · {latest}</small><p><b>{spanish_number(plant['occupied'])} de {spanish_number(plant['authorized'])}</b> posiciones están ocupadas ({float(plant['coverage']):.1%}). La brecha es de {spanish_number(gap)}: {spanish_number(plant['vacant'])} vacantes disponibles y {spanish_number(plant['onc'])} ONC.</p></div></article>
            <article><i>02</i><div><small>FOCO POR GERENCIA</small><p>La menor cobertura está en <b>{escape(area_focus)}</b>. La mayor brecha absoluta se concentra en <b>{escape(gap_focus)}</b>.</p></div></article>
            <article><i>03</i><div><small>VACACIONES</small><p>Las solicitudes reducen el pasivo en <b>{spanish_number(reduction, 1)} días ({reduction_pct:.1%})</b>, hasta {spanish_number(plant['vacation_days_net'], 1)} días depurados.</p></div></article>
            <article><i>04</i><div><small>PERSONAS Y CALIDAD</small><p>{escape(people_copy)} En el histórico, <b>{quality['clean_count']} de {quality['total']}</b> controles no presentan hallazgos y {quality['action_count']} requieren revisión.</p></div></article>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_executive_pulse(data: ConniData) -> None:
    snapshot = executive_snapshot(data)
    if snapshot is None:
        st.warning("El archivo fue leído, pero no contiene períodos válidos en la hoja Personal.")
        return
    latest = str(snapshot["latest"])
    plant = snapshot["plant"]
    socio = snapshot["socio"]
    quality = snapshot["quality"]
    coverage = float(plant["coverage"])
    if coverage >= 0.95:
        tone, headline = "stable", "Cobertura en rango alto"
    elif coverage >= 0.90:
        tone, headline = "attention", "Cobertura para seguimiento"
    else:
        tone, headline = "priority", "Brecha de cobertura prioritaria"
    population = int(socio["population"]) if socio is not None else 0
    coverage_width = min(max(coverage * 100, 0), 100)
    st.markdown(
        f"""
        <div class="compact-panel-anchor pulse-panel">
          <div class="compact-panel-heading">
            <span class="compact-panel-icon">⌁</span>
            <div><small>PULSO GERENCIAL</small><h2>Señales del último corte</h2><p>{escape(data.source_name)}</p></div>
          </div>
          <div class="pulse-metrics">
            <article><small>CORTE ACTIVO</small><strong>{latest}</strong><p>Último período</p></article>
            <article><small>COBERTURA</small><strong>{coverage:.1%}</strong><p>{spanish_number(plant['occupied'])} ocupadas</p></article>
            <article><small>PASIVO DEPURADO</small><strong>{spanish_number(plant['vacation_days_net'], 1)}</strong><p>Días</p></article>
            <article><small>POBLACIÓN</small><strong>{spanish_number(population)}</strong><p>Personas</p></article>
          </div>
          <div class="coverage-rail" aria-label="Cobertura {coverage:.1%}"><span style="--coverage:{coverage_width:.2f}%"></span></div>
          <div class="pulse-decision {tone}">
            <span><i></i></span><div><small>LECTURA GERENCIAL</small><h3>{headline}</h3><p>{spanish_number(plant['vacant'])} vacantes, {spanish_number(plant['onc'])} ONC y {quality['action_count']} controles históricos por revisar.</p></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_quality_panel(data: ConniData) -> None:
    quality = classify_quality_controls(quality_summary(data))
    active = quality["active"]
    clear = quality["clear"]
    descriptions = {
        "Posiciones sin persona": "Vacantes u ONC sin persona · comportamiento esperado",
        "Fechas de nacimiento vacías": "Dato faltante que afecta la lectura de edad",
        "Encuestas sin período": "No se pueden asignar a un corte específico",
    }
    active_rows: list[str] = []
    for row in active.itertuples(index=False):
        priority = str(row.Prioridad)
        visual_class = "context" if priority == "Informativo" else "review"
        label = descriptions.get(str(row.Control), str(row.Control))
        active_rows.append(
            f'<article class="quality-row {visual_class}"><strong>{spanish_number(int(row.Registros))}</strong>'
            f'<div><b>{escape(label)}</b><small>{escape(str(row.Estado))} · {escape(priority)}</small></div></article>'
        )
    clear_rows = "".join(
        f'<li><span>✓</span><b>{escape(str(row.Control))}</b><i>0</i></li>' for row in clear.itertuples(index=False)
    )
    st.markdown(
        f"""
        <div class="compact-panel-anchor quality-panel">
          <div class="compact-panel-heading">
            <span class="compact-panel-icon shield">✓</span>
            <div><small>CALIDAD · HISTÓRICO COMPLETO</small><h2>{quality['clean_count']} de {quality['total']} sin hallazgos</h2><p>{quality['action_count']} controles requieren revisión</p></div>
          </div>
          <div class="quality-active">{''.join(active_rows)}</div>
          <details class="quality-clear">
            <summary>Ver {quality['clean_count']} controles sin hallazgos <span>＋</span></summary>
            <ul>{clear_rows}</ul>
          </details>
          <div class="quality-privacy"><b>Salida agregada y segura.</b> Excluye nombres, documentos, correos y fechas de nacimiento.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        export_bytes = analytics_workbook(data)
        st.download_button(
            "↓  Descargar modelo analítico agregado",
            data=export_bytes,
            file_name="Conni_Modelo_Analitico.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )
    except Exception as exc:
        st.error(f"No fue posible preparar la descarga agregada: {exc}")


def render_home(data: ConniData | None) -> None:
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
        """,
        unsafe_allow_html=True,
    )


def render_upload_controls(current: ConniData | None) -> None:
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
        if current is not None:
            st.caption("El último archivo válido continúa activo hasta que cargues uno nuevo o lo retires.")
    if current is not None:
        periods = int(current.personal["period"].nunique())
        st.markdown(
            f"<div class='active-file'><span>✓</span><div><small>ARCHIVO ACTIVO</small><b>{escape(current.source_name)}</b><p>{spanish_number(len(current.personal))} filas de planta · {periods} cortes disponibles</p></div></div>",
            unsafe_allow_html=True,
        )
        st.button("Retirar archivo de esta sesión", key="clear_master", on_click=clear_loaded_data)


def render_analysis_journey(current: ConniData | None, compact: bool = False) -> None:
    ready = current is not None
    status = "ready" if ready else "locked"
    compact_class = " compact" if compact else ""
    st.markdown(
        f"""
        <div class="window-journey{compact_class}">
          <small>RUTA DE ANÁLISIS</small><h3>Tres pasos, una sola lectura.</h3>
          <article class="complete"><span>01</span><div><b>Carga de información</b><p>{'Archivo listo para análisis' if ready else 'Punto de entrada activo'}</p></div><i>●</i></article>
          <article class="{status}"><span>02</span><div><b>Planta y vacaciones</b><p>{'Ventana habilitada' if ready else 'Se habilita con el maestro'}</p></div><i>{'✓' if ready else '⌁'}</i></article>
          <article class="{status}"><span>03</span><div><b>Perfil sociodemográfico</b><p>{'Ventana habilitada' if ready else 'Se habilita con el maestro'}</p></div><i>{'✓' if ready else '⌁'}</i></article>
          <div class="journey-note"><b>Diseñado para gerencia.</b> La lectura prioriza señales, brechas y contexto para apoyar conversaciones de decisión.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_upload_window(data: ConniData | None) -> None:
    current = active_data()
    if current is None:
        st.markdown(
            """
            <div class="upload-window-heading">
              <span>VENTANA 01 · FUENTE DE INFORMACIÓN</span>
              <h1>Carga y habilitación de la experiencia</h1>
              <p>No hay cifras de ejemplo: cada indicador se construye únicamente con el archivo asignado en esta sesión.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        upload_col, journey_col = st.columns([1.35, 0.65], gap="large")
        with upload_col:
            render_upload_controls(None)
        with journey_col:
            render_analysis_journey(None)
        st.markdown(
            """
            <div class="no-data-state">
              <div class="empty-orbit"><i></i></div>
              <h3>La experiencia está lista; falta la fuente.</h3>
              <p>Carga el Maestro Databricks para construir los indicadores. Hasta entonces, Planta y Perfil permanecen sin cifras.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        periods = int(current.personal["period"].nunique())
        source_summary = (
            f"✓ Maestro activo · {current.source_name} · {spanish_number(len(current.personal))} filas · "
            f"{periods} cortes · administrar fuente"
        )
        with st.expander(source_summary, expanded=False):
            upload_col, journey_col = st.columns([1.35, 0.65], gap="large")
            with upload_col:
                render_upload_controls(current)
            with journey_col:
                render_analysis_journey(current, compact=True)

        render_executive_explanation(current)
        with st.container(key="insight_quality_row"):
            pulse_col, quality_col = st.columns([1.35, 0.65], gap="large")
            with pulse_col:
                render_executive_pulse(current)
            with quality_col:
                render_quality_panel(current)


def dashboard_filters(data: ConniData, key_prefix: str) -> tuple[str, list[str], list[str]]:
    periods = sorted(data.personal["period"].dropna().astype(str).unique(), reverse=True)
    if not periods:
        st.error("No se encontraron períodos válidos en Personal.")
        st.stop()
    with st.container(border=True):
        st.markdown(
            "<div class='filter-strip-heading'><span>⌘</span><div><b>Filtros del tablero</b><small>Los tres controles actualizan toda la sección visible.</small></div></div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns([0.85, 1.55, 1.6], gap="medium")
        period = c1.selectbox("▣  Período", periods, key=f"{key_prefix}_period")
        snapshot = data.personal.loc[data.personal["period"].eq(period)]
        strategies = sorted(snapshot["strategy"].dropna().astype(str).unique())
        selected_strategies = c2.multiselect("⌂  Unidad estratégica", strategies, key=f"{key_prefix}_strategy")
        scoped = snapshot if not selected_strategies else snapshot.loc[snapshot["strategy"].isin(selected_strategies)]
        organizations = sorted(scoped["organization"].dropna().astype(str).unique())
        selected_orgs = c3.multiselect("⌘  Unidad organizativa", organizations, key=f"{key_prefix}_org")
    return period, selected_strategies, selected_orgs


def dashboard_heading(number: str, title: str, copy: str) -> None:
    st.markdown(
        f"<div class='dashboard-heading'><span>VENTANA {number} · LECTURA EJECUTIVA</span><h1>{title}</h1></div>",
        unsafe_allow_html=True,
    )
    with st.expander("Ver propósito, alcance y forma de lectura", expanded=False):
        st.markdown(
            f"<div class='dashboard-context'><b>{title}</b><p>{copy}</p><small>Usa los filtros y las categorías para concentrarte en una sola conversación gerencial a la vez.</small></div>",
            unsafe_allow_html=True,
        )


def category_navigation(
    key: str,
    options: tuple[str, ...],
    labels: dict[str, str],
) -> str:
    st.markdown(
        "<div class='category-heading'><span>SECCIONES DEL TABLERO</span><small>Selecciona una lectura</small></div>",
        unsafe_allow_html=True,
    )
    return st.radio(
        "Secciones del tablero",
        options,
        format_func=lambda option: labels[option],
        horizontal=True,
        key=key,
        label_visibility="collapsed",
    )


def section_heading(icon: str, title: str, copy: str) -> None:
    st.markdown(
        f"<div class='section-heading-card'><span>{icon}</span><div><small>LECTURA ACTIVA</small><h2>{title}</h2><p>{copy}</p></div></div>",
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


def render_gender_overview(personal: pd.DataFrame) -> None:
    totals = gender_totals(personal)
    total = sum(totals.values())
    women_pct = totals["Mujeres"] / total if total else 0.0
    men_pct = totals["Hombres"] / total if total else 0.0
    unknown_note = (
        f" · {spanish_number(totals['Sin información'])} sin dato"
        if totals["Sin información"]
        else ""
    )
    people_art = image_data_uri(ROOT / "assets" / "people_gender.png")
    st.markdown(
        f"""
        <section class="gender-overview">
          <header><small>COMPOSICIÓN GENERAL</small><h3>Distribución por género</h3><p>{spanish_number(total)} personas{unknown_note}</p></header>
          <div class="gender-stage"><span></span><img src="{people_art}" alt="Ilustración de una mujer y un hombre"></div>
          <div class="gender-stat-row"><b>{spanish_number(totals['Mujeres'])}<small>Mujeres</small></b><b>{spanish_number(totals['Hombres'])}<small>Hombres</small></b></div>
          <div class="gender-progress women"><label><span>Mujeres</span><strong>{women_pct:.0%}</strong></label><i><em style="--fill:{women_pct * 100:.2f}%"></em></i></div>
          <div class="gender-progress men"><label><span>Hombres</span><strong>{men_pct:.0%}</strong></label><i><em style="--fill:{men_pct * 100:.2f}%"></em></i></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_plant_dashboard(data: ConniData) -> None:
    dashboard_heading("02", "Planta y vacaciones", "Una vista ejecutiva de posiciones, cobertura y exposición del pasivo vacacional.")
    section = category_navigation(
        "plant_section",
        ("Resumen gerencial", "Estructura de planta", "Vacaciones"),
        {
            "Resumen gerencial": "👥  Resumen gerencial",
            "Estructura de planta": "🏢  Estructura de planta",
            "Vacaciones": "🗓️  Vacaciones",
        },
    )
    period, strategies, orgs = dashboard_filters(data, "plant")
    filtered = filter_period_and_area(data, period, strategies, orgs)
    metrics = plant_metrics(filtered.personal)
    if metrics["authorized"] == 0:
        st.warning("Los filtros seleccionados no tienen posiciones.")
        return
    authorized_art = image_data_uri(ROOT / "assets" / "people_authorized.png")
    occupied_art = image_data_uri(ROOT / "assets" / "people_occupied.png")
    kpi_cards(
        [
            ("Planta autorizada", spanish_number(metrics["authorized"]), "Posiciones del período", COLORS["blue"], authorized_art),
            ("Planta ocupada", spanish_number(metrics["occupied"]), f"{metrics['coverage']:.0%} de cobertura", COLORS["green"], occupied_art),
            ("Vacantes", spanish_number(metrics["vacant"]), "Disponibles para cubrir", COLORS["yellow"], "◇"),
            ("ONC", spanish_number(metrics["onc"]), "Orden de no cubrir", COLORS["red"], "⊘"),
            ("Practicantes", spanish_number(metrics["practitioners"]), "Subgrupo de ocupados", COLORS["cyan"], "♙"),
            ("Pasivo depurado", spanish_number(metrics["vacation_days_net"], 1), "Días después de solicitudes", COLORS["bright"], "▣"),
        ]
    )
    area = plant_by_area(filtered.personal)
    gender = gender_by_area(filtered.personal)
    composition = pd.DataFrame(
        {
            "Estado": ["Ocupada", "Vacantes", "ONC"],
            "Posiciones": [metrics["occupied"], metrics["vacant"], metrics["onc"]],
        }
    )
    if section == "Resumen gerencial":
        section_heading("👥", "Resumen gerencial", "Una sola pantalla para conversar sobre género, brechas de cobertura y composición total de la planta.")
        if not area.empty:
            focus = area.assign(Brecha=area["Autorizada"] - area["Ocupada"])
            focus["Cobertura"] = focus["Ocupada"] / focus["Autorizada"].replace(0, pd.NA)
            largest_gap = focus.sort_values(["Brecha", "Autorizada"], ascending=[False, False]).iloc[0]
            st.markdown(
                f"<div class='dashboard-smart-read'><span>LECTURA DEL FILTRO</span><p>En <b>{escape(period)}</b>, la cobertura es <b>{metrics['coverage']:.1%}</b>. La mayor brecha está en <b>{escape(str(largest_gap['Área']))}</b> con {spanish_number(int(largest_gap['Brecha']))} posiciones; compara su composición de género y el balance entre vacantes y ONC en los visuales siguientes.</p></div>",
                unsafe_allow_html=True,
            )

        gender_chart = gender.copy()
        if not gender_chart.empty:
            gender_chart["Género"] = gender_chart["Género"].map(gender_bucket)
            gender_chart = gender_chart.groupby(["Área", "Género"], as_index=False)["Personas"].sum()
            gender_chart["Gerencia"] = gender_chart["Área"].map(executive_area_label)
        plant_chart = area.copy()
        plant_chart["Gerencia"] = plant_chart["Área"].map(executive_area_label)
        area_order = plant_chart["Gerencia"].tolist()

        with st.container(key="executive_visuals"):
            gender_total_col, gender_area_col, capacity_col, vacancy_col = st.columns(
                [0.82, 1.52, 1.10, 0.98], gap="medium"
            )
            with gender_total_col:
                render_gender_overview(filtered.personal)

            with gender_area_col:
                st.markdown("<div class='executive-chart-heading'><span>02</span><h3>Género por gerencia</h3></div>", unsafe_allow_html=True)
                if gender_chart.empty:
                    st.info("Sin datos de género para los filtros elegidos.")
                else:
                    fig = px.bar(
                        gender_chart,
                        x="Gerencia",
                        y="Personas",
                        color="Género",
                        barmode="group",
                        text="Personas",
                        custom_data=["Área"],
                        category_orders={"Gerencia": area_order, "Género": ["Mujeres", "Hombres", "Sin información"]},
                        color_discrete_map={"Mujeres": COLORS["cyan"], "Hombres": COLORS["blue"], "Sin información": COLORS["muted"]},
                    )
                    fig.update_traces(textposition="outside", cliponaxis=False, marker_line_width=0, hovertemplate="<b>%{customdata[0]}</b><br>%{fullData.name}: %{y} personas<extra></extra>")
                    fig.update_xaxes(title=None, tickangle=0, tickfont_size=9)
                    fig.update_yaxes(title="Personas", rangemode="tozero")
                    gender_area_col.plotly_chart(executive_chart_style(fig), width="stretch", config={"displayModeBar": False})

            with capacity_col:
                st.markdown("<div class='executive-chart-heading'><span>03</span><h3>Ocupados y vacantes</h3></div>", unsafe_allow_html=True)
                capacity = plant_chart.melt(
                    id_vars=["Área", "Gerencia"],
                    value_vars=["Ocupada", "Vacantes"],
                    var_name="Estado",
                    value_name="Posiciones",
                )
                fig = px.bar(
                    capacity,
                    x="Gerencia",
                    y="Posiciones",
                    color="Estado",
                    barmode="stack",
                    text="Posiciones",
                    custom_data=["Área"],
                    category_orders={"Gerencia": area_order, "Estado": ["Ocupada", "Vacantes"]},
                    color_discrete_map={"Ocupada": COLORS["blue"], "Vacantes": "#75D4ED"},
                )
                fig.update_traces(textposition="inside", marker_line_width=0, hovertemplate="<b>%{customdata[0]}</b><br>%{fullData.name}: %{y} posiciones<extra></extra>")
                fig.update_xaxes(title=None, tickangle=0, tickfont_size=9)
                fig.update_yaxes(title="Posiciones", rangemode="tozero")
                capacity_col.plotly_chart(executive_chart_style(fig), width="stretch", config={"displayModeBar": False})

            with vacancy_col:
                st.markdown("<div class='executive-chart-heading'><span>04</span><h3>Vacantes vs. ONC</h3></div>", unsafe_allow_html=True)
                vacancy_area = plant_chart.melt(
                    id_vars=["Área", "Gerencia"],
                    value_vars=["Vacantes", "ONC"],
                    var_name="Estado",
                    value_name="Posiciones",
                )
                fig = px.bar(
                    vacancy_area,
                    x="Gerencia",
                    y="Posiciones",
                    color="Estado",
                    barmode="group",
                    text="Posiciones",
                    custom_data=["Área"],
                    category_orders={"Gerencia": area_order, "Estado": ["Vacantes", "ONC"]},
                    color_discrete_map={"Vacantes": COLORS["yellow"], "ONC": COLORS["red"]},
                )
                fig.update_traces(textposition="outside", cliponaxis=False, marker_line_width=0, hovertemplate="<b>%{customdata[0]}</b><br>%{fullData.name}: %{y} posiciones<extra></extra>")
                fig.update_xaxes(title=None, tickangle=0, tickfont_size=9)
                fig.update_yaxes(title="Posiciones", rangemode="tozero")
                vacancy_col.plotly_chart(executive_chart_style(fig), width="stretch", config={"displayModeBar": False})
    elif section == "Estructura de planta":
        section_heading("🏢", "Estructura de planta", "Detalle de ocupación, vacantes y ONC para comparar cobertura entre gerencias.")
        left, right = st.columns([1.55, 0.85], gap="medium")
        long_area = area.melt(
            id_vars="Área",
            value_vars=["Ocupada", "Vacantes", "ONC"],
            var_name="Estado",
            value_name="Posiciones",
        )
        fig = px.bar(
            long_area,
            y="Área",
            x="Posiciones",
            color="Estado",
            orientation="h",
            barmode="group",
            title="Cobertura por gerencia",
            color_discrete_map={"Ocupada": COLORS["blue"], "Vacantes": COLORS["yellow"], "ONC": COLORS["red"]},
        )
        left.plotly_chart(chart_style(fig, max(370, 90 + len(area) * 54)), width="stretch")
        fig = px.pie(
            composition,
            names="Estado",
            values="Posiciones",
            hole=.60,
            title="Planta total",
            color="Estado",
            color_discrete_map={"Ocupada": COLORS["blue"], "Vacantes": COLORS["yellow"], "ONC": COLORS["red"]},
        )
        fig.update_traces(textposition="inside", textinfo="percent+value")
        right.plotly_chart(chart_style(fig, max(370, 90 + len(area) * 54)), width="stretch")
        st.markdown("<div class='table-heading'><span>▦</span><div><b>Detalle por gerencia</b><small>Planta autorizada, ocupada, vacantes y ONC.</small></div></div>", unsafe_allow_html=True)
        st.dataframe(area, width="stretch", hide_index=True)
    else:
        section_heading("🗓️", "Vacaciones", "Exposición del pasivo antes y después de solicitudes, con distribución por períodos acumulados.")
        vacation = vacation_by_area(filtered.personal)
        periods = vacation_period_distribution(filtered.personal)
        left, right = st.columns([1.35, 1], gap="medium")
        if not vacation.empty:
            long_vac = vacation.melt(
                id_vars="Área",
                value_vars=["Días pasivo real", "Días pasivo depurado"],
                var_name="Concepto",
                value_name="Días",
            )
            fig = px.bar(
                long_vac,
                y="Área",
                x="Días",
                color="Concepto",
                orientation="h",
                barmode="group",
                title="Pasivo real vs. depurado",
                color_discrete_sequence=[COLORS["navy"], COLORS["cyan"]],
            )
            left.plotly_chart(chart_style(fig, 390), width="stretch")
        fig = px.bar(
            periods,
            x="Periodos",
            y="Personas",
            title="Personas por períodos acumulados",
            color="Personas",
            color_continuous_scale=[[0, "#E9F7FC"], [1, COLORS["blue"]]],
        )
        fig.update_layout(coloraxis_showscale=False)
        right.plotly_chart(chart_style(fig, 390), width="stretch")
        st.markdown("<div class='table-heading'><span>▦</span><div><b>Pasivo vacacional por gerencia</b><small>Comparación entre días reales y depurados.</small></div></div>", unsafe_allow_html=True)
        st.dataframe(vacation, width="stretch", hide_index=True)


def render_socio_dashboard(data: ConniData) -> None:
    dashboard_heading("03", "Perfil sociodemográfico", "Características de nuestra gente y su experiencia de movilidad.")
    section = category_navigation(
        "socio_section",
        ("Perfil general", "Movilidad", "Entorno personal"),
        {
            "Perfil general": "👤  Perfil general",
            "Movilidad": "🧭  Movilidad",
            "Entorno personal": "⌂  Entorno personal",
        },
    )
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
            ("Población", spanish_number(metrics["population"]), "Personas caracterizadas", COLORS["blue"], "👥"),
            ("Edad promedio", age_text, "Años", COLORS["cyan"], "🎂"),
            ("Edad mínima", "—" if pd.isna(metrics["min_age"]) else f"{metrics['min_age']:.0f}", "Años", COLORS["green"], "↘"),
            ("Edad máxima", "—" if pd.isna(metrics["max_age"]) else f"{metrics['max_age']:.0f}", "Años", COLORS["yellow"], "↗"),
            ("Transporte público", f"{metrics['public_transport']:.0%}", "Sobre población total", COLORS["bright"], "🚌"),
            ("Tiempo promedio", commute_text, f"Minutos · {metrics['commute_reported']} registros", COLORS["red"], "⏱️"),
        ]
    )
    if section == "Perfil general":
        section_heading("👤", "Perfil general", "Distribución de la población por edad y género para una lectura demográfica rápida.")
        age = categorical_count(socio, "age_range", "Rango de edad")
        source_age_label = age["Rango de edad"].map(normalize_label).isin({"18 25", "18 a 25"})
        age.loc[source_age_label, "Rango de edad"] = "Hasta 25"
        gender = categorical_count(socio, "gender", "Género")
        left, right = st.columns([1.35, 1], gap="medium")
        fig = px.bar(
            age.sort_values("Personas"),
            x="Personas",
            y="Rango de edad",
            orientation="h",
            title="Distribución por rango etario",
            color="Personas",
            color_continuous_scale=[[0, "#BDEAF4"], [1, COLORS["blue"]]],
        )
        fig.update_layout(coloraxis_showscale=False)
        left.plotly_chart(chart_style(fig, 390), width="stretch")
        fig = px.pie(
            gender,
            names="Género",
            values="Personas",
            hole=.58,
            title="Distribución por género",
            color_discrete_sequence=[COLORS["cyan"], COLORS["blue"], COLORS["yellow"]],
        )
        fig.update_traces(textposition="inside", textinfo="percent+value")
        right.plotly_chart(chart_style(fig, 390), width="stretch")
    elif section == "Movilidad":
        section_heading("🧭", "Movilidad", "Medios, distancia y tiempo de desplazamiento reportados por nuestra gente.")
        transport = categorical_count(socio, "transport", "Medio de transporte")
        distance = categorical_count(socio, "distance_range", "Distancia")
        commute = categorical_count(socio, "commute_range", "Tiempo de desplazamiento")
        left, right = st.columns(2, gap="medium")
        fig = px.bar(
            transport.sort_values("Personas"),
            x="Personas",
            y="Medio de transporte",
            orientation="h",
            title="Medio de transporte",
            color="Medio de transporte",
            color_discrete_sequence=PALETTE,
        )
        fig.update_layout(showlegend=False)
        left.plotly_chart(chart_style(fig, 370), width="stretch")
        fig = px.bar(
            distance,
            x="Distancia",
            y="Personas",
            title="Distancia al lugar de trabajo",
            color="Distancia",
            color_discrete_sequence=PALETTE,
        )
        fig.update_layout(showlegend=False)
        fig.update_xaxes(tickangle=-15)
        right.plotly_chart(chart_style(fig, 370), width="stretch")
        fig = px.bar(
            commute,
            x="Tiempo de desplazamiento",
            y="Personas",
            title="Tiempo reportado de desplazamiento",
            color="Personas",
            color_continuous_scale=[[0, "#FFF2B3"], [1, COLORS["blue"]]],
        )
        fig.update_layout(coloraxis_showscale=False)
        fig.update_xaxes(tickangle=-12)
        st.plotly_chart(chart_style(fig, 350), width="stretch")
        st.markdown(
            f"<div class='info-banner'><b>Distancia predominante:</b> {escape(str(metrics['predominant_distance']))}. "
            "El promedio de desplazamiento usa el punto medio de cada rango; ‘más de 180 min’ se representa como 180 minutos.</div>",
            unsafe_allow_html=True,
        )
    else:
        section_heading("⌂", "Entorno personal", "Estado civil, responsabilidad de hogar y mascotas como contexto agregado de bienestar.")
        pets = categorical_count(socio, "pet_type", "Mascota")
        marital = categorical_count(socio, "marital_status", "Estado civil")
        household = categorical_count(socio, "head_household", "Cabeza de hogar")
        left, middle, right = st.columns(3, gap="medium")
        fig = px.bar(
            pets.sort_values("Personas"),
            x="Personas",
            y="Mascota",
            orientation="h",
            title="Tipo de mascota",
            color="Mascota",
            color_discrete_sequence=PALETTE,
        )
        fig.update_layout(showlegend=False)
        left.plotly_chart(chart_style(fig, 360), width="stretch")
        fig = px.bar(
            marital.sort_values("Personas"),
            x="Personas",
            y="Estado civil",
            orientation="h",
            title="Estado civil",
            color="Personas",
            color_continuous_scale=[[0, "#DDF4FA"], [1, COLORS["blue"]]],
        )
        fig.update_layout(coloraxis_showscale=False)
        middle.plotly_chart(chart_style(fig, 360), width="stretch")
        fig = px.pie(
            household,
            names="Cabeza de hogar",
            values="Personas",
            hole=.58,
            title="Cabeza de hogar",
            color_discrete_sequence=[COLORS["blue"], COLORS["yellow"], COLORS["muted"]],
        )
        fig.update_traces(
            textposition="inside",
            textinfo="percent",
            hovertemplate="<b>%{label}</b><br>%{value} personas<br>%{percent}<extra></extra>",
        )
        right.plotly_chart(chart_style(fig, 360), width="stretch")


sync_navigation_from_url()
data = active_data()
topbar()
page = st.session_state.page
if page == "Inicio":
    render_home(data)
    window_navigation(data)
else:
    window_navigation(data)
    if page == "Carga de información":
        render_upload_window(data)
    elif data is None:
        number = "02" if page == "Planta y vacaciones" else "03"
        render_locked_dashboard(number, page)
    elif page == "Planta y vacaciones":
        render_plant_dashboard(data)
    else:
        render_socio_dashboard(data)

st.markdown("<div class='footer'>Conni · Inteligencia de Talento · Prototipo Streamlit 2026</div>", unsafe_allow_html=True)
