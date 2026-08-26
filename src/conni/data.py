from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
import unicodedata
from typing import BinaryIO, Mapping

import numpy as np
import pandas as pd


MONTHS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}


@dataclass(frozen=True)
class ConniData:
    personal: pd.DataFrame
    sociodemo: pd.DataFrame
    encuesta: pd.DataFrame
    source_name: str
    is_demo: bool = False


class WorkbookValidationError(ValueError):
    """Raised when a workbook cannot satisfy the minimum Conni contract."""


def normalize_label(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower().replace("\xa0", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_key(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).replace("\xa0", " ").strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    text = re.sub(r"[\x00-\x1f\x7f]", "", text).strip()
    return text or None


def _rename_known(df: pd.DataFrame, aliases: Mapping[str, str]) -> pd.DataFrame:
    rename: dict[object, str] = {}
    used: set[str] = set()
    for column in df.columns:
        normalized = normalize_label(column)
        target = aliases.get(normalized)
        if target and target not in used:
            rename[column] = target
            used.add(target)
    return df.rename(columns=rename).copy()


def _series(df: pd.DataFrame, name: str, default: object = None) -> pd.Series:
    if name in df.columns:
        return df[name]
    return pd.Series([default] * len(df), index=df.index, dtype="object")


def _to_number(series: pd.Series) -> pd.Series:
    def parse_number(value: object) -> object:
        if value is None or pd.isna(value):
            return None
        if isinstance(value, (int, float, np.number)):
            return value
        text = re.sub(r"[^0-9,.-]", "", str(value).strip())
        if not text:
            return None
        if "," in text and "." in text:
            # Accept both Colombian (6.920,45) and international (6,920.45) formats.
            text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        return text

    cleaned = series.map(parse_number)
    return pd.to_numeric(cleaned, errors="coerce")


def _boolish(series: pd.Series) -> pd.Series:
    truthy = {"true", "verdadero", "si", "sí", "1", "yes", "x"}
    return series.map(lambda value: normalize_label(value) in {normalize_label(x) for x in truthy})


def _period_label(month: pd.Series, year: pd.Series, per_info: pd.Series) -> pd.Series:
    numeric_date = pd.to_numeric(per_info, errors="coerce")
    excel_serial = numeric_date.between(20_000, 60_000)
    parsed_date = pd.to_datetime(per_info.where(~excel_serial), errors="coerce")
    parsed_date.loc[excel_serial] = pd.to_datetime(
        numeric_date.loc[excel_serial], unit="D", origin="1899-12-30", errors="coerce"
    )

    def month_number(value: object) -> float:
        if value is None or pd.isna(value):
            return np.nan
        text = normalize_label(value)
        if text[:3] in MONTHS:
            return float(MONTHS[text[:3]])
        try:
            number = int(float(str(value)))
            return float(number) if 1 <= number <= 12 else np.nan
        except (TypeError, ValueError):
            return np.nan

    month_num = month.map(month_number)
    year_num = pd.to_numeric(year, errors="coerce")
    labels: list[str | None] = []
    for idx in month.index:
        y = year_num.loc[idx]
        m = month_num.loc[idx]
        if pd.notna(y) and pd.notna(m):
            labels.append(f"{int(y):04d}-{int(m):02d}")
        elif pd.notna(parsed_date.loc[idx]):
            labels.append(parsed_date.loc[idx].strftime("%Y-%m"))
        else:
            labels.append(None)
    return pd.Series(labels, index=month.index, dtype="object")


PERSONAL_ALIASES = {
    "cod": "record_id",
    "mes": "month",
    "ano": "year",
    "per info": "snapshot_date",
    "unidad estrategica": "strategy",
    "unidad organizativa": "organization",
    "id posicion": "position_id",
    "posicion": "position_name",
    "tipo de vinculo": "link_type",
    "tipo de posicion": "position_type",
    "motivo de aprobacion gral": "approval_reason",
    "vacante": "vacant_flag_raw",
    "orden de no cubrir": "onc_raw",
    "no personal": "person_id",
    "no documento": "document_id",
    "nombre completo": "full_name",
    "genero": "gender",
    "fecha de ingreso": "hire_date",
    "antiguedad en anos": "tenure_years",
    "clase de contrato": "contract_class",
    "periodos acumulados": "vacation_periods",
    "pasivo vacacional": "vacation_days",
    "periodos luego de sol": "vacation_periods_net",
    "dias luego de sol": "vacation_days_net",
    "encuesta": "survey_status",
}


SOCIO_ALIASES = {
    "mes": "month",
    "ano": "year",
    "per info": "snapshot_date",
    "no de personal": "person_id",
    "sexo biologico": "gender",
    "fecha de nacimiento": "birth_date",
    "edad anos del empleado": "age",
    "rango de edades": "age_range",
    "estado civil": "marital_status",
    "es usted cabeza de hogar picklist label": "head_household",
    "es usted cabeza de hogar": "head_household",
    "medio de transporte picklist label": "transport",
    "medio de transporte": "transport",
    "distancia en km picklist label": "distance_range",
    "distancia en km": "distance_range",
    "tiempo de desplazamiento picklist label": "commute_range",
    "tiempo de desplazamiento": "commute_range",
    "tipo de mascota picklist label": "pet_type",
    "tipo de mascota": "pet_type",
    "numero de mascotas picklist label": "pet_count",
    "numero de mascotas": "pet_count",
    "unidad estrategica": "strategy",
    "unidad organizativa": "organization",
    "id posicion": "position_id",
    "tipo de vinculo picklist label": "link_type",
    "tipo de vinculo": "link_type",
}


SURVEY_ALIASES = {
    "id": "response_id",
    "hora de inicio": "started_at",
    "hora de finalizacion": "finished_at",
    "correo electronico": "email",
    "cedula": "document_id",
    "mes": "month",
    "ano": "year",
    "per info": "snapshot_date",
    "tienes hijos": "has_children",
    "cuantos hijos tienes": "children_count",
    "cuaantos hijos tienes": "children_count",
    "tienes algun emprendimiento": "has_business",
}


def canonical_personal(raw: pd.DataFrame) -> pd.DataFrame:
    df = _rename_known(raw, PERSONAL_ALIASES)
    required = {"position_id", "person_id"}
    if not required.intersection(df.columns):
        raise WorkbookValidationError(
            "La hoja Personal no contiene 'ID Posición' ni 'No personal'."
        )
    df["person_id"] = _series(df, "person_id").map(normalize_key)
    df["document_id"] = _series(df, "document_id").map(normalize_key)
    df["position_id"] = _series(df, "position_id").map(normalize_key)
    df["period"] = _period_label(
        _series(df, "month"), _series(df, "year"), _series(df, "snapshot_date")
    )
    vacant_raw = _series(df, "vacant_flag_raw")
    vacant_flag_present = vacant_raw.map(
        lambda value: value is not None and not pd.isna(value) and bool(str(value).strip())
    )
    df["vacant_flag"] = _boolish(vacant_raw)
    df["onc_flag"] = _series(df, "onc_raw").map(
        lambda value: normalize_label(value) in {"si", "true", "verdadero", "1"}
    )
    for column in (
        "tenure_years",
        "vacation_periods",
        "vacation_days",
        "vacation_periods_net",
        "vacation_days_net",
    ):
        df[column] = _to_number(_series(df, column))
    for column in (
        "strategy",
        "organization",
        "position_name",
        "position_type",
        "link_type",
        "approval_reason",
        "gender",
        "contract_class",
        "full_name",
    ):
        df[column] = _series(df, column).map(
            lambda value: None if value is None or pd.isna(value) or not str(value).strip() else str(value).strip()
        )
    has_position = df["position_id"].notna()
    has_person = df["person_id"].notna()
    inferred_vacant = ~has_person
    # 'Vacante' is the business source of truth. Person presence is only a fallback
    # for legacy rows where the source flag is empty.
    df["is_vacant"] = has_position & df["vacant_flag"].where(vacant_flag_present, inferred_vacant)
    df["is_occupied"] = has_position & ~df["is_vacant"]
    df["vacancy_flag_conflict"] = (
        has_position & vacant_flag_present & (df["vacant_flag"] == has_person)
    )
    return df.loc[has_position | has_person].reset_index(drop=True)


def canonical_sociodemo(raw: pd.DataFrame) -> pd.DataFrame:
    df = _rename_known(raw, SOCIO_ALIASES)
    if "person_id" not in df.columns:
        raise WorkbookValidationError("La hoja Sociodemo no contiene 'No de Personal'.")
    df["person_id"] = _series(df, "person_id").map(normalize_key)
    df["position_id"] = _series(df, "position_id").map(normalize_key)
    df["period"] = _period_label(
        _series(df, "month"), _series(df, "year"), _series(df, "snapshot_date")
    )
    df["birth_date"] = pd.to_datetime(_series(df, "birth_date"), errors="coerce")
    supplied_age = _to_number(_series(df, "age"))
    today = pd.Timestamp.today().normalize()
    calculated_age = ((today - df["birth_date"]).dt.days / 365.2425).round(1)
    df["age"] = supplied_age.fillna(calculated_age)
    for column in (
        "gender",
        "age_range",
        "marital_status",
        "head_household",
        "transport",
        "distance_range",
        "commute_range",
        "pet_type",
        "strategy",
        "organization",
        "link_type",
    ):
        df[column] = _series(df, column).map(
            lambda value: None if value is None or pd.isna(value) or not str(value).strip() else str(value).strip()
        )
    df["pet_count"] = _to_number(_series(df, "pet_count"))
    return df.loc[df["person_id"].notna()].reset_index(drop=True)


def canonical_survey(raw: pd.DataFrame) -> pd.DataFrame:
    df = _rename_known(raw, SURVEY_ALIASES)
    df["document_id"] = _series(df, "document_id").map(normalize_key)
    df["period"] = _period_label(
        _series(df, "month"), _series(df, "year"), _series(df, "snapshot_date")
    )
    df["email"] = _series(df, "email").map(
        lambda value: None if value is None or pd.isna(value) or not str(value).strip() else str(value).strip().lower()
    )
    df["children_count"] = _to_number(_series(df, "children_count"))
    return df.reset_index(drop=True)


def _find_sheet(sheets: Mapping[str, pd.DataFrame], expected: str) -> pd.DataFrame | None:
    expected_norm = normalize_label(expected)
    for name, frame in sheets.items():
        normalized = normalize_label(name)
        if normalized == expected_norm or expected_norm in normalized:
            return frame
    return None


def load_master(content: bytes | BinaryIO, source_name: str = "Maestro_Databricks.xlsx") -> ConniData:
    payload = content if hasattr(content, "read") else BytesIO(content)
    try:
        sheets = pd.read_excel(payload, sheet_name=None, dtype=object, engine="openpyxl")
    except Exception as exc:  # pragma: no cover - engine errors vary
        raise WorkbookValidationError(f"No fue posible leer el archivo Excel: {exc}") from exc
    personal = _find_sheet(sheets, "02_SRC_PERSONAL")
    socio = _find_sheet(sheets, "01_SRC_SOCIODEMO")
    survey = _find_sheet(sheets, "03_SRC_CORREOS")
    missing = [
        label
        for label, frame in (
            ("01_SRC_SOCIODEMO", socio),
            ("02_SRC_PERSONAL", personal),
            ("03_SRC_CORREOS", survey),
        )
        if frame is None
    ]
    if missing:
        raise WorkbookValidationError("Faltan hojas requeridas: " + ", ".join(missing))
    return ConniData(
        personal=canonical_personal(personal),
        sociodemo=canonical_sociodemo(socio),
        encuesta=canonical_survey(survey),
        source_name=source_name,
        is_demo=False,
    )


def demo_data(seed: int = 2026) -> ConniData:
    """Create deterministic, synthetic data for the public GitHub demo."""
    rng = np.random.default_rng(seed)
    periods = ["2026-04", "2026-05", "2026-06", "2026-07"]
    strategies = [
        "Gerencia Operación de Subsidios",
        "Gerencia Operaciones y Tesorería",
        "Gerencia Finanzas Corporativas",
        "Subdirección Financiera",
    ]
    organizations = {
        strategies[0]: "Gerencia Operación de Subsidios",
        strategies[1]: "Gerencia Operaciones y Tesorería",
        strategies[2]: "Gerencia Finanzas Corporativas",
        strategies[3]: "Staff Subdirección Financiera",
    }
    personal_rows: list[dict[str, object]] = []
    socio_rows: list[dict[str, object]] = []
    survey_rows: list[dict[str, object]] = []
    person_counter = 10000
    for pidx, period in enumerate(periods):
        positions = 112 + pidx * 3
        vacancies = 8 + pidx
        onc = 3 + (pidx % 2)
        occupied = positions - vacancies - onc
        for idx in range(positions):
            strategy = strategies[idx % len(strategies)]
            is_occupied = idx < occupied
            is_onc = occupied <= idx < occupied + onc
            person_id = str(person_counter + idx) if is_occupied else None
            reason = (
                "ESTUDIANTE EN PRACTICA"
                if is_occupied and idx % 19 == 0
                else "SISO"
                if is_occupied and idx % 47 == 0
                else "OPERACION PERMANENTE"
            )
            gender = "Femenino" if idx % 5 < 3 else "Masculino"
            personal_rows.append(
                {
                    "period": period,
                    "position_id": f"P-{period}-{idx:03d}",
                    "person_id": person_id,
                    "document_id": f"D-{person_id}" if person_id else None,
                    "strategy": strategy,
                    "organization": organizations[strategy],
                    "position_name": "Cargo demostración",
                    "position_type": "Planta",
                    "link_type": "Colsubsidio",
                    "approval_reason": reason,
                    "gender": gender if is_occupied else None,
                    "contract_class": "Indefinido" if is_occupied else None,
                    "tenure_years": float(rng.uniform(0.5, 22)) if is_occupied else np.nan,
                    "vacation_periods": float(rng.choice([0, 1, 1, 1, 2, 2, 3])) if is_occupied else np.nan,
                    "vacation_days": float(rng.integers(0, 48)) if is_occupied else np.nan,
                    "vacation_periods_net": float(rng.choice([0, 0, 1, 1, 2])) if is_occupied else np.nan,
                    "vacation_days_net": float(rng.integers(0, 38)) if is_occupied else np.nan,
                    "vacant_flag": not is_occupied,
                    "onc_flag": is_onc,
                    "is_occupied": is_occupied,
                    "is_vacant": not is_occupied,
                    "vacancy_flag_conflict": False,
                }
            )
            if is_occupied:
                age = int(rng.integers(21, 62))
                transport = rng.choice(
                    ["Transporte Público", "Carro", "Moto", "Bicicleta", "Otro"],
                    p=[0.55, 0.14, 0.17, 0.08, 0.06],
                )
                distance = rng.choice(["1-5 km", "6-10 km", "11-20 km", "21-50 km", "Más de 50 km"])
                commute = rng.choice(["30 minutos", "60 minutos", "90 minutos", "120 minutos", "Más de 120 minutos"])
                socio_rows.append(
                    {
                        "period": period,
                        "person_id": person_id,
                        "position_id": f"P-{period}-{idx:03d}",
                        "strategy": strategy,
                        "organization": organizations[strategy],
                        "gender": gender,
                        "age": age,
                        "age_range": "18-25" if age <= 25 else "26-35" if age <= 35 else "36-45" if age <= 45 else "46-55" if age <= 55 else "56 o más",
                        "marital_status": rng.choice(["Soltero/a", "En pareja", "Separado/a"], p=[0.48, 0.44, 0.08]),
                        "head_household": rng.choice(["Sí", "No"], p=[0.38, 0.62]),
                        "transport": transport,
                        "distance_range": distance,
                        "commute_range": commute,
                        "pet_type": rng.choice(["Perro", "Gato", "Ninguna", "Otro"], p=[0.42, 0.22, 0.30, 0.06]),
                        "pet_count": int(rng.integers(0, 4)),
                        "birth_date": pd.NaT,
                        "link_type": "Colsubsidio",
                    }
                )
                if period == periods[-1] and idx % 5 != 0:
                    survey_rows.append(
                        {
                            "period": period,
                            "document_id": f"D-{person_id}",
                            "email": f"persona{idx:03d}@example.com",
                            "children_count": float(rng.choice([0, 0, 1, 1, 2, 3])),
                        }
                    )
        person_counter += 1000
    return ConniData(
        personal=pd.DataFrame(personal_rows),
        sociodemo=pd.DataFrame(socio_rows),
        encuesta=pd.DataFrame(survey_rows),
        source_name="Demostración sintética",
        is_demo=True,
    )
