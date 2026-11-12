
from pathlib import Path
import json
from datetime import datetime
from sqlalchemy import inspect
from config.db_config import engine

DOCS = Path("docs")
DOCS.mkdir(exist_ok=True)

# 1. README
readme = """# Loyalty Points Management System

## 1. Project Overview

The Loyalty Points Management System manages customer loyalty points
through earning, returns, redemption, and expiry.

It maintains transaction history, point lots, allocations, account
balances, and reconciliation checks.

## 2. Main Features

- Synthetic customer and order data generation.
- Loyalty account and tier management.
- Points accrual from eligible orders.
- Return-based points reversal.
- Points lot tracking and allocation.
- FIFO-based points redemption.
- Points expiry processing.
- Immutable points transaction ledger.
- Account-to-ledger reconciliation.
- Controlled anomaly injection and detection.
- CSV, JSON, and SQL exports.

## 3. Technology Stack

- Python
- MySQL 8
- SQLAlchemy
- Pandas
- NumPy
- Faker
- Streamlit
- Plotly
- Scikit-learn
- Git

## 4. Dataset

Synthetic dataset configuration:

| Entity | Records |
|---|---:|
| Customers | 20,000 |
| Loyalty accounts | 20,000 |
| Orders | 100,000 |
| Order lines | 300,000 |
| Return headers | 12,119 |
| Return lines | 24,172 |
| Points transactions | 143,718 |
| Points lots | 86,870 |
| Points allocations | 57,088 |
| Redemptions | 68 |
| Expiry batches | 1 |

Random seed: `20261022`

These are synthetic records and business assumptions, not real customer
or official YottaFlex data.

## 5. Points Processing

The system supports:

1. Points accrual from eligible orders.
2. Points reversal for completed returns.
3. Points redemption against active rewards.
4. Expiry of eligible points lots.
5. Transaction-level allocation tracking.
6. Account balance reconciliation against the ledger.

## 6. Anomaly Scenarios

Five controlled anomaly scenarios are included:

1. Account balance differs from ledger balance.
2. Redemption exceeds available points.
3. Returned order retains earned points.
4. Points lot is expired twice.
5. Tier is calculated using gross spend instead of qualifying spend.

The anomaly input and ground-truth labels are stored separately.

**Important limitation:** The current anomaly detector is a preliminary
rule-based demonstration using scenario descriptions in the test input.
Its evaluation contains five injected positive cases and no normal
control records. The reported 100% metrics therefore do not establish
real-world detection performance.

## 7. Project Structure

- `config/` - configuration and database settings
- `database/` - database schema and migrations
- `src/generator/` - synthetic data generation
- `src/business_logic/` - accrual, returns, redemption, and expiry
- `src/ledger/` - ledger processing
- `src/anomalies/` - anomaly injection, detection, and evaluation
- `src/validation/` - validation, exports, and documentation
- `data/` - generated and processed data
- `exports/` - CSV, JSON, and SQL exports
- `dashboard/` - dashboard application
- `tests/` - automated tests
- `docs/` - project documentation

## 8. Environment Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Configure the MySQL database connection using the environment variables
expected by `config/db_config.py`.

Create the database using the SQL schema in `database/`.

## 9. Main Execution Commands

Run the commands from the project root with the virtual environment active.

```powershell
python -m src.business_logic.ledger_processor
python -m src.business_logic.redemption_expiry_processor
python -m src.anomalies.anomaly_injector
python -m src.anomalies.anomaly_detector
python -m src.anomalies.evaluate_detection
python -m src.validation.final_validation
python -m src.validation.export_project
```

**Warning:** The ledger and redemption/expiry processors have already
been executed for this generated database. Do not rerun them against
the same populated database.

## 10. Exports

- `exports/csv/` - table exports in CSV format
- `exports/json/` - table exports in JSON format
- `exports/sql/` - MySQL database dump

## 11. Validation

The latest final validation report recorded 11 passed checks and
0 failed checks.

See `data/processed/final_validation_report.json`.

## 12. Limitations

- Data is synthetic.
- Points debt tables currently contain no records.
- The anomaly detector requires independent business-rule checks and
  normal control records before its metrics can be treated as
  representative performance.
- The dashboard and remaining features should be checked before release.

## 13. Reproducibility

The synthetic data uses seed `20261022`.
"""

(DOCS / "README.md").write_text(readme, encoding="utf-8")

# 2. Data dictionary from the live database
inspector = inspect(engine)
dictionary_lines = [
    "# Data Dictionary",
    "",
    "Generated from the current MySQL database schema.",
    ""
]

table_names = inspector.get_table_names()

for table in sorted(table_names):
    dictionary_lines.extend([f"## {table}", ""])
    dictionary_lines.append("| Column | Database type | Nullable | Key |")
    dictionary_lines.append("|---|---|---|---|")

    primary_keys = set(
        inspector.get_pk_constraint(table).get("constrained_columns") or []
    )

    foreign_keys = set()
    for fk in inspector.get_foreign_keys(table):
        foreign_keys.update(fk.get("constrained_columns") or [])

    for column in inspector.get_columns(table):
        name = column["name"]
        key = "PK" if name in primary_keys else (
            "FK" if name in foreign_keys else ""
        )
        nullable = "Yes" if column.get("nullable") else "No"
        dictionary_lines.append(
            f"| {name} | {column['type']} | {nullable} | {key} |"
        )

    dictionary_lines.append("")

(DOCS / "data_dictionary.md").write_text(
    "\n".join(dictionary_lines), encoding="utf-8"
)

# 3. Validation summary
validation_path = Path("data/processed/final_validation_report.json")

if validation_path.exists():
    report = json.loads(validation_path.read_text(encoding="utf-8"))

    validation_md = [
        "# Final Validation Summary",
        "",
        f"Validation date: {report.get('validation_date', 'Not recorded')}",
        "",
        f"Overall status: **{report.get('overall_status')}**",
        "",
        f"- Checks passed: {report.get('checks_passed')}",
        f"- Checks failed: {report.get('checks_failed')}",
        "",
        "## Individual checks",
        "",
        "| Check | Status | Actual | Expected |",
        "|---|---|---:|---:|"
    ]

    for check in report.get("checks", []):
        validation_md.append(
            f"| {check['check']} | {check['status']} | "
            f"{check['actual']} | {check['expected']} |"
        )

    (DOCS / "validation_summary.md").write_text(
        "\n".join(validation_md), encoding="utf-8"
    )

    (DOCS / "validation_report.json").write_text(
        json.dumps(report, indent=4), encoding="utf-8"
    )

# 4. Source manifest
manifest = {
    "project": "Loyalty Points Management System",
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "random_seed": 20261022,
    "database_tables": sorted(table_names),
    "source_files": []
}

for folder in ["config", "database", "src", "dashboard", "tests"]:
    root = Path(folder)
    if root.exists():
        for path in sorted(root.rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and ".pyc" not in path.suffix
            ):
                manifest["source_files"].append(str(path))

(DOCS / "source_manifest.json").write_text(
    json.dumps(manifest, indent=4), encoding="utf-8"
)

print("=" * 50)
print("DOCUMENTATION GENERATED")
print("=" * 50)

for name in [
    "README.md",
    "data_dictionary.md",
    "validation_summary.md",
    "validation_report.json",
    "source_manifest.json"
]:
    path = DOCS / name
    if path.exists():
        print(f"CREATED: {path}")

print(f"\nDatabase tables documented: {len(table_names)}")
print(f"Source files listed: {len(manifest['source_files'])}")
