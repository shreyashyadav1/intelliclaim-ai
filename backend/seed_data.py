"""
IntelliClaim AI - Demo Data Seeder

Replaces every claim and document in the configured database (MONGODB_URI /
MONGODB_DB_NAME, from the environment or backend/.env) with 50 demo claims.
The random generator is seeded, so each run produces the same claims; dates
are relative to the day the script runs.

Run:  python seed_data.py         (local databases)
      python seed_data.py --yes   (required for any other host, e.g. Atlas)
"""

import argparse
import asyncio
import random
import re
import sys
from datetime import UTC, datetime, timedelta

from config import settings
from db.connection import close_db, connect_db, get_database, ping_database, redact_mongo_uri

SEED = 42
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "mongodb"}  # "mongodb" is the docker compose service

# Realistic demo data
PATIENTS = [
    {"name": "Sarah Johnson", "policy": "POL-2026-50001"},
    {"name": "Michael Chen", "policy": "POL-2026-50002"},
    {"name": "Emily Rodriguez", "policy": "POL-2026-50003"},
    {"name": "James Williams", "policy": "POL-2026-50004"},
    {"name": "Amanda Thompson", "policy": "POL-2026-50005"},
    {"name": "Robert Davis", "policy": "POL-2026-50006"},
    {"name": "Lisa Garcia", "policy": "POL-2026-50007"},
    {"name": "David Brown", "policy": "POL-2026-50008"},
    {"name": "Jennifer Martinez", "policy": "POL-2026-50009"},
    {"name": "Christopher Lee", "policy": "POL-2026-50010"},
    {"name": "Maria Hernandez", "policy": "POL-2026-50011"},
    {"name": "Kevin O'Brien", "policy": "POL-2026-50012"},
    {"name": "Stephanie Kim", "policy": "POL-2026-50013"},
    {"name": "Andrew Patel", "policy": "POL-2026-50014"},
    {"name": "Rachel Nguyen", "policy": "POL-2026-50015"},
]

DIAGNOSES = [
    ("ACL Tear (S83.5)", 28000, 42000),
    ("Type 2 Diabetes (E11.9)", 8000, 18000),
    ("Acute Appendicitis (K35.80)", 22000, 35000),
    ("Lumbar Disc Herniation (M51.16)", 45000, 78000),
    ("Knee Replacement (Z96.651)", 65000, 110000),
    ("Coronary Artery Disease (I25.10)", 80000, 180000),
    ("Cholecystitis (K81.0)", 14000, 25000),
    ("Rotator Cuff Tear (M75.10)", 20000, 40000),
    ("Breast Cancer Stage II (C50.9)", 90000, 150000),
    ("Pneumonia (J18.9)", 5000, 15000),
    ("Hip Fracture (S72.0)", 35000, 60000),
    ("Chronic Kidney Disease (N18.3)", 12000, 30000),
    ("Atrial Fibrillation (I48.91)", 15000, 45000),
    ("Cervical Spondylosis (M47.812)", 10000, 28000),
    ("Gallstone Pancreatitis (K85.1)", 18000, 38000),
]

HOSPITALS = [
    ("Metro General Hospital", "500 Medical Pkwy, New York, NY 10001", "NPI-1234567890"),
    ("City Medical Center", "1200 Health Ave, Chicago, IL 60601", "NPI-2345678901"),
    ("St. Mary's Hospital", "800 Care Blvd, Los Angeles, CA 90001", "NPI-3456789012"),
    ("Spine Care Institute", "1250 Medical Dr, Houston, TX 77001", "NPI-4567890123"),
    ("Orthopedic Surgical Center", "300 Bone Way, Phoenix, AZ 85001", "NPI-5678901234"),
    ("Heart & Vascular Center", "450 Cardiac Ln, Philadelphia, PA 19101", "NPI-6789012345"),
    ("Regional Medical Center", "700 Health St, San Antonio, TX 78201", "NPI-7890123456"),
    ("Sports Medicine Clinic", "900 Athletic Dr, San Diego, CA 92101", "NPI-8901234567"),
    ("Cancer Treatment Center", "150 Oncology Rd, Dallas, TX 75201", "NPI-9012345678"),
    ("Community Hospital", "250 Main St, San Jose, CA 95101", "NPI-0123456789"),
]

STATUSES = ["pending", "approved", "rejected", "flagged"]
STATUS_WEIGHTS = [0.15, 0.55, 0.15, 0.15]

DOC_CLASSES = ["medical_report", "invoice", "claim_form", "discharge_summary"]


def is_local_database(uri: str) -> bool:
    """True when every host in a mongodb:// URI is local (SRV URIs never are)."""
    match = re.match(r"^mongodb://(?:[^@/]*@)?([^/?]+)", uri or "")
    if match is None:
        return False
    hosts = []
    for entry in match.group(1).split(","):
        entry = entry.strip().lower()
        hosts.append(entry[1 : entry.index("]")] if entry.startswith("[") else entry.split(":")[0])
    return all(host in LOCAL_HOSTS for host in hosts)


def _random_date(rng: random.Random, now: datetime, days_back: int = 90) -> datetime:
    return now - timedelta(
        days=rng.randint(0, days_back),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
    )


def build_demo_data(rng: random.Random, now: datetime) -> tuple[list[dict], list[dict]]:
    """Generate the demo claims and their documents."""
    claims = []
    documents = []

    for i in range(50):
        patient = rng.choice(PATIENTS)
        diagnosis, cost_min, cost_max = rng.choice(DIAGNOSES)
        hospital_name, hospital_addr, provider_id = rng.choice(HOSPITALS)
        status = rng.choices(STATUSES, STATUS_WEIGHTS)[0]
        cost = round(rng.uniform(cost_min, cost_max), 2)

        created = _random_date(rng, now)
        admission = created - timedelta(days=rng.randint(1, 5))
        discharge = admission + timedelta(days=rng.randint(1, 14))

        risk_score = 0.0
        risk_flags = []
        if cost > 100000:
            risk_score += 30
            risk_flags.append(f"Very high treatment cost (${cost:,.2f})")
        elif cost > 50000:
            risk_score += 15
            risk_flags.append(f"High treatment cost (${cost:,.2f})")
        if status == "flagged":
            risk_score += 25
            risk_flags.append("Manually flagged for review")
        risk_score += rng.uniform(0, 15)
        risk_score = min(round(risk_score, 1), 100)

        claim_id = f"clm-{10001 + i}"
        claim_number = f"CLM-2026-{10001 + i}"

        # Create 1-3 documents per claim
        doc_ids = []
        for j in range(rng.randint(1, 3)):
            doc_class = rng.choice(DOC_CLASSES)
            doc_id = f"doc-{i * 3 + j + 1}"
            doc_ids.append(doc_id)
            condition = diagnosis.split("(")[0].strip().lower()
            documents.append({
                "_id": doc_id,
                "filename": f"{doc_class}_{patient['name'].lower().replace(' ', '_')}_{i}.pdf",
                "file_type": "pdf",
                "file_size": rng.randint(50000, 500000),
                "page_count": 1,
                "storage_path": f"./uploads/documents/{doc_id}.pdf",
                "document_class": doc_class,
                "extracted_text": (
                    f"Patient: {patient['name']}\nPolicy: {patient['policy']}\nDiagnosis: {diagnosis}\n"
                    f"Hospital: {hospital_name}\nTreatment Cost: ${cost:,.2f}\n"
                    f"Date of Service: {created.strftime('%Y-%m-%d')}\n\n"
                    f"Clinical Notes: Patient presented with {condition}. Treatment was administered at "
                    f"{hospital_name}. Total charges amount to ${cost:,.2f}."
                ),
                "claim_id": claim_id,
                "processing_status": "processed",
                "error_message": None,
                "created_at": created,
                "updated_at": created,
            })

        claims.append({
            "_id": claim_id,
            "claim_number": claim_number,
            "claim_number_is_placeholder": False,
            "policy_number": patient["policy"],
            "patient_name": patient["name"],
            "diagnosis": diagnosis,
            "treatment_cost": cost,
            "hospital_name": hospital_name,
            "hospital_address": hospital_addr,
            "provider_id": provider_id,
            "date_of_service": created.strftime("%Y-%m-%d"),
            "date_of_admission": admission.strftime("%Y-%m-%d"),
            "date_of_discharge": discharge.strftime("%Y-%m-%d"),
            "status": status,
            "risk_score": risk_score,
            "risk_flags": risk_flags,
            "document_ids": doc_ids,
            "extraction_confidence": round(rng.uniform(0.78, 0.99), 2),
            "created_at": created,
            "updated_at": created,
        })

    return claims, documents


async def seed() -> None:
    await connect_db()  # also creates the indexes
    try:
        if not await ping_database(timeout=5):
            sys.exit(f"MongoDB at {redact_mongo_uri(settings.MONGODB_URI)} is not reachable.")

        db = get_database()
        claims, documents = build_demo_data(random.Random(SEED), datetime.now(UTC))

        await db.claims.delete_many({})
        await db.documents.delete_many({})
        await db.claims.insert_many(claims)
        await db.documents.insert_many(documents)
    finally:
        await close_db()

    print(f"Seeded {len(claims)} claims and {len(documents)} documents into {settings.MONGODB_DB_NAME}")
    for status in STATUSES:
        print(f"  {status}: {sum(1 for c in claims if c['status'] == status)}")
    avg_cost = sum(c["treatment_cost"] for c in claims) / len(claims)
    print(f"  average cost: ${avg_cost:,.2f}")
    print(f"  high risk (>= 60): {sum(1 for c in claims if c['risk_score'] >= 60)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="allow wiping a database that is not on this machine")
    args = parser.parse_args()

    target = redact_mongo_uri(settings.MONGODB_URI)
    if not is_local_database(settings.MONGODB_URI) and not args.yes:
        sys.exit(
            f"Refusing to replace all data in {target} ({settings.MONGODB_DB_NAME}) because it is not a local "
            "database. Re-run with --yes if that is intended."
        )
    print(f"Seeding {target} ({settings.MONGODB_DB_NAME})...")
    asyncio.run(seed())


if __name__ == "__main__":
    main()
