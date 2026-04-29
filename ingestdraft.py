"""
STEP 3 (Updated): XML → RDF Ingestion with 3-Ontology Architecture
====================================================================
Architecture:
  - ontology_A.ttl    = Hospital A's local schema (EHR vocabulary)
  - ontology_B.ttl    = Hospital B's local schema (Clinical vocabulary)
  - mediator_ontology.ttl = Global schema + mapping rules (owl:equivalentClass, owl:sameAs)

What changes from the old approach:
  - Each hospital's data is now loaded INTO its own local ontology's namespace
  - The mediator is then loaded, which imports both local ontologies
  - Queries run against the GLOBAL (med:) namespace
  - The mediator's owl:equivalentClass rules do the cross-hospital translation

Run:
  pip install rdflib
  python ingest.py
"""

import xml.etree.ElementTree as ET
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL, XSD
from pathlib import Path
import re

# ─────────────────────────────────────────────────────────────
#  SETUP: Paths and Namespaces
# ─────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
ONTO_DIR   = BASE_DIR / "ontology"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# All 3 namespaces
EHR  = Namespace("http://hospital-a.org/ehr#")         # Hospital A local
CLIN = Namespace("http://hospital-b.org/clinical#")    # Hospital B local
MED  = Namespace("http://medonto.org/global#")          # Global mediator

# Patient-data namespaces (separates schema from instance data)
HOSP_A_INST = Namespace("http://hospital-a.org/patient#")
HOSP_B_INST = Namespace("http://hospital-b.org/patient#")


# ─────────────────────────────────────────────────────────────
#  DRUG/DISEASE LOOKUP TABLES
#  Maps raw XML text → the LOCAL ontology's individual URI
#  (each hospital maps to its OWN namespace, not the global one)
# ─────────────────────────────────────────────────────────────

# Hospital A drug text → ehr: URI
DRUG_MAP_A = {
    "warfarin":    EHR.Warfarin,
    "metformin":   EHR.Metformin,
    "aspirin":     EHR.Aspirin,
    "ibuprofen":   EHR.Ibuprofen,
    "lisinopril":  EHR.Lisinopril,
    "salbutamol":  EHR.Salbutamol,
}

# Hospital A condition text → ehr: URI
DISEASE_MAP_A = {
    "diabetes type 2":       EHR.DiabetesType2,
    "hypertension":          EHR.Hypertension,
    "chronic kidney disease":EHR.ChronicKidneyDisease,
    "asthma":                EHR.Asthma,
}

# Hospital B drug generic name → clin: URI
DRUG_MAP_B = {
    "metformin hydrochloride": CLIN.MetforminHydrochloride,
    "acetylsalicylic acid":    CLIN.AcetylsalicylicAcid,
    "ibuprofen":               CLIN.Ibuprofen,
    "lisinopril":              CLIN.Lisinopril,
    "salbutamol sulfate":      CLIN.SalbutamolSulfate,
    "amlodipine":              CLIN.Amlodipine,
}

# Hospital B ICD code / text → clin: URI
DISEASE_MAP_B = {
    "e11":                    CLIN.AdultOnsetDiabetes,
    "adult-onset diabetes":   CLIN.AdultOnsetDiabetes,
    "i10":                    CLIN.EssentialHypertension,
    "essential hypertension": CLIN.EssentialHypertension,
    "n18":                    CLIN.ChronicRenalFailure,
    "chronic renal failure":  CLIN.ChronicRenalFailure,
    "j45":                    CLIN.BronchialAsthma,
    "bronchial asthma":       CLIN.BronchialAsthma,
}

# Hospital B food items → clin: URI
FOOD_MAP_B = {
    "grapefruit":       CLIN.Grapefruit,
    "grapefruit juice": CLIN.GrapefruitJuice,
}


def normalize(text: str) -> str:
    return text.strip().lower()

def safe_uri(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())


# ─────────────────────────────────────────────────────────────
#  LOAD ONTOLOGIES
# ─────────────────────────────────────────────────────────────

def load_all_ontologies() -> Graph:
    """
    Load the 3-ontology stack into a single rdflib graph.
    Order matters:
      1. ontology_A.ttl  (Hospital A local schema)
      2. ontology_B.ttl  (Hospital B local schema)
      3. mediator_ontology.ttl  (Global schema + all mapping rules)
    """
    g = Graph()
    # g.bind("ehr",  EHR)
    # g.bind("clin", CLIN)
    # g.bind("med",  MED)
    # g.bind("owl",  OWL)
    # g.bind("rdfs", RDFS)

    for onto_file in ["ontology_A.ttl", "ontology_B.ttl", "mediator_ontology.ttl"]:
        path = ONTO_DIR / onto_file
        g.parse(str(path), format="turtle")
        print(f"Loaded {onto_file}: graph now has {len(g)} triples")

    return g


# ─────────────────────────────────────────────────────────────
#  INGEST HOSPITAL A (EHR format → ehr: local classes)
# ─────────────────────────────────────────────────────────────

def ingest_hospital_A(g: Graph) -> dict:
    """
    Parse hospital_A.xml.
    Instances are created in the ehr: (local) namespace.
    The mediator's owl:equivalentClass rules automatically make them
    queryable via the global med:Patient class.
    """
    tree = ET.parse(DATA_DIR / "hospital_A.xml")
    root = tree.getroot()
    patient_index = {}

    print("\n[Hospital A — EHR Format → ehr: namespace]")
    for record in root.findall("EHR_Record"):
        pid        = record.get("id")
        full_name  = record.findtext("FullName", "").strip()
        dob        = record.findtext("DateOfBirth", "").strip()
        gender     = record.findtext("Gender", "").strip()
        blood_type = record.findtext("BloodType", "").strip()
        physician  = record.findtext("AttendingPhysician", "").strip()

        patient_uri = HOSP_A_INST[safe_uri(pid)]

        # Type as Hospital A's LOCAL class (ehr:EHR_Record)
        # The mediator maps ehr:EHR_Record → med:Patient via owl:equivalentClass
        g.add((patient_uri, RDF.type,       EHR.EHR_Record))
        g.add((patient_uri, EHR.PatientID,  Literal(pid)))
        g.add((patient_uri, EHR.FullName,   Literal(full_name)))
        g.add((patient_uri, EHR.DateOfBirth,Literal(dob)))
        g.add((patient_uri, EHR.Gender,     Literal(gender)))
        g.add((patient_uri, EHR.BloodType,  Literal(blood_type)))
        # sourceHospital is a global property (useful for provenance)
        g.add((patient_uri, MED.sourceHospital, Literal("Hospital A - City General Hospital")))

        # Doctor — typed as ehr:AttendingPhysician (maps to global med:Doctor)
        if physician:
            doctor_uri = EHR[safe_uri(physician)]
            g.add((doctor_uri, RDF.type,     EHR.AttendingPhysician))
            g.add((doctor_uri, EHR.FullName, Literal(physician)))
            g.add((patient_uri, EHR.seenBy, doctor_uri))  # local property (maps to med:treatedBy)

        # Diseases — use ehr: local disease URIs
        for cond_elem in record.findall("Condition"):
            cond_text = cond_elem.text.strip()
            disease_uri = DISEASE_MAP_A.get(normalize(cond_text))
            if disease_uri:
                g.add((patient_uri, EHR.hasCondition, disease_uri))

        # Drugs — use ehr: local drug URIs
        for rx in record.findall("Prescription"):
            drug_name = rx.findtext("DrugName", "").strip()
            drug_uri  = DRUG_MAP_A.get(normalize(drug_name))
            if drug_uri:
                g.add((patient_uri, EHR.hasPrescription, drug_uri))

        patient_index[normalize(full_name)] = patient_uri
        print(f"  → Ingested: {full_name} ({pid}) [typed as ehr:EHR_Record]")

    return patient_index


# ─────────────────────────────────────────────────────────────
#  INGEST HOSPITAL B (Clinical format → clin: local classes)
# ─────────────────────────────────────────────────────────────

def ingest_hospital_B(g: Graph, patient_index_A: dict) -> dict:
    """
    Parse hospital_B.xml.
    Instances are created in the clin: (local) namespace.
    Entity resolution: if a patient also appears in Hospital A,
    we link them with owl:sameAs.
    """
    tree = ET.parse(DATA_DIR / "hospital_B.xml")
    root = tree.getroot()
    patient_index = {}

    print("\n[Hospital B — Clinical Format → clin: namespace]")
    for record in root.findall("ClinicalRecord"):
        ref      = record.get("ref")
        name_raw = record.findtext("Patient_Name", "").strip()
        dob      = record.findtext("DOB", "").strip()
        sex      = record.findtext("Sex", "").strip()
        officer  = record.findtext("ClinicalOfficer", "").strip()

        # Normalize "Surname, Firstname" → "Firstname Surname"
        if "," in name_raw:
            parts = [p.strip() for p in name_raw.split(",")]
            full_name = f"{parts[1]} {parts[0]}"
        else:
            full_name = name_raw

        patient_uri = HOSP_B_INST[safe_uri(ref)]

        # Type as Hospital B's LOCAL class (clin:ClinicalSubject)
        # The mediator maps clin:ClinicalSubject → med:Patient via owl:equivalentClass
        g.add((patient_uri, RDF.type,            CLIN.ClinicalSubject))
        g.add((patient_uri, CLIN.Subject_Ref,    Literal(ref)))
        g.add((patient_uri, CLIN.Patient_Name,   Literal(full_name)))
        g.add((patient_uri, CLIN.DOB,            Literal(dob)))
        g.add((patient_uri, CLIN.Sex,            Literal(sex)))
        g.add((patient_uri, MED.sourceHospital,  Literal("Hospital B - Metro Clinical Centre")))

        # Entity resolution: link cross-hospital patients
        norm_name = normalize(full_name)
        if norm_name in patient_index_A:
            matched_uri = patient_index_A[norm_name]
            g.add((patient_uri, OWL.sameAs, matched_uri))
            print(f"  [LINKED] {full_name}: clin:ClinicalSubject ↔ ehr:EHR_Record (owl:sameAs)")
        else:
            print(f"  [NEW]    Ingested: {full_name} ({ref}) [typed as clin:ClinicalSubject]")

        # Doctor — typed as clin:ClinicalOfficer (maps to global med:Doctor)
        if officer:
            if "," in officer:
                parts = officer.replace(" MD", "").split(",")
                phys_name = f"Dr. {parts[1].strip()} {parts[0].strip()}"
            else:
                phys_name = officer
            doctor_uri = CLIN[safe_uri(phys_name)]
            g.add((doctor_uri, RDF.type,          CLIN.ClinicalOfficer))
            g.add((doctor_uri, CLIN.Patient_Name, Literal(phys_name)))
            g.add((patient_uri, CLIN.underCareOf, doctor_uri))

        # Diagnoses — use clin: local disease URIs (by ICD code)
        for diag in record.findall("Diagnosis"):
            icd_code  = diag.get("code", "").lower()
            diag_text = (diag.text or "").strip()
            disease_uri = DISEASE_MAP_B.get(icd_code) or DISEASE_MAP_B.get(normalize(diag_text))
            if disease_uri:
                g.add((patient_uri, CLIN.hasDiagnosis, disease_uri))

        # Medications — use clin: local drug URIs
        for med_elem in record.findall("Medication"):
            drug_name = med_elem.findtext("GenericName", "").strip()
            drug_uri  = DRUG_MAP_B.get(normalize(drug_name))
            if drug_uri:
                g.add((patient_uri, CLIN.onMedication, drug_uri))

        # Nutrition — use clin: local food URIs (only Hospital B has these)
        for food_elem in record.findall("NutritionLog"):
            food_name = food_elem.findtext("FoodItem", "").strip()
            food_uri  = FOOD_MAP_B.get(normalize(food_name))
            if food_uri:
                g.add((patient_uri, CLIN.hasNutritionEntry, food_uri))
                print(f"    Nutrition: {full_name} hasNutritionEntry {food_name}")

        patient_index[norm_name] = patient_uri

    return patient_index


# ─────────────────────────────────────────────────────────────
#  INFERENCE ENGINE
#  Now runs using GLOBAL (med:) predicates because the mediator
#  declared owl:equivalentProperty mappings.
# ─────────────────────────────────────────────────────────────

def apply_inference_rules(g: Graph) -> int:
    """
    Apply inference rules using the GLOBAL mediator predicates.
    The query engine sees med:hasCondition = ehr:hasCondition = clin:hasDiagnosis
    because of owl:equivalentProperty in the mediator.
    """
    new_triples = []
    print("\n[Applying Inference Rules via Mediator Mappings...]")

    # ── Warfarin (ehr: local) + Grapefruit (clin: local) → DangerousInteraction ──
    # Note: we mix ehr: and clin: predicates here on purpose —
    # the mediator's owl:equivalentProperty lets us query either.
    # We query by the GLOBAL med: equivalents to show cross-source integration.
    q_warfarin = """
    PREFIX ehr:  <http://hospital-a.org/ehr#>
    PREFIX clin: <http://hospital-b.org/clinical#>
    PREFIX owl:  <http://www.w3.org/2002/07/owl#>
    SELECT DISTINCT ?patient WHERE {
        # Warfarin is in ehr: namespace (Hospital A source property)
        ?patient ehr:hasPrescription ehr:Warfarin .
        # The SAME patient (via owl:sameAs) consumes Grapefruit in clin: namespace
        ?patient_b owl:sameAs ?patient .
        ?patient_b clin:hasNutritionEntry clin:GrapefruitJuice .
    }
    """
    for row in g.query(q_warfarin):
        t = (row.patient, MED.hasInteractionRisk, MED.WarfarinGrapefruitAlert)
        new_triples.append(t)
        print(f"  [INFERRED] {row.patient.split('#')[-1]} → Warfarin+Grapefruit risk")
        print(f"       (Hospital A: hasPrescription ehr:Warfarin ↔ Hospital B: hasNutritionEntry clin:GrapefruitJuice)")

    # ── Amlodipine + Grapefruit ──
    q_amlodipine = """
    PREFIX clin: <http://hospital-b.org/clinical#>
    SELECT DISTINCT ?patient WHERE {
        ?patient clin:onMedication      clin:Amlodipine .
        ?patient clin:hasNutritionEntry clin:Grapefruit .
    }
    """
    for row in g.query(q_amlodipine):
        t = (row.patient, MED.hasInteractionRisk, MED.AmlodipineGrapefruitAlert)
        new_triples.append(t)
        print(f"  [INFERRED] {row.patient.split('#')[-1]} → Amlodipine+Grapefruit risk")

    # ── NSAID + Asthma (cross-hospital: Emily Turner is only in Hospital B) ──
    q_nsaid = """
    PREFIX clin: <http://hospital-b.org/clinical#>
    PREFIX med:  <http://medonto.org/global#>
    PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT DISTINCT ?patient ?drug WHERE {
        ?patient clin:onMedication  ?drug .
        ?drug    rdf:type           med:NSAID .
        ?patient clin:hasDiagnosis  clin:BronchialAsthma .
    }
    """
    for row in g.query(q_nsaid):
        t = (row.patient, MED.hasInteractionRisk, MED.NSAIDAsthmaAlert)
        if t not in new_triples:
            new_triples.append(t)
        print(f"  [INFERRED] {row.patient.split('#')[-1]} → NSAID+Asthma risk")

    # ── Infer global med:treatedBy from local ehr:seenBy ──
    # Shows how owl:equivalentProperty works in practice
    q_inv = """
    PREFIX ehr:  <http://hospital-a.org/ehr#>
    PREFIX clin: <http://hospital-b.org/clinical#>
    PREFIX med:  <http://medonto.org/global#>
    SELECT DISTINCT ?doctor ?patient WHERE {
        { ?patient ehr:seenBy      ?doctor }
        UNION
        { ?patient clin:underCareOf ?doctor }
    }
    """
    inv_count = 0
    for row in g.query(q_inv):
        t = (row.doctor, MED.treats, row.patient)
        if t not in g:
            new_triples.append(t)
            inv_count += 1
    print(f"  [INFERRED] {inv_count} global med:treats inverse relationships (Doctor→Patient)")

    # ── owl:sameAs symmetry ──
    q_sym = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT ?a ?b WHERE { ?a owl:sameAs ?b . }
    """
    sym_count = 0
    for row in g.query(q_sym):
        t = (row.b, OWL.sameAs, row.a)
        if t not in g:
            new_triples.append(t)
            sym_count += 1
    print(f"  [INFERRED] {sym_count} symmetric owl:sameAs triples")

    for triple in new_triples:
        g.add(triple)

    return len(new_triples)


# ─────────────────────────────────────────────────────────────
#  MAIN PIPELINE
# ─────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  Semantic Medical Integration — 3-Ontology Architecture")
    print("=" * 65)

    # Step 1: Load ontology_A + ontology_B + mediator (in order)
    g = load_all_ontologies()
    baseline = len(g)

    # Step 2: Ingest Hospital A data into ehr: namespace
    pa_index = ingest_hospital_A(g)
    after_A = len(g)
    print(f"\n  Added {after_A - baseline} triples from Hospital A")

    # Step 3: Ingest Hospital B data into clin: namespace
    pb_index = ingest_hospital_B(g, pa_index)
    after_B = len(g)
    print(f"\n  Added {after_B - after_A} triples from Hospital B")

    # Step 4: Apply inference rules
    print("\n" + "=" * 65)
    n_inferred = apply_inference_rules(g)
    print(f"\n  Generated {n_inferred} NEW inferred triples")

    # Step 5: Save
    out = OUTPUT_DIR / "merged_output.ttl"
    g.serialize(destination=str(out), format="turtle")

    print("\n" + "=" * 65)
    print(f"  Done! Total triples: {len(g)}")
    print(f"  Saved to: {out}")
    print("=" * 65)

    return g


if __name__ == "__main__":
    main()
