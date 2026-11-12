# Loyalty Points Management System

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
.\.venv\Scripts\Activate.ps1
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
