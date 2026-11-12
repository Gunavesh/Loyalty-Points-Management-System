
from pathlib import Path
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)

BASE = Path("data/anomalies")

results = pd.read_csv(BASE / "anomaly_detection_results.csv")
truth = pd.read_csv(BASE / "ground_truth.csv")

evaluation = results.merge(
    truth[["anomaly_id", "is_anomaly"]],
    on="anomaly_id",
    suffixes=("_predicted", "_actual"),
    validate="one_to_one"
)

y_true = evaluation["is_anomaly_actual"].astype(int)
y_pred = evaluation["is_anomaly_predicted"].astype(int)

metrics = {
    "records_evaluated": len(evaluation),
    "accuracy": accuracy_score(y_true, y_pred),
    "precision": precision_score(y_true, y_pred, zero_division=0),
    "recall": recall_score(y_true, y_pred, zero_division=0),
    "f1_score": f1_score(y_true, y_pred, zero_division=0),
}

tn, fp, fn, tp = confusion_matrix(
    y_true, y_pred, labels=[0, 1]
).ravel()

metrics.update({
    "true_positives": int(tp),
    "true_negatives": int(tn),
    "false_positives": int(fp),
    "false_negatives": int(fn),
    "evaluation_limitation": (
        "Only injected positive cases are currently available. "
        "Normal control records are needed to measure specificity "
        "and false-positive performance."
    )
})

pd.DataFrame([metrics]).to_csv(
    BASE / "evaluation_metrics.csv", index=False
)

evaluation.to_csv(
    BASE / "evaluation_details.csv", index=False
)

print("=" * 50)
print("DETECTION EVALUATION")
print("=" * 50)

for name, value in metrics.items():
    print(f"{name}: {value}")

print("\nEvaluation files saved in data/anomalies/")
