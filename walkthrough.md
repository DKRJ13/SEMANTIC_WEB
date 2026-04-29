# Semantic Medical Integration Pipeline (SNOMED CT + Owlready2)

We have successfully rebuilt the semantic integration engine using industry-standard tools:
1. **SNOMED CT** as the central vocabulary.
2. **owlready2 / HermiT** as the automated Java reasoning engine.

## 1. The Architecture
We use a 3-file integration layer (Mediator-Wrapper variant):
- [ontology_A.ttl](file:///Users/daksh15/DATA_MODELLING/semantic_medical/ontology/ontology_A.ttl): Hospital A local dictionary (e.g. `ehr:DiabetesType2`).
- [ontology_B.ttl](file:///Users/daksh15/DATA_MODELLING/semantic_medical/ontology/ontology_B.ttl): Hospital B local dictionary (e.g. `clin:AdultOnsetDiabetes`).
- [snomed_core.ttl](file:///Users/daksh15/DATA_MODELLING/semantic_medical/ontology/snomed_core.ttl): A lightweight snapshot of SNOMED CT, containing canonical IDs like `sct:73211009` (Diabetes) & `sct:404684003` (Clinical finding).
- [snomed_mapping.ttl](file:///Users/daksh15/DATA_MODELLING/semantic_medical/ontology/snomed_mapping.ttl): The integration rules. It maps hospital terms to SNOMED codes and defines complex OWL logic (e.g., General Class Axioms that classify patients with interaction risks).

## 2. The Automated Reasoning Pipeline ([ingest.py](file:///Users/daksh15/DATA_MODELLING/semantic_medical/ingest.py))
No manual Python logic or SPARQL scripts are used to determine drug interactions.
1. Parses [hospital_A.xml](file:///Users/daksh15/DATA_MODELLING/semantic_medical/data/hospital_A.xml) and [hospital_B.xml](file:///Users/daksh15/DATA_MODELLING/semantic_medical/data/hospital_B.xml) into raw RDF triples (`merged_raw.owl`), aligned via `owl:sameAs`.
2. Passes `merged_raw.owl` to **Owlready2**. Owlready2 spins up the **HermiT Reasoner** (written in Java).
3. HermiT reads the pure logical definitions in [snomed_mapping.ttl](file:///Users/daksh15/DATA_MODELLING/semantic_medical/ontology/snomed_mapping.ttl) and deduces that certain patients match the intersection of "Taking Warfarin" and "Eating Grapefruit".
4. HermiT automatically asserts `rdf:type sct:BleedingRiskPatient` for those individuals and dumps the final fully-reasoned graph to `merged_reasoned.owl`.

## 3. Querying the Results ([sparql_queries.py](file:///Users/daksh15/DATA_MODELLING/semantic_medical/sparql_queries.py))
Queries are run using canonical SNOMED codes against the output of the automated reasoner.

**Example execution:**
```bash
$ python sparql_queries.py
Loading merged_reasoned.owl...

============================================================
QUERY 1: Identifying Patients with Severe Bleeding Risks
         (Automatically inferred by HermiT reasoner)
============================================================
 🚨 [ALERT] High Bleeding Risk Detected: AS_2024_001
 🚨 [ALERT] High Bleeding Risk Detected: P_101

============================================================
QUERY 2: Find all Diabetics (Cross-Hospital SNOMED Lookup)
         (sct:73211009 = Diabetes mellitus)
============================================================
  ⚕️ Patient P_101 has Diabetes.
  ⚕️ Patient P_104 has Diabetes.
  ⚕️ Patient ET_2024_003 has Diabetes.
  ⚕️ Patient AS_2024_001 has Diabetes.
```

The system is now fully automated, based strictly on OWL Logic, capable of inferring massive complex relationships across disparate data silos simultaneously.
