"""
Synthetic claims with labelled anomalies for the risk suite.

A claim history (stored in MongoDB during the run, so the duplicate check
has something to find) plus incoming claims to validate. Anomalies are
labelled by type and variant; some variants are ones the rule-based checks
are not designed to catch, so recall below 1 is expected:

- duplicate: exact copy of a history claim, the same with different case or
  spacing in the name, or with a typo in the name.
- cost_outlier: above $150,000, between $55,000 and $140,000, or 8-15 times
  the diagnosis's usual cost while still under $50,000.
- date_inconsistency: discharge before admission, a stay over 90 days, or a
  date of service after discharge.
- missing_fields: one or two required fields, three or more, or only
  optional fields (address, provider ID).

Clean claims include legitimately expensive and elective procedures, which
the cost and keyword rules flag (false positives).
"""

import random
from datetime import date, timedelta
from typing import Any

from faker import Faker

from evals.dataset.documents import HOSPITALS, INPATIENT, OUTPATIENT, SEED, STATES

REQUIRED = ("policy_number", "claim_number", "patient_name", "diagnosis", "treatment_cost", "hospital_name")
OPTIONAL = ("hospital_address", "provider_id")

# (diagnosis, typical cost range in USD, stay range in days or None for outpatient)
ROUTINE = tuple(
    [(f"{c.description} ({c.code})", c.cost_range, None) for c in OUTPATIENT]
    + [(f"{c.description} ({c.code})", c.cost_range, c.stay_range) for c in INPATIENT]
)
EXPENSIVE = (
    ("Primary osteoarthritis, right knee (M17.11) - total knee replacement", (52000, 78000), (1, 3)),
    ("Coronary artery disease (I25.10) - coronary artery bypass graft", (95000, 145000), (5, 9)),
    ("Primary osteoarthritis, left hip (M16.12) - elective total hip replacement", (30000, 48000), (1, 3)),
)
LOW_COST = tuple(entry for entry in ROUTINE if entry[1][1] <= 2200)

# (anomaly type, variant, number of claims)
ANOMALIES = (
    ("duplicate", "exact", 8),
    ("duplicate", "name_case_or_spacing", 6),
    ("duplicate", "name_typo", 6),
    ("cost_outlier", "above_150k", 6),
    ("cost_outlier", "55k_to_140k", 7),
    ("cost_outlier", "relative_under_50k", 7),
    ("date_inconsistency", "discharge_before_admission", 8),
    ("date_inconsistency", "stay_over_90_days", 5),
    ("date_inconsistency", "service_after_discharge", 7),
    ("missing_fields", "one_or_two_required", 10),
    ("missing_fields", "three_or_more_required", 6),
    ("missing_fields", "optional_only", 4),
)


class _Generator:
    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.fake = Faker("en_US")
        self.fake.seed_instance(seed)
        self._names: set[str] = set()
        self._numbers: set[str] = set()
        self.hospitals = [
            (name, f"{self.fake.building_number()} {self.fake.street_name()}, {self.fake.city()}, "
                   f"{self.rng.choice(STATES)} {self.fake.zipcode()}")
            for name in HOSPITALS
        ]

    def name(self) -> str:
        while True:
            name = f"{self.fake.first_name()} {self.fake.last_name()}"
            if name not in self._names:
                self._names.add(name)
                return name

    def number(self, prefix: str) -> str:
        while True:
            value = f"{prefix}-{self.rng.randint(10000, 99999)}"
            if value not in self._numbers:
                self._numbers.add(value)
                return value

    def claim(self, claim_id: str, condition=None, cost: float | None = None) -> dict[str, Any]:
        diagnosis, (low, high), stay = condition or self.rng.choice(ROUTINE)
        hospital, address = self.rng.choice(self.hospitals)
        service = date(2025, 7, 1) + timedelta(days=self.rng.randint(0, 330))
        discharge = service + timedelta(days=self.rng.randint(*stay)) if stay else None
        return {
            "_id": claim_id,
            "claim_number": self.number("CLM-2026"),
            "policy_number": self.number("POL-2026"),
            "patient_name": self.name(),
            "diagnosis": diagnosis,
            "treatment_cost": cost if cost is not None else round(self.rng.uniform(low, high), 2),
            "hospital_name": hospital,
            "hospital_address": address,
            "provider_id": f"PRV-{self.rng.randint(100000, 999999)}",
            "date_of_service": service.isoformat(),
            "date_of_admission": service.isoformat() if stay else None,
            "date_of_discharge": discharge.isoformat() if discharge else None,
            "status": "pending",
        }


def _typo(name: str, rng: random.Random) -> str:
    """Swap two adjacent letters inside the last name."""
    first, last = name.split(" ", 1)
    position = rng.randrange(1, len(last) - 1)
    letters = list(last)
    letters[position], letters[position + 1] = letters[position + 1], letters[position]
    typo = "".join(letters)
    return f"{first} {typo}" if typo != last else f"{first} {last}e"


def _apply(gen: _Generator, claim: dict[str, Any], kind: str, variant: str, history: list[dict],
           *, duplicate: bool = False) -> None:
    """Inject one anomaly. On a duplicate, the fields that make it a duplicate are left alone."""
    rng = gen.rng
    if kind == "duplicate":
        original = rng.choice(history)
        for key in ("patient_name", "diagnosis", "date_of_service", "date_of_admission", "date_of_discharge",
                    "hospital_name", "hospital_address", "provider_id", "policy_number"):
            claim[key] = original[key]
        claim["treatment_cost"] = round(original["treatment_cost"] * rng.uniform(0.95, 1.05), 2)
        if variant == "name_case_or_spacing":
            claim["patient_name"] = rng.choice((str.upper, str.lower))(original["patient_name"]) + "  "
        elif variant == "name_typo":
            claim["patient_name"] = _typo(original["patient_name"], rng)
    elif kind == "cost_outlier":
        low_cost_diagnosis, (low, high), stay = rng.choice(LOW_COST)
        if not duplicate:
            claim["diagnosis"] = low_cost_diagnosis
            claim["date_of_admission"] = claim["date_of_discharge"] = None
        if variant == "above_150k":
            claim["treatment_cost"] = round(rng.uniform(155000, 400000), 2)
        elif variant == "55k_to_140k":
            claim["treatment_cost"] = round(rng.uniform(55000, 140000), 2)
        else:
            claim["treatment_cost"] = round(min(high * rng.uniform(8, 15), 49000), 2)
    elif kind == "date_inconsistency":
        admission = date.fromisoformat(claim["date_of_service"])
        claim["date_of_admission"] = admission.isoformat()
        if variant == "discharge_before_admission":
            claim["date_of_discharge"] = (admission - timedelta(days=rng.randint(1, 20))).isoformat()
        elif variant == "stay_over_90_days":
            claim["date_of_discharge"] = (admission + timedelta(days=rng.randint(95, 200))).isoformat()
        else:
            discharge = admission + timedelta(days=rng.randint(1, 5))
            claim["date_of_discharge"] = discharge.isoformat()
            claim["date_of_service"] = (discharge + timedelta(days=rng.randint(3, 30))).isoformat()
    elif kind == "missing_fields":
        candidates = [f for f in REQUIRED if f not in ("patient_name", "diagnosis")] if duplicate else REQUIRED
        if variant == "one_or_two_required":
            removed = rng.sample(candidates, rng.randint(1, 2))
        elif variant == "three_or_more_required":
            removed = rng.sample(candidates, rng.randint(3, 4))
        else:
            removed = list(OPTIONAL)
        for field in removed:
            claim[field] = None
    else:  # pragma: no cover - guarded by ANOMALIES
        raise ValueError(kind)


def build_risk_claims(seed: int = SEED + 1) -> dict[str, Any]:
    """History claims plus labelled incoming claims, deterministic for a seed."""
    gen = _Generator(seed)
    history = [gen.claim(f"hist-{index:03d}") for index in range(1, 61)]

    cases: list[tuple[list[tuple[str, str]], dict]] = []
    for _ in range(110):
        cases.append(([], {}))
    for index in range(10):
        cases.append(([], {"condition": EXPENSIVE[index % len(EXPENSIVE)]}))
    for kind, variant, count in ANOMALIES:
        for _ in range(count):
            cases.append(([(kind, variant)], {}))
    # A few claims with two anomalies at once.
    for kind, variant in (("cost_outlier", "55k_to_140k"), ("date_inconsistency", "discharge_before_admission"),
                          ("missing_fields", "one_or_two_required")):
        for _ in range(2):
            cases.append(([("duplicate", "exact"), (kind, variant)], {}))
    gen.rng.shuffle(cases)

    claims = []
    for index, (anomalies, options) in enumerate(cases, start=1):
        claim = gen.claim(f"rc-{index:03d}", options.get("condition"))
        for kind, variant in anomalies:
            _apply(gen, claim, kind, variant, history, duplicate=kind != "duplicate" and len(anomalies) > 1)
        claims.append({
            "id": claim["_id"],
            "claim": claim,
            "anomalous": bool(anomalies),
            "anomalies": [{"type": kind, "variant": variant} for kind, variant in anomalies],
        })
    return {"seed": seed, "history": history, "claims": claims}
