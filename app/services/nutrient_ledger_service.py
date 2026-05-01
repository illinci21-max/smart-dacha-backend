"""Nutrient ledger helpers for fertilizer applications."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from app.models.treatment_application import TreatmentApplication


_NUTRIENT_RE = re.compile(
    r"\b(N|P|K|Mg|Ca)\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:г|g)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NutrientLedgerEntry:
    nitrogen_g_m2: float = 0.0
    phosphorus_g_m2: float = 0.0
    potassium_g_m2: float = 0.0
    magnesium_g_m2: float = 0.0
    calcium_g_m2: float = 0.0

    @property
    def has_values(self) -> bool:
        return any(
            value > 0
            for value in (
                self.nitrogen_g_m2,
                self.phosphorus_g_m2,
                self.potassium_g_m2,
                self.magnesium_g_m2,
                self.calcium_g_m2,
            )
        )

    def to_action_payload(self) -> dict:
        return {
            "n_applied_g_m2": self.nitrogen_g_m2,
            "p_applied_g_m2": self.phosphorus_g_m2,
            "k_applied_g_m2": self.potassium_g_m2,
            "mg_applied_g_m2": self.magnesium_g_m2,
            "ca_applied_g_m2": self.calcium_g_m2,
        }


def parse_nutrient_amounts(text: str | None) -> NutrientLedgerEntry:
    values = {
        "n": 0.0,
        "p": 0.0,
        "k": 0.0,
        "mg": 0.0,
        "ca": 0.0,
    }
    if not text:
        return NutrientLedgerEntry()
    for name, raw_value in _NUTRIENT_RE.findall(text):
        key = name.casefold()
        values[key] += float(raw_value.replace(",", "."))
    return NutrientLedgerEntry(
        nitrogen_g_m2=values["n"],
        phosphorus_g_m2=values["p"],
        potassium_g_m2=values["k"],
        magnesium_g_m2=values["mg"],
        calcium_g_m2=values["ca"],
    )


def _decimal_to_float(value: Decimal | None) -> float:
    return float(value) if value is not None else 0.0


def _product_amount_g(value: str | None) -> float:
    if not value:
        return 0.0
    match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*(?:г|g)\b", value, re.IGNORECASE)
    if not match:
        return 0.0
    return float(match.group(1).replace(",", "."))


def nutrient_ledger_from_treatment(treatment: TreatmentApplication) -> NutrientLedgerEntry:
    direct = parse_nutrient_amounts(treatment.applied_amount or treatment.rate_amount)
    if direct.has_values:
        return direct

    product_g_m2 = _product_amount_g(treatment.applied_amount or treatment.rate_amount)
    area = _decimal_to_float(treatment.area_sqm)
    if product_g_m2 <= 0:
        return NutrientLedgerEntry()
    if area > 0:
        product_g_m2 = product_g_m2 / area

    return NutrientLedgerEntry(
        nitrogen_g_m2=product_g_m2 * _decimal_to_float(treatment.n_pct) / 100.0,
        phosphorus_g_m2=product_g_m2 * _decimal_to_float(treatment.p_pct) / 100.0,
        potassium_g_m2=product_g_m2 * _decimal_to_float(treatment.k_pct) / 100.0,
        magnesium_g_m2=product_g_m2 * _decimal_to_float(treatment.mg_pct) / 100.0,
        calcium_g_m2=product_g_m2 * _decimal_to_float(treatment.ca_pct) / 100.0,
    )
