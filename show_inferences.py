"""
INFERENCE VISUALIZER
====================
This script compares the Raw XML graph with the Fully Reasoned graph
and explicitly prints out ONLY the facts that the AI (HermiT) generated
on its own. This is perfect for demonstrating the power of the reasoner to your professor.
"""

from rdflib import Graph, BNode
from pathlib import Path

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"

def show_inferences():
    print("Loading graphs... (This takes a few seconds)")
    g_raw = Graph().parse(str(OUTPUT_DIR / "merged_raw.owl"), format="xml")
    g_reasoned = Graph().parse(str(OUTPUT_DIR / "merged_reasoned.owl"), format="xml")
    
    print(f"Raw graph: {len(g_raw)} triples")
    print(f"Reasoned graph: {len(g_reasoned)} triples")
    
    # To do true set subtraction, we must filter out volatile Blank Nodes.
    # Owlready2 rewrites BNode IDs (e.g. _:N1 to _:N2) when saving the reasoned file.
    # If we don't filter them, naive subtraction thinks the original facts are "new".
    def remove_bnodes(g):
        clean_g = Graph()
        for s, p, o in g:
            if not isinstance(s, BNode) and not isinstance(o, BNode):
                clean_g.add((s, p, o))
        return clean_g

    raw_clean = remove_bnodes(g_raw)
    reasoned_clean = remove_bnodes(g_reasoned)
    
    # Mathematical subtraction of strictly identifiable graphs
    inferred_graph = reasoned_clean - raw_clean
    print(f"Total AI Inferences (excluding BNode shifts): {len(inferred_graph)}\n")
    
    print("=" * 70)
    print(" 🚨 HIGHLIGHTS OF DEDUCED KNOWLEDGE (Filtered for clarity) 🚨")
    print("=" * 70)
    
    # We only print the interesting ones (skipping internal OWL class typings)
    for s, p, o in inferred_graph:
        subject = str(s).split('/')[-1].split('#')[-1]
        predicate = str(p).split('/')[-1].split('#')[-1]
        obj = str(o).split('/')[-1].split('#')[-1]
        
        # Highlight our risk intersections
        if "RiskPatient" in obj:
            print(f" [CLINICAL DIAGNOSIS] {subject} was classified as -> {obj}")
            print(f"    (Reason: Met the exact intersection rules for {obj})\n")
        
        # Highlight the new Second Opinion feature
        elif "eligibleForSecondOpinionFrom" in predicate:
            print(f" [NEW PATHWAY DETECTED] {subject} is eligible for a second opinion from -> {obj}")
            print(f"    (Reason: The reasoner followed the 'Friends/Colleagues' property chain!)\n")

if __name__ == "__main__":
    show_inferences()
