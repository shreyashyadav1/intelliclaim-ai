"""
Synthetic claim documents with ground truth, and questions generated from it.

Everything is derived from one seeded random generator (and a seeded Faker
instance), so the same code and package versions always produce the same
documents. People come from Faker; hospitals, insurers and plans are
invented names, and every page carries a line saying it is fictional.
Provider IDs use a PRV- prefix rather than the NPI format, and phone numbers
use the 555-01xx range reserved for fiction.

Document families (60 documents from 24 patient episodes):
- 24 medical invoices (one per episode),
- 12 outpatient medical reports and 12 two-page discharge summaries,
- 12 insurance policy summaries.

Each document records its class label (policy summaries are
"policy_document"), its pages (the exact text rendered into the PDF), the
eleven extraction fields as normalised values, and the same values as
printed.
"""

import random
import textwrap
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from faker import Faker

from models.extraction import CLAIM_FIELDS
from utils.paged_text import PagedText

SEED = 7341
DISCLAIMER = "Synthetic document for software evaluation. All people, organizations and identifiers are fictional."
LINE_WIDTH = 92

HOSPITALS = (
    "Juniperwick Medical Center",
    "Tamarack Hollow General Hospital",
    "Bramblemoor Community Clinic",
    "Marigold Quarry Regional Hospital",
    "Fernhollow Valley Medical Center",
    "Larkspur Bay Health Center",
    "Cinderholt Memorial Hospital",
    "Wrenfield Crossing Hospital",
)
INSURERS = ("Bluefern Mutual Health", "Quillstone Health Plan", "Tidewren Assurance")
PLAN_TIERS = ("Bronze 6000", "Silver 3500", "Silver 2500", "Gold 1500", "Gold 1000", "Platinum 500")
STATES = ("CA", "OR", "WA", "CO", "TX", "IL", "NY", "PA", "OH", "GA", "NC", "MN")
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


@dataclass(frozen=True)
class Outpatient:
    code: str
    description: str
    cost_range: tuple[int, int]  # USD
    complaint: str
    plan: str
    items: tuple[str, ...]


@dataclass(frozen=True)
class Inpatient:
    code: str
    description: str
    cost_range: tuple[int, int]
    stay_range: tuple[int, int]  # days
    course: str
    medication: str
    items: tuple[str, ...]


OUTPATIENT = (
    Outpatient("J06.9", "Acute upper respiratory infection", (180, 650),
               "Sore throat, nasal congestion and low-grade fever for four days.",
               "Supportive care, fluids and rest. Return if symptoms persist beyond ten days.",
               ("Office visit", "Rapid strep test", "Medication")),
    Outpatient("E11.9", "Type 2 diabetes mellitus without complications", (220, 900),
               "Routine review of blood sugar control and medication.",
               "Continue metformin, reinforce diet and exercise, repeat HbA1c in three months.",
               ("Office visit", "HbA1c laboratory test", "Lipid panel")),
    Outpatient("I10", "Essential (primary) hypertension", (150, 600),
               "Follow-up of elevated blood pressure readings at home.",
               "Start lisinopril 10 mg daily and monitor blood pressure at home twice a week.",
               ("Office visit", "Basic metabolic panel", "Electrocardiogram")),
    Outpatient("S52.501A", "Fracture of lower end of right radius", (1800, 6500),
               "Wrist pain and swelling after a fall on an outstretched hand.",
               "Closed reduction and short arm cast; recheck alignment with X-ray in one week.",
               ("Emergency evaluation", "Wrist X-ray", "Closed reduction", "Cast application")),
    Outpatient("M54.50", "Low back pain", (240, 1200),
               "Lower back pain for two weeks after lifting boxes, no leg weakness.",
               "Physical therapy twice weekly, ibuprofen as needed, avoid heavy lifting.",
               ("Office visit", "Lumbar spine X-ray", "Physical therapy evaluation")),
    Outpatient("J45.909", "Asthma, uncomplicated", (200, 800),
               "Increased wheezing at night over the past month.",
               "Add an inhaled corticosteroid, review inhaler technique, written action plan given.",
               ("Office visit", "Spirometry", "Medication")),
    Outpatient("G43.909", "Migraine, not intractable", (300, 1500),
               "Recurrent throbbing headaches with light sensitivity, two per week.",
               "Start sumatriptan as needed, keep a headache diary, reduce caffeine.",
               ("Office visit", "Neurological assessment", "Medication")),
    Outpatient("L03.115", "Cellulitis of right lower limb", (400, 2200),
               "Redness, warmth and swelling of the right lower leg for three days.",
               "Oral cephalexin for seven days, elevate the leg, mark the border of redness.",
               ("Urgent care visit", "Complete blood count", "Medication")),
)

INPATIENT = (
    Inpatient("K35.80", "Acute appendicitis", (14000, 32000), (1, 3),
              "Admitted with right lower quadrant pain. Laparoscopic appendectomy was performed without "
              "complications and the patient tolerated a regular diet before discharge.",
              "Oxycodone 5 mg every 6 hours as needed for pain",
              ("Room and board", "Operating room services", "Anesthesia", "Pharmacy", "Laboratory")),
    Inpatient("J18.9", "Pneumonia, unspecified organism", (6000, 18000), (3, 6),
              "Admitted with fever, cough and hypoxia. Treated with intravenous antibiotics and oxygen, "
              "with steady improvement in breathing and oxygen saturation.",
              "Amoxicillin-clavulanate 875 mg twice daily for 5 days",
              ("Room and board", "Respiratory therapy", "Pharmacy", "Chest imaging", "Laboratory")),
    Inpatient("K81.0", "Acute cholecystitis", (12000, 28000), (2, 4),
              "Admitted with right upper quadrant pain and fever. Laparoscopic cholecystectomy was "
              "performed on the second hospital day.",
              "Acetaminophen 1000 mg every 8 hours as needed",
              ("Room and board", "Operating room services", "Anesthesia", "Imaging", "Pharmacy")),
    Inpatient("I48.91", "Atrial fibrillation", (8000, 26000), (2, 5),
              "Admitted with palpitations and rapid ventricular response. Rate control was achieved and "
              "anticoagulation was started after risk assessment.",
              "Apixaban 5 mg twice daily",
              ("Room and board", "Cardiac monitoring", "Echocardiogram", "Pharmacy", "Laboratory")),
    Inpatient("N20.0", "Calculus of kidney", (5000, 15000), (1, 3),
              "Admitted with severe flank pain. Imaging showed a 6 mm kidney stone, which passed with "
              "hydration and pain control.",
              "Tamsulosin 0.4 mg daily for 14 days",
              ("Room and board", "CT imaging", "Pharmacy", "Laboratory")),
    Inpatient("I21.4", "Non-ST elevation myocardial infarction", (25000, 68000), (3, 7),
              "Admitted with chest pain and elevated troponin. Cardiac catheterization with stent "
              "placement was performed, followed by cardiac rehabilitation teaching.",
              "Clopidogrel 75 mg daily",
              ("Room and board", "Cardiac catheterization", "Coronary stent", "Pharmacy", "Laboratory")),
    Inpatient("S72.001A", "Fracture of right femoral neck", (28000, 55000), (4, 8),
              "Admitted after a fall at home. Hip hemiarthroplasty was performed and physical therapy "
              "started on the first postoperative day.",
              "Enoxaparin 40 mg daily for 28 days",
              ("Room and board", "Operating room services", "Implant", "Physical therapy", "Pharmacy")),
    Inpatient("A41.9", "Sepsis, unspecified organism", (30000, 90000), (5, 10),
              "Admitted with fever, low blood pressure and confusion. Treated with intravenous fluids "
              "and antibiotics in the intensive care unit before transfer to the ward.",
              "Levofloxacin 750 mg daily for 7 days",
              ("Intensive care", "Room and board", "Pharmacy", "Laboratory", "Blood cultures")),
)


def document_text(doc: dict[str, Any]) -> str:
    """The ground-truth text of a generated document, pages joined as the application joins them."""
    return PagedText.from_pages(doc["pages"]).text


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def us_date(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def long_date(value: date) -> str:
    return f"{MONTHS[value.month - 1]} {value.day}, {value.year}"


def money(cents: int) -> str:
    return f"${cents // 100:,}.{cents % 100:02d}"


def wrap(text: str) -> list[str]:
    return textwrap.wrap(text, LINE_WIDTH)


def split_amount(total_cents: int, parts: int, rng: random.Random) -> list[int]:
    """Split a total into `parts` positive amounts that add up exactly."""
    weights = [rng.uniform(1.0, 4.0) for _ in range(parts)]
    amounts = [int(total_cents * weight / sum(weights)) for weight in weights[:-1]]
    return [*amounts, total_cents - sum(amounts)]


class _Unique:
    """Draws values from a generator until one has not been used before."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def draw(self, make) -> str:
        while True:
            value = make()
            if value not in self._seen:
                self._seen.add(value)
                return value


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
@dataclass
class Episode:
    patient: str
    insurer: str
    policy_number: str
    claim_number: str
    hospital: dict[str, str]
    physician: dict[str, str]
    condition: Outpatient | Inpatient
    service_date: date
    discharge_date: date | None
    total_cents: int
    items: list[tuple[str, int]]


def _world(rng: random.Random, fake: Faker) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    hospitals = []
    for name in HOSPITALS:
        street = f"{fake.building_number()} {fake.street_name()}"
        address = f"{street}, {fake.city()}, {rng.choice(STATES)} {fake.zipcode()}"
        phone = f"(555) 01{rng.randint(0, 99):02d}-{rng.randint(1000, 9999)}"
        hospitals.append({"name": name, "address": address, "phone": phone})

    provider_ids = _Unique()
    physicians = []
    for index in range(12):
        physicians.append({
            "name": f"Dr. {fake.first_name()} {fake.last_name()}",
            "provider_id": provider_ids.draw(lambda: f"PRV-{rng.randint(100000, 999999)}"),
            "hospital": HOSPITALS[index % len(HOSPITALS)],
        })
    return hospitals, physicians


def _episodes(rng: random.Random, fake: Faker, hospitals, physicians, count: int = 24) -> list[Episode]:
    names, policies, claims = _Unique(), _Unique(), _Unique()
    outpatient = list(OUTPATIENT)
    inpatient = list(INPATIENT)
    rng.shuffle(outpatient)
    rng.shuffle(inpatient)
    episodes = []
    for index in range(count):
        is_inpatient = index % 2 == 1
        pool = inpatient if is_inpatient else outpatient
        condition = pool[(index // 2) % len(pool)]
        physician = physicians[rng.randrange(len(physicians))]
        hospital = next(h for h in hospitals if h["name"] == physician["hospital"])
        service_date = date(2026, 1, 5) + timedelta(days=rng.randint(0, 170))
        discharge = service_date + timedelta(days=rng.randint(*condition.stay_range)) if is_inpatient else None
        low, high = condition.cost_range
        total = rng.randint(low * 100, high * 100)
        amounts = split_amount(total, len(condition.items), rng)
        episodes.append(Episode(
            patient=names.draw(lambda: f"{fake.first_name()} {fake.last_name()}"),
            insurer=rng.choice(INSURERS),
            policy_number=policies.draw(lambda: f"POL-2026-{rng.randint(10000, 99999)}"),
            claim_number=claims.draw(lambda: f"CLM-2026-{rng.randint(10000, 99999)}"),
            hospital=hospital,
            physician=physician,
            condition=condition,
            service_date=service_date,
            discharge_date=discharge,
            total_cents=total,
            items=list(zip(condition.items, amounts, strict=True)),
        ))
    return episodes


def _header(hospital: dict[str, str]) -> list[str]:
    return [hospital["name"], hospital["address"], f"Phone: {hospital['phone']}", ""]


def _fields(**values: Any) -> dict[str, Any]:
    return {name: values.get(name) for name in CLAIM_FIELDS}


def _invoice(episode: Episode, number: str, rng: random.Random) -> dict[str, Any]:
    condition = episode.condition
    diagnosis = f"{condition.description} ({condition.code})"
    invoice_date = (episode.discharge_date or episode.service_date) + timedelta(days=rng.randint(3, 10))
    lines = [
        *_header(episode.hospital),
        "INVOICE",
        f"Invoice number: {number}",
        f"Invoice date: {us_date(invoice_date)}",
        "",
        f"Patient: {episode.patient}",
        f"Insurer: {episode.insurer}",
        f"Policy number: {episode.policy_number}",
        f"Claim number: {episode.claim_number}",
        f"Attending physician: {episode.physician['name']}",
        f"Provider ID: {episode.physician['provider_id']}",
        f"Diagnosis: {diagnosis}",
        f"Date of service: {us_date(episode.service_date)}",
    ]
    if episode.discharge_date:
        lines += [
            f"Admission date: {us_date(episode.service_date)}",
            f"Discharge date: {us_date(episode.discharge_date)}",
        ]
    lines += ["", "Itemized charges"]
    lines += [f"{item}: {money(amount)}" for item, amount in episode.items]
    lines += [
        f"Subtotal: {money(episode.total_cents)}",
        "Adjustments: $0.00",
        f"Total amount due: {money(episode.total_cents)}",
        "",
        "Payment is due within 30 days of the invoice date.",
        "",
        DISCLAIMER,
    ]
    inpatient = episode.discharge_date is not None
    fields = _fields(
        policy_number=episode.policy_number,
        claim_number=episode.claim_number,
        patient_name=episode.patient,
        diagnosis=diagnosis,
        treatment_cost=episode.total_cents / 100,
        hospital_name=episode.hospital["name"],
        hospital_address=episode.hospital["address"],
        provider_id=episode.physician["provider_id"],
        date_of_service=episode.service_date.isoformat(),
        date_of_admission=episode.service_date.isoformat() if inpatient else None,
        date_of_discharge=episode.discharge_date.isoformat() if inpatient else None,
    )
    printed = {
        **fields,
        "treatment_cost": money(episode.total_cents),
        "date_of_service": us_date(episode.service_date),
        "date_of_admission": us_date(episode.service_date) if inpatient else None,
        "date_of_discharge": us_date(episode.discharge_date) if inpatient else None,
    }
    return {"kind": "invoice", "document_class": "invoice", "reference": number,
            "pages": [lines], "fields": fields, "printed": printed}


def _medical_report(episode: Episode, number: str, rng: random.Random) -> dict[str, Any]:
    condition = episode.condition
    diagnosis = f"{condition.description} ({condition.code})"
    systolic, diastolic = rng.randint(108, 152), rng.randint(64, 96)
    blood_pressure = f"{systolic}/{diastolic} mmHg"
    lines = [
        *_header(episode.hospital),
        "OUTPATIENT MEDICAL REPORT",
        f"Report ID: {number}",
        "",
        f"Patient: {episode.patient}",
        f"Policy number: {episode.policy_number}",
        f"Date of service: {long_date(episode.service_date)}",
        f"Examining physician: {episode.physician['name']}",
        f"Provider ID: {episode.physician['provider_id']}",
        "",
        *wrap(f"Chief complaint: {condition.complaint}"),
        *wrap(
            f"Examination findings: blood pressure {blood_pressure}, heart rate {rng.randint(58, 96)} bpm, "
            f"temperature {rng.choice(('97.9', '98.2', '98.6', '99.1'))} F. Findings are consistent with the "
            "history described above."
        ),
        f"Diagnosis: {diagnosis}",
        *wrap(f"Plan: {condition.plan}"),
        "",
        DISCLAIMER,
    ]
    fields = _fields(
        policy_number=episode.policy_number,
        patient_name=episode.patient,
        diagnosis=diagnosis,
        hospital_name=episode.hospital["name"],
        hospital_address=episode.hospital["address"],
        provider_id=episode.physician["provider_id"],
        date_of_service=episode.service_date.isoformat(),
    )
    printed = {**fields, "date_of_service": long_date(episode.service_date)}
    return {"kind": "medical_report", "document_class": "medical_report", "reference": number,
            "pages": [lines], "fields": fields, "printed": printed, "blood_pressure": blood_pressure}


def _discharge_summary(episode: Episode, number: str, rng: random.Random) -> dict[str, Any]:
    condition = episode.condition
    diagnosis = f"{condition.description} ({condition.code})"
    stay = (episode.discharge_date - episode.service_date).days
    follow_up_days = rng.choice((7, 10, 14))
    first = [
        *_header(episode.hospital),
        "DISCHARGE SUMMARY",
        f"Summary ID: {number}",
        "",
        f"Patient: {episode.patient}",
        f"Policy number: {episode.policy_number}",
        f"Attending physician: {episode.physician['name']}",
        f"Provider ID: {episode.physician['provider_id']}",
        f"Admission date: {episode.service_date.isoformat()}",
        f"Discharge date: {episode.discharge_date.isoformat()}",
        f"Length of stay: {stay} day{'s' if stay != 1 else ''}",
        f"Principal diagnosis: {diagnosis}",
        "",
        *wrap(f"Hospital course: {condition.course}"),
        "",
        DISCLAIMER,
    ]
    second = [
        f"{episode.hospital['name']} - Discharge summary {number} - Patient: {episode.patient} (page 2)",
        "",
        f"Discharge medication: {condition.medication}.",
        *wrap(
            "Discharge instructions: rest at home, resume normal activity gradually, and return to the "
            "emergency department for fever, worsening pain or shortness of breath."
        ),
        f"Follow-up: primary care visit within {follow_up_days} days.",
        "",
        DISCLAIMER,
    ]
    fields = _fields(
        policy_number=episode.policy_number,
        patient_name=episode.patient,
        diagnosis=diagnosis,
        hospital_name=episode.hospital["name"],
        hospital_address=episode.hospital["address"],
        provider_id=episode.physician["provider_id"],
        date_of_admission=episode.service_date.isoformat(),
        date_of_discharge=episode.discharge_date.isoformat(),
    )
    medication = condition.medication.split(" ")[0]
    return {"kind": "discharge_summary", "document_class": "discharge_summary", "reference": number,
            "pages": [first, second], "fields": fields, "printed": dict(fields),
            "length_of_stay": stay, "medication": medication}


def _policy_summary(episode: Episode, rng: random.Random) -> dict[str, Any]:
    tier = rng.choice(PLAN_TIERS)
    plan = f"{episode.insurer.split()[0]} {tier}"
    start = date(2026, rng.choice((1, 1, 1, 4, 7)), 1)
    end = date(start.year + 1, start.month, 1) - timedelta(days=1)
    deductible = rng.choice((500, 1000, 1500, 2000, 2500, 3500, 5000, 6000)) * 100
    out_of_pocket = deductible * rng.choice((2, 3)) + rng.choice((0, 50000, 100000))
    lines = [
        episode.insurer,
        "Member services: (555) 0142-7700",
        "",
        "POLICY SUMMARY",
        "",
        f"Policyholder: {episode.patient}",
        f"Policy number: {episode.policy_number}",
        f"Plan: {plan}",
        f"Coverage period: {us_date(start)} to {us_date(end)}",
        "",
        "Cost sharing (in-network)",
        f"Annual deductible: {money(deductible)}",
        f"Out-of-pocket maximum: {money(out_of_pocket)}",
        f"Coinsurance after deductible: {rng.choice((10, 20, 30))}%",
        f"Primary care visit copay: {money(rng.choice((20, 25, 30, 40)) * 100)}",
        f"Specialist visit copay: {money(rng.choice((50, 60, 75)) * 100)}",
        f"Emergency room copay: {money(rng.choice((250, 350, 500)) * 100)}",
        "",
        *wrap(
            "Covered services include preventive care, hospital stays, surgery, emergency care, laboratory "
            "tests and prescription drugs, subject to the cost sharing above."
        ),
        *wrap("This summary is not a contract. The policy documents describe the full terms of coverage."),
        "",
        DISCLAIMER,
    ]
    fields = _fields(policy_number=episode.policy_number, patient_name=episode.patient)
    return {"kind": "policy_summary", "document_class": "policy_document", "reference": episode.policy_number,
            "pages": [lines], "fields": fields, "printed": dict(fields), "plan": plan,
            "deductible_cents": deductible, "out_of_pocket_cents": out_of_pocket, "coverage_end": end}


def build_documents(seed: int = SEED) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (documents, questions) for the given seed."""
    rng = random.Random(seed)
    fake = Faker("en_US")
    fake.seed_instance(seed)
    hospitals, physicians = _world(rng, fake)
    episodes = _episodes(rng, fake, hospitals, physicians)

    invoice_numbers, report_numbers = _Unique(), _Unique()
    drafts: list[tuple[Episode, dict[str, Any]]] = []
    for episode in episodes:
        drafts.append((episode, _invoice(episode, invoice_numbers.draw(lambda: f"INV-{rng.randint(1000, 9999)}"), rng)))
        if episode.discharge_date is None:
            number = report_numbers.draw(lambda: f"MR-{rng.randint(2000, 2999)}")
            drafts.append((episode, _medical_report(episode, number, rng)))
        else:
            number = report_numbers.draw(lambda: f"DS-{rng.randint(3000, 3999)}")
            drafts.append((episode, _discharge_summary(episode, number, rng)))
    for episode in rng.sample(episodes, 12):
        drafts.append((episode, _policy_summary(episode, rng)))

    rng.shuffle(drafts)  # filenames and ids carry no hint of the document type
    documents, extras = [], {}
    for position, (episode, draft) in enumerate(drafts, start=1):
        doc_id = f"doc-{position:03d}"
        pages = ["\n".join(lines) for lines in draft.pop("pages")]
        extras[doc_id] = (episode, {k: draft.pop(k) for k in list(draft) if k not in (
            "kind", "document_class", "reference", "fields", "printed")})
        documents.append({
            "id": doc_id,
            "filename": f"{doc_id}.pdf",
            **draft,
            "patient": episode.patient,
            "pages": pages,
        })
    return documents, _questions(documents, extras, rng)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------
def _question(doc: dict[str, Any], text: str, answer: Any, answer_type: str, surface: str | None,
              style: str) -> dict[str, Any]:
    return {
        "question": text,
        "answer": answer,
        "answer_type": answer_type,  # money, date, number, text or none (not answerable)
        "answer_text": surface,  # the answer as printed in the source document
        "answerable": answer is not None,
        # identifier: names a document number; descriptive: names the patient and uses the document's
        # wording; paraphrase: names the patient but avoids the document's labels
        "style": style,
        "source_document_ids": [doc["id"]],
    }


def _questions(documents: list[dict[str, Any]], extras: dict, rng: random.Random) -> list[dict[str, Any]]:
    questions = []
    unanswerable_invoices = unanswerable_summaries = paraphrased_invoices = 0
    for doc in documents:
        episode, extra = extras[doc["id"]]
        fields, printed, ref = doc["fields"], doc["printed"], doc["reference"]
        description = episode.condition.description[0].lower() + episode.condition.description[1:]
        if doc["kind"] == "invoice":
            questions += [
                _question(doc, f"What is the total amount due on invoice {ref}?", f"{fields['treatment_cost']:.2f}",
                          "money", printed["treatment_cost"], "identifier"),
                _question(doc, f"Which hospital issued invoice {ref}?", fields["hospital_name"], "text",
                          fields["hospital_name"], "identifier"),
                _question(doc, f"How much was {doc['patient']} billed in total for treatment of {description}?",
                          f"{fields['treatment_cost']:.2f}", "money", printed["treatment_cost"], "descriptive"),
            ]
            if paraphrased_invoices < 12:
                paraphrased_invoices += 1
                questions.append(_question(doc, f"What was the final bill for {doc['patient']}'s care?",
                                           f"{fields['treatment_cost']:.2f}", "money", printed["treatment_cost"],
                                           "paraphrase"))
            if unanswerable_invoices < 6:
                unanswerable_invoices += 1
                questions.append(_question(doc, f"What annual deductible is stated on invoice {ref}?",
                                           None, "none", None, "identifier"))
        elif doc["kind"] == "medical_report":
            questions += [
                _question(doc, f"Who was the examining physician in medical report {ref}?",
                          episode.physician["name"], "text", episode.physician["name"], "identifier"),
                _question(doc, f"What blood pressure was recorded for {doc['patient']} at the outpatient visit?",
                          extra["blood_pressure"], "text", extra["blood_pressure"], "descriptive"),
                _question(doc, f"What was {doc['patient']}'s BP when the doctor saw them?",
                          extra["blood_pressure"], "text", extra["blood_pressure"], "paraphrase"),
            ]
        elif doc["kind"] == "discharge_summary":
            questions += [
                _question(doc, f"On what date was the patient in discharge summary {ref} discharged?",
                          fields["date_of_discharge"], "date", printed["date_of_discharge"], "identifier"),
                _question(doc, f"How many days was {doc['patient']} hospitalized for {description}?",
                          str(extra["length_of_stay"]), "number", f"{extra['length_of_stay']} day", "descriptive"),
                _question(doc, f"Which medication was {doc['patient']} prescribed at discharge?",
                          extra["medication"], "text", extra["medication"], "descriptive"),
                _question(doc, f"For how many nights did {doc['patient']} stay?",
                          str(extra["length_of_stay"]), "number", f"{extra['length_of_stay']} day", "paraphrase"),
            ]
            if unanswerable_summaries < 6:
                unanswerable_summaries += 1
                questions.append(_question(doc, f"What total amount was billed according to discharge summary {ref}?",
                                           None, "none", None, "identifier"))
        else:
            deductible, out_of_pocket = extra["deductible_cents"], extra["out_of_pocket_cents"]
            questions += [
                _question(doc, f"What is the annual deductible for policy {ref}?", f"{deductible / 100:.2f}",
                          "money", money(deductible), "identifier"),
                _question(doc, f"What is the out-of-pocket maximum on {doc['patient']}'s health plan?",
                          f"{out_of_pocket / 100:.2f}", "money", money(out_of_pocket), "descriptive"),
                _question(doc, f"When does coverage under policy {ref} end?", extra["coverage_end"].isoformat(),
                          "date", us_date(extra["coverage_end"]), "identifier"),
                _question(doc, f"How much must {doc['patient']} pay each year before the insurer starts paying?",
                          f"{deductible / 100:.2f}", "money", money(deductible), "paraphrase"),
            ]
    rng.shuffle(questions)
    for number, question in enumerate(questions, start=1):
        question["id"] = f"q-{number:03d}"
    return [{"id": q.pop("id"), **q} for q in questions]
