from io import BytesIO
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from conni.data import _to_number, canonical_personal, canonical_sociodemo, canonical_survey, demo_data, load_master


def test_demo_is_deterministic_and_contains_vacancies():
    first = demo_data()
    second = demo_data()
    assert len(first.personal) == len(second.personal)
    assert first.personal["is_vacant"].sum() > 0
    assert first.personal["period"].nunique() == 4
    assert first.sociodemo["person_id"].notna().all()


def test_canonical_personal_preserves_position_without_person():
    raw = pd.DataFrame(
        {
            "Mes": ["Jul", "Jul"],
            "Año": [2026, 2026],
            "ID Posición": ["001", "002"],
            "No personal": ["100", None],
            "No Documento": ["900", None],
            "Vacante": [False, True],
            "Orden de No Cubrir": ["NO", "SI"],
        }
    )
    result = canonical_personal(raw)
    assert len(result) == 2
    assert result["period"].tolist() == ["2026-07", "2026-07"]
    assert result["is_occupied"].tolist() == [True, False]
    assert result["is_vacant"].tolist() == [False, True]


def test_vacant_boolean_is_source_of_truth():
    raw = pd.DataFrame(
        {
            "Mes": ["Jul", "Jul"],
            "Año": [2026, 2026],
            "ID Posición": ["001", "002"],
            "No personal": ["100", None],
            "Vacante": [True, False],
        }
    )
    result = canonical_personal(raw)
    assert result["is_vacant"].tolist() == [True, False]
    assert result["vacancy_flag_conflict"].tolist() == [True, True]


def test_number_and_excel_serial_normalization():
    numbers = _to_number(pd.Series(["6.920,45", "6,920.45", "12,5", 3.25]))
    assert numbers.tolist() == [6920.45, 6920.45, 12.5, 3.25]
    survey = canonical_survey(pd.DataFrame({"Cédula": ["1"], "Per_Info": [46213]}))
    assert survey.loc[0, "period"] == "2026-07"


def test_load_master_contract():
    personal = pd.DataFrame({"Mes": ["Jul"], "Año": [2026], "ID Posición": ["1"], "No personal": ["7"]})
    socio = pd.DataFrame({"Mes": ["Jul"], "Año": [2026], "No de Personal": ["7"], "Fecha de Nacimiento": ["1990-01-01"]})
    survey = pd.DataFrame({"Cédula": ["99"], "Correo electrónico": ["demo@example.com"]})
    content = BytesIO()
    with pd.ExcelWriter(content, engine="openpyxl") as writer:
        socio.to_excel(writer, sheet_name="01_SRC_SOCIODEMO", index=False)
        personal.to_excel(writer, sheet_name="02_SRC_PERSONAL", index=False)
        survey.to_excel(writer, sheet_name="03_SRC_CORREOS", index=False)
    result = load_master(content.getvalue())
    assert len(result.personal) == 1
    assert len(result.sociodemo) == 1
    assert len(result.encuesta) == 1
