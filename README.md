# Semantic Medical Data Integration

This project provides a semantic pipeline for unifying clinical data across multiple hospital systems. By integrating isolated datasets into a shared knowledge graph, the system enables a more comprehensive view of patient health records and automates the detection of clinical risks.

## Project Overview

Clinical data is frequently siloed, with different institutions using unique naming conventions and storage formats. This fragmentation makes it difficult to reconcile patient records or identify potential medical conflicts when a patient receives care from multiple providers.

This system addresses these challenges by:
1.  **Unifying Data Sources**: Consolidating varied CSV datasets into a single RDF knowledge graph.
2.  **Standardizing Vocabularies**: Aligning local hospital terms with the global SNOMED CT standard.
3.  **Automated Clinical Reasoning**: Using logical inference to identify high-risk scenarios, such as dangerous drug-drug interactions, that may be missed in isolated systems.

## Core Components

### 1. Data Ingestion (csv_ingest.py)
The ingestion engine uses a configuration-driven approach to map hospital-specific CSV files into a unified RDF format. It employs a URI unification strategy to ensure that patients and clinicians are recognized consistently across different datasets without requiring complex manual mapping.

### 2. Semantic Reasoning
The system integrates the HermiT reasoner via Owlready2. Rather than relying on simple database queries, the system uses formal OWL logic to:
*   Identify patients with specific clinical risk profiles.
*   Infer relationships between symptoms, diagnoses, and treatments across disparate silos.
*   Maintain data provenance to track the origin of every clinical assertion.

### 3. Flask Interface (app.py)
A lightweight web interface is provided to query the reasoned knowledge graph and visualize clinical insights.

## Getting Started

### Prerequisites
The system requires Python 3 and the following dependencies:
```bash
pip install flask rdflib owlready2
```

### Installation and Execution
1.  **Prepare Data**: Ensure hospital CSV files and their corresponding JSON configuration files are located in the `data/` directory.
2.  **Generate Knowledge Graph**:
    ```bash
    python csv_ingest.py
    ```
3.  **Start the Web Interface**:
    ```bash
    python app.py
    ```
4.  **Access Results**: Navigate to `http://localhost:5000` in your web browser.

## Design Philosophy
The architecture is designed to be modular and scalable. Supporting a new hospital only requires adding a JSON configuration file that defines how local headers map to canonical medical concepts. This ensures the system remains flexible as the network of integrated clinical providers grows.
