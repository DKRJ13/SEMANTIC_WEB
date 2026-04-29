"""
Flask Web Frontend for Semantic Medical Reasoner
=================================================
Upload CSVs + TTL ontologies, run the HermiT reasoner,
and query the graph with SPARQL — with source provenance.
"""

import os, json
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from rdflib import Graph, Namespace
from csv_ingest import run_pipeline, OUTPUT_DIR, DATA_DIR, ONTO_DIR

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

EHR  = Namespace("http://hospital-a.org/ehr#")
CLIN = Namespace("http://hospital-b.org/clinical#")
SCT  = Namespace("http://snomed.info/id/")

# Pre-built queries for the UI
PRESET_QUERIES = {
    "bleeding_risk": {
        "title": "Bleeding Risk (Warfarin + Grapefruit)",
        "sparql": """
PREFIX sct: <http://snomed.info/id/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ehr: <http://hospital-a.org/ehr#>
PREFIX clin: <http://hospital-b.org/clinical#>

SELECT DISTINCT ?patient ?name WHERE {
    ?patient rdf:type sct:BleedingRiskPatient .
    { ?patient ehr:FullName ?name } UNION { ?patient clin:Patient_Name ?name }
}"""
    },
    "diabetics": {
        "title": "All Diabetics (Cross-Hospital)",
        "sparql": """
PREFIX sct: <http://snomed.info/id/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ehr: <http://hospital-a.org/ehr#>
PREFIX clin: <http://hospital-b.org/clinical#>

SELECT DISTINCT ?patient ?name WHERE {
    { ?patient ehr:hasCondition ?d } UNION { ?patient clin:hasDiagnosis ?d }
    ?d rdf:type sct:73211009 .
    { ?patient ehr:FullName ?name } UNION { ?patient clin:Patient_Name ?name }
}"""
    },
    "second_opinion": {
        "title": "Second Opinion Eligibility",
        "sparql": """
PREFIX clin: <http://hospital-b.org/clinical#>
PREFIX ehr: <http://hospital-a.org/ehr#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?patientName ?doctorName ?specialty WHERE {
    ?patient a ehr:EHR_Record .
    ?patient clin:eligibleForSecondOpinionFrom ?doctor .
    ?patient ehr:FullName ?patientName .
    ?doctor rdfs:label ?doctorName .
    { ?doctor ehr:hasSpecialty ?specialty } UNION { ?doctor clin:hasSpecialty ?specialty }
}"""
    },
    "genetic_risk": {
        "title": "Genetic Ancestry Risk (Huntington's)",
        "sparql": """
PREFIX sct: <http://snomed.info/id/>
PREFIX ehr: <http://hospital-a.org/ehr#>
PREFIX clin: <http://hospital-b.org/clinical#>

SELECT DISTINCT ?patient ?patientName WHERE {
    ?patient sct:hasRiskOfGeneticDisease ?diseaseInstance .
    ?diseaseInstance a sct:58756001 .
    { ?patient ehr:FullName ?patientName } UNION { ?patient clin:Patient_Name ?patientName }
}"""
    },
    "bronchospasm_risk": {
        "title": "Bronchospasm Risk (NSAID + Asthma) [Cross-Hospital C]",
        "sparql": """
PREFIX sct: <http://snomed.info/id/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX ehr: <http://hospital-a.org/ehr#>
PREFIX clin: <http://hospital-b.org/clinical#>
PREFIX medc: <http://hospital-c.org/med#>

SELECT DISTINCT ?patient ?patientName WHERE {
    ?patient rdf:type sct:BronchospasmRiskPatient .
    { ?patient ehr:FullName ?patientName } 
    UNION { ?patient clin:Patient_Name ?patientName }
    UNION { ?patient medc:Name ?patientName }
}"""
    }
}

# Global state
current_provenance = {}
reasoned_graph = None


@app.route("/")
def index():
    csv_files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".csv")])
    json_files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".json") and f != "provenance.json"])
    ttl_files = sorted([f for f in os.listdir(ONTO_DIR) if f.endswith(".ttl")])
    return render_template("index.html",
                           csv_files=csv_files,
                           json_files=json_files,
                           ttl_files=ttl_files,
                           presets=PRESET_QUERIES)


@app.route("/upload", methods=["POST"])
def upload():
    uploaded = []
    for f in request.files.getlist("files"):
        fname = f.filename
        if fname.endswith(".csv") or fname.endswith(".json"):
            dest = DATA_DIR / fname
        elif fname.endswith(".ttl"):
            dest = ONTO_DIR / fname
        else:
            continue
        f.save(str(dest))
        uploaded.append(fname)
    return jsonify({"status": "ok", "uploaded": uploaded})


@app.route("/run", methods=["POST"])
def run():
    global current_provenance, reasoned_graph
    try:
        reasoned_path, prov = run_pipeline()
        current_provenance = prov

        # Load the reasoned graph for querying
        reasoned_graph = Graph()
        reasoned_graph.parse(str(reasoned_path), format="xml")

        return jsonify({
            "status": "ok",
            "message": f"Pipeline complete. Graph has {len(reasoned_graph)} triples.",
            "provenance_count": len(prov)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/query", methods=["POST"])
def query():
    global reasoned_graph, current_provenance
    if reasoned_graph is None:
        return jsonify({"status": "error", "message": "Run the pipeline first."}), 400

    sparql = request.json.get("sparql", "")
    if not sparql.strip():
        return jsonify({"status": "error", "message": "Empty query."}), 400

    try:
        results = []
        for row in reasoned_graph.query(sparql):
            row_dict = {}
            sources = set()
            for var in row.labels:
                val = str(row[var])
                row_dict[str(var)] = val
                # Look up provenance for any URI values
                if val in current_provenance:
                    sources.update(current_provenance[val])
            row_dict["_source"] = ", ".join(sorted(sources)) if sources else "ontology / inferred"
            results.append(row_dict)

        # Get column names from first result
        columns = list(results[0].keys()) if results else []

        return jsonify({
            "status": "ok",
            "columns": columns,
            "results": results,
            "count": len(results)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001)
