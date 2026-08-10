"""
Batch-scores every workflow JSON in samples/corpus/ using the same rubric
the FastAPI /score endpoint uses, and writes governance_report.csv.

This is run standalone here to validate the rubric across a real, diverse
corpus before wiring the n8n orchestration pipeline on top of the same
scoring logic (via the API).
"""
import json
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from api.rubric import score_workflow

CORPUS_DIR = "samples/corpus"
OUTPUT_CSV = "output/governance_report.csv"

rows = []
errors = []

for fname in sorted(os.listdir(CORPUS_DIR)):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(CORPUS_DIR, fname)
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            wf = json.load(f)
        result = score_workflow(wf, filename=fname)
        rows.append({
            "filename": result["filename"],
            "workflow_name": result["workflow_name"],
            "category": fname.split("__")[0],
            "node_count": result["node_count"],
            "composite_risk_score": result["composite_risk_score"],
            "credential_score": result["dimensions"]["credential_exposure"]["score"],
            "hardcoded_secrets_found": len(result["dimensions"]["credential_exposure"]["hardcoded_secret_findings"]),
            "error_handling_score": result["dimensions"]["error_handling"]["score"],
            "has_error_handling": result["dimensions"]["error_handling"]["has_error_handling"],
            "autonomy_score": result["dimensions"]["autonomy_tier"]["score"],
            "autonomy_tier": result["dimensions"]["autonomy_tier"]["tier"],
            "audit_score": result["dimensions"]["audit_trail"]["score"],
            "has_logging_node": result["dimensions"]["audit_trail"]["has_logging_node"],
        })
    except Exception as e:
        errors.append({"filename": fname, "error": str(e)})

df = pd.DataFrame(rows)
os.makedirs("output", exist_ok=True)
df.to_csv(OUTPUT_CSV, index=False)

print(f"Scored {len(df)} workflows successfully. {len(errors)} errors.")
if errors:
    print("Errors:", errors[:5])

print("\n--- Composite score distribution ---")
print(df["composite_risk_score"].describe())

print("\n--- Autonomy tier distribution ---")
print(df["autonomy_tier"].value_counts())

print("\n--- Riskiest 5 workflows ---")
print(df.nsmallest(5, "composite_risk_score")[["filename", "composite_risk_score", "autonomy_tier", "hardcoded_secrets_found"]].to_string(index=False))

print("\n--- Safest 5 workflows ---")
print(df.nlargest(5, "composite_risk_score")[["filename", "composite_risk_score", "autonomy_tier"]].to_string(index=False))

print(f"\nWritten to {OUTPUT_CSV}")
