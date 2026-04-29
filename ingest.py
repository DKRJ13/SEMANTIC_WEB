"""
Normalized Database XML → RDF Ingestion
=======================================
Now supporting standalone 4-Root Entities: Diseases, Drugs, Doctors, Patients.
"""

import xml.etree.ElementTree as ET
from rdflib import Graph, Namespace, Literal, RDF, RDFS, OWL, XSD, BNode
from pathlib import Path
import re
from owlready2 import get_ontology, sync_reasoner

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
ONTO_DIR   = BASE_DIR / "ontology"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

EHR  = Namespace("http://hospital-a.org/ehr#")
CLIN = Namespace("http://hospital-b.org/clinical#")
HOSP_A_INST = Namespace("http://hospital-a.org/patient#")
HOSP_B_INST = Namespace("http://hospital-b.org/patient#")

# Map Normalized XML IDs to the pre-existing Semantic Ontology Graph URIs
A_DICT = {
    "D-01": EHR.DiabetesType2, "D-02": EHR.Hypertension, 
    "D-03": EHR.ChronicKidneyDisease, "D-04": EHR.Asthma, "D-05": EHR.Huntingtons,
    "RX-01": EHR.Metformin, "RX-02": EHR.Warfarin, "RX-03": EHR.Ibuprofen, 
    "RX-04": EHR.Lisinopril, "RX-05": EHR.Amlodipine
}

B_DICT = {
    "G10": CLIN.HuntingtonsDisease, "E11": CLIN.AdultOnsetDiabetes, 
    "I10": CLIN.EssentialHypertension, "N18": CLIN.ChronicRenalFailure, "J45": CLIN.BronchialAsthma,
    "MED-01": CLIN.MetforminHydrochloride, "MED-02": CLIN.AcetylsalicylicAcid, 
    "MED-03": CLIN.Ibuprofen, "MED-04": CLIN.Lisinopril, "MED-05": CLIN.Amlodipine,
    "F-01": CLIN.Grapefruit, "F-02": CLIN.GrapefruitJuice
}

def normalize(text: str) -> str: return text.strip().lower()
def safe_uri(name: str) -> str: return re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())

def build_raw_graph():
    g = Graph()

    files = ["ontology_A.ttl", "ontology_B.ttl", "snomed_core.ttl", "snomed_mapping.ttl"]
    for f in files:
        g.parse(str(ONTO_DIR / f), format="turtle")

    patient_index_A = {}
    doctor_index_A = {}

    treeA = ET.parse(DATA_DIR / "hospital_A.xml")
    rootA = treeA.getroot()

    # Parse Dictionaries (Diseases & Drugs)
    for obj in rootA.find("Diseases").findall("Disease"):
        obj_id = obj.get("id")
        name = obj.findtext("Name", "").strip()
        if obj_id in A_DICT:
            g.add((A_DICT[obj_id], RDFS.label, Literal(name)))

    for obj in rootA.find("Drugs").findall("Drug"):
        obj_id = obj.get("id")
        name = obj.findtext("Name", "").strip()
        if obj_id in A_DICT:
            g.add((A_DICT[obj_id], RDFS.label, Literal(name)))

    # Parse Doctors
    for doc in rootA.find("Doctors").findall("Doctor"):
        doc_uri = EHR[doc.get("id")]
        g.add((doc_uri, RDF.type, EHR.MedicalPersonnel))
        name = doc.findtext("Name", "").strip()
        g.add((doc_uri, RDFS.label, Literal(name)))
        spec = doc.findtext("Specialty", "").strip()
        if spec: g.add((doc_uri, EHR.hasSpecialty, Literal(spec)))
        
        doctor_index_A[normalize(name)] = doc_uri
        
        for rel in doc.findall("ReliesOnRef"):
            g.add((doc_uri, EHR.reliesOnColleague, EHR[rel.text.strip()]))

    # Parse Patients
    for record in rootA.find("Patients").findall("Patient"):
        patient_uri = HOSP_A_INST[safe_uri(record.get("id"))]
        full_name = record.findtext("FullName", "").strip()
        patient_index_A[normalize(full_name)] = patient_uri
        
        g.add((patient_uri, RDF.type, EHR.EHR_Record))
        g.add((patient_uri, EHR.FullName, Literal(full_name)))

        dob = record.findtext("DateOfBirth", "").strip()
        if dob: g.add((patient_uri, EHR.DateOfBirth, Literal(dob)))

        for cond in record.findall("ConditionRef"):
            g.add((patient_uri, EHR.hasCondition, A_DICT[cond.text.strip()]))
        for gcond in record.findall("GeneticConditionRef"):
            g.add((patient_uri, EHR.hasGeneticCondition, A_DICT[gcond.text.strip()]))
        for rx in record.findall("PrescriptionRef"):
            g.add((patient_uri, EHR.hasPrescription, A_DICT[rx.text.strip()]))
        for parent in record.findall("ParentRef"):
            g.add((patient_uri, EHR.hasParent, HOSP_A_INST[safe_uri(parent.text.strip())]))
        for phys in record.findall("AttendingPhysicianRef"):
            g.add((patient_uri, EHR.seenBy, EHR[phys.text.strip()]))

    treeB = ET.parse(DATA_DIR / "hospital_B.xml")
    rootB = treeB.getroot()

    # Parse Dictionaries (Diseases, Drugs, Foods)
    for obj in rootB.find("Diseases").findall("Disease"):
        obj_id = obj.get("code")
        name = obj.findtext("Name", "").strip()
        if obj_id in B_DICT:
            g.add((B_DICT[obj_id], RDFS.label, Literal(name)))

    for obj in rootB.find("Drugs").findall("Drug"):
        obj_id = obj.get("code")
        name = obj.findtext("Name", "").strip()
        if obj_id in B_DICT:
            g.add((B_DICT[obj_id], RDFS.label, Literal(name)))
            
    for obj in rootB.find("Foods").findall("Food"):
        obj_id = obj.get("item")
        name = obj.findtext("Name", "").strip()
        if obj_id in B_DICT:
            g.add((B_DICT[obj_id], RDFS.label, Literal(name)))

    # Parse Doctors
    for doc in rootB.find("ClinicalOfficers").findall("Officer"):
        doc_uri = CLIN[doc.get("id")]
        g.add((doc_uri, RDF.type, CLIN.ClinicalOfficer))
        name = doc.findtext("Name", "").strip()
        g.add((doc_uri, RDFS.label, Literal(name)))
        spec = doc.findtext("Specialty", "").strip()
        if spec: g.add((doc_uri, CLIN.hasSpecialty, Literal(spec)))
        
        # Bridge Cross-Hospital Doctors!
        if normalize(name) in doctor_index_A:
            g.add((doc_uri, OWL.sameAs, doctor_index_A[normalize(name)]))
            
        for peer in doc.findall("ConsultsWithRef"):
            g.add((doc_uri, CLIN.consultsWith, CLIN[peer.text.strip()]))

    # Parse Patients
    for record in rootB.find("ClinicalSubjects").findall("Subject"):
        patient_uri = HOSP_B_INST[safe_uri(record.get("ref"))]
        name_raw = record.findtext("Name", "").strip()
        bmi = record.findtext("BMI", "").strip()
        dob = record.findtext("DOB", "").strip()
        sex = record.findtext("Sex", "").strip()
        
        parts = [p.strip() for p in name_raw.split(",")]
        full_name = f"{parts[1]} {parts[0]}" if "," in name_raw else name_raw
        
        g.add((patient_uri, RDF.type, CLIN.ClinicalSubject))
        g.add((patient_uri, CLIN.Patient_Name, Literal(full_name)))
        if bmi: g.add((patient_uri, CLIN.BMI, Literal(float(bmi), datatype=XSD.float)))
        if dob: g.add((patient_uri, CLIN.DOB, Literal(dob)))
        if sex: g.add((patient_uri, CLIN.Sex, Literal(sex)))

        # Bridge Cross-Hospital Patients
        if normalize(full_name) in patient_index_A:
            g.add((patient_uri, OWL.sameAs, patient_index_A[normalize(full_name)]))

        for diag in record.findall("DiagnosisRef"):
            g.add((patient_uri, CLIN.hasDiagnosis, B_DICT[diag.text.strip()]))
        for gdiag in record.findall("GeneticDiagnosisRef"):
            g.add((patient_uri, CLIN.hasGeneticDiagnosis, B_DICT[gdiag.text.strip()]))
        for med in record.findall("MedicationRef"):
            g.add((patient_uri, CLIN.onMedication, B_DICT[med.text.strip()]))
        for food in record.findall("NutritionRef"):
            g.add((patient_uri, CLIN.hasNutritionEntry, B_DICT[food.text.strip()]))
        for parent in record.findall("BiologicalParentRef"):
            g.add((patient_uri, CLIN.hasBiologicalParent, HOSP_B_INST[safe_uri(parent.text.strip())]))
        for phys in record.findall("UnderCareOfRef"):
            g.add((patient_uri, CLIN.underCareOf, CLIN[phys.text.strip()]))
        for friend in record.findall("FriendRef"):
            g.add((patient_uri, CLIN.knowsPatient, HOSP_B_INST[safe_uri(friend.text.strip())]))

    # Prevent external network downloads
    g.remove((None, OWL.imports, None))

    raw_path = OUTPUT_DIR / "merged_raw.owl"
    g.serialize(destination=str(raw_path), format="xml")
    return raw_path


def run_reasoner(raw_path: Path):
    onto = get_ontology(f"file://{raw_path}").load()
    with onto:
        print(1)
        # reasoning engiune
        sync_reasoner(infer_property_values=True)
        print(2)

    reasoned_path = OUTPUT_DIR / "merged_reasoned.owl"
    onto.save(file=str(reasoned_path), format="rdfxml")
    return reasoned_path


def main():
    raw_path = build_raw_graph()
    reasoned_path = run_reasoner(raw_path)
    

if __name__ == "__main__":
    main()
