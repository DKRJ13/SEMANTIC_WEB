"""
Config-Driven CSV -> RDF Ingestion Engine (URI Unification)
============================================================
Auto-discovers *_config.json files in /data, reads the mapping rules,
ingests all associated CSVs into RDF with shared canonical URIs for
patients and doctors. No owl:sameAs needed - fully plug-and-play.
"""

import csv, re, os, json
from pathlib import Path
from rdflib import Graph, Namespace, Literal, URIRef, RDF, RDFS, OWL, XSD
from owlready2 import get_ontology, sync_reasoner

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
ONTO_DIR   = BASE_DIR / "ontology"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Unified namespaces for cross-hospital entity resolution
PATIENT_NS = Namespace("http://unified.org/patient#")
DOCTOR_NS  = Namespace("http://unified.org/doctor#")


def normalize(text): return text.strip().lower()
def safe_uri(name):  return re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())

def read_csv(filepath):
    rows = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: v.strip() if v else "" for k, v in row.items()})
    return rows

def multi(val):
    return [v.strip() for v in val.split("|") if v.strip()] if val else []

def transform_name(raw, fmt):
    """Convert 'Last, First' to 'First Last' if format is last_first."""
    if fmt == "last_first" and "," in raw:
        parts = [p.strip() for p in raw.split(",")]
        return f"{parts[1]} {parts[0]}" if len(parts) == 2 else raw
    return raw


def get_unified_uri(name_raw, name_fmt, mpi, unified_ns):
    """Return a canonical URI for this person, creating one if first encounter."""
    full_name = transform_name(name_raw, name_fmt)
    key = normalize(full_name)
    if key not in mpi:
        mpi[key] = unified_ns[safe_uri(full_name)]
    return mpi[key], full_name


def ingest_hospital(g, config, data_dir, provenance, patient_mpi, doctor_mpi):
    """
    Generic ingestion engine with URI unification.
    Patients and doctors get a single canonical URI shared across hospitals.
    No owl:sameAs is produced.
    """
    ns   = Namespace(config["namespace"])
    inst = Namespace(config["instance_namespace"])
    term = config.get("terminology", {})
    hospital_id = config["hospital_id"]

    def resolve_ref(val):
        if val in term:
            return ns[term[val]]
        return ns[safe_uri(val)]

    def tag(uri, source_file):
        fname = os.path.basename(source_file)
        provenance.setdefault(str(uri), set()).add(fname)

    for entity_name, schema in config["csv_files"].items():
        csv_filename = f"{hospital_id}_{entity_name}.csv"
        csv_path = data_dir / csv_filename
        if not csv_path.exists():
            continue

        entity_type = schema["entity_type"]
        id_col      = schema["id_column"]
        columns     = schema["columns"]
        use_ns_id   = schema.get("use_namespace_for_id", False)
        name_col    = schema.get("name_column", None)
        name_fmt    = schema.get("name_format", None)
        is_person   = schema.get("is_person", entity_name in ("patients", "doctors"))

        for row in read_csv(csv_path):
            entity_id = row.get(id_col, "")
            if not entity_id:
                continue

            # ── URI Unification ──
            # Patients and doctors share a single canonical URI across hospitals.
            # Non-person entities (diseases, drugs) keep their hospital-specific URIs.
            if is_person and name_col:
                raw_name = row.get(name_col, "").strip()
                if raw_name and entity_name in ("patients", "subjects"):
                    entity_uri, _ = get_unified_uri(raw_name, name_fmt, patient_mpi, PATIENT_NS)
                elif raw_name and entity_name in ("doctors", "officers", "staff"):
                    entity_uri, _ = get_unified_uri(raw_name, name_fmt, doctor_mpi, DOCTOR_NS)
                else:
                    entity_uri = ns[entity_id] if use_ns_id else inst[safe_uri(entity_id)]
            else:
                entity_uri = ns[entity_id] if use_ns_id else inst[safe_uri(entity_id)]

            # Assign RDF type (accumulates: EHR_Record + ClinicalSubject on same node)
            g.add((entity_uri, RDF.type, ns[entity_type]))
            tag(entity_uri, csv_path)

            # Process each mapped column
            for col_name, rule in columns.items():
                raw_val = row.get(col_name, "").strip()
                if not raw_val:
                    continue

                prop_name = rule["property"]
                val_type  = rule["type"]
                is_multi  = rule.get("multi", False)
                col_transform = rule.get("transform", None)

                if prop_name.startswith("rdfs:"):
                    prop_uri = RDFS[prop_name.split(":")[1]]
                else:
                    prop_uri = ns[prop_name]

                values = multi(raw_val) if is_multi else [raw_val]

                for val in values:
                    val = val.strip()
                    if not val:
                        continue

                    if val_type == "literal":
                        display_val = transform_name(val, col_transform) if col_transform else val
                        g.add((entity_uri, prop_uri, Literal(display_val)))
                    elif val_type == "float":
                        try:
                            g.add((entity_uri, prop_uri, Literal(float(val), datatype=XSD.float)))
                        except ValueError:
                            pass
                    elif val_type == "ref":
                        g.add((entity_uri, prop_uri, resolve_ref(val)))
                    elif val_type == "uri":
                        uri_ns = rule.get("uri_namespace", "self")
                        if uri_ns == "self":
                            g.add((entity_uri, prop_uri, ns[val]))
                        else:
                            g.add((entity_uri, prop_uri, Namespace(uri_ns)[val]))
                    elif val_type == "instance_ref":
                        # Instance refs for patients should also go through MPI
                        ref_name_raw = None
                        # Look up the referenced entity's name from the same CSV
                        # For now, use the hospital-local URI as fallback
                        g.add((entity_uri, prop_uri, inst[safe_uri(val)]))


def build_raw_graph(data_dir=None, onto_dir=None):
    """Build raw RDF graph from all configs using URI unification."""
    if data_dir is None: data_dir = DATA_DIR
    if onto_dir is None: onto_dir = ONTO_DIR
    data_dir = Path(data_dir)
    onto_dir = Path(onto_dir)

    g = Graph()
    provenance = {}

    # Auto-discover and load ALL .ttl ontology files
    for ttl_file in sorted(onto_dir.glob("*.ttl")):
        g.parse(str(ttl_file), format="turtle")

    # Master Patient/Doctor Indexes: normalized name -> single canonical URI
    patient_mpi = {}
    doctor_mpi  = {}

    # Auto-discover and process ALL *_config.json files
    config_files = sorted(data_dir.glob("*_config.json"))
    for config_path in config_files:
        with open(config_path, "r") as f:
            config = json.load(f)
        ingest_hospital(g, config, data_dir, provenance, patient_mpi, doctor_mpi)

    # No owl:sameAs needed — URI unification means all hospitals
    # already attached their triples to the same canonical node.

    # Prevent external network downloads
    g.remove((None, OWL.imports, None))

    raw_path = OUTPUT_DIR / "merged_raw.owl"
    g.serialize(destination=str(raw_path), format="xml")

    # Save provenance map
    prov_path = OUTPUT_DIR / "provenance.json"
    serializable = {k: list(v) for k, v in provenance.items()}
    with open(prov_path, "w") as f:
        json.dump(serializable, f, indent=2)

    return g, raw_path, provenance


def run_reasoner(raw_path):
    onto = get_ontology(f"file://{raw_path}").load()
    with onto:
        sync_reasoner(infer_property_values=True)
    reasoned_path = OUTPUT_DIR / "merged_reasoned.owl"
    onto.save(file=str(reasoned_path), format="rdfxml")
    return reasoned_path


def run_pipeline(data_dir=None, onto_dir=None):
    g, raw_path, provenance = build_raw_graph(data_dir, onto_dir)
    reasoned_path = run_reasoner(raw_path)
    return reasoned_path, provenance


if __name__ == "__main__":
    print("Running config-driven CSV ingestion pipeline (URI unification)...")
    reasoned_path, prov = run_pipeline()
    print(f"Done. Reasoned graph saved to: {reasoned_path}")
    print(f"Total provenance entries: {len(prov)}")
