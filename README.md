# Loyalty Points Management System

## 1. Project Overview

The Loyalty Points Management System manages customer loyalty points through earning, returns, redemption, and expiry.

It maintains transaction history, point lots, allocations, account balances, and reconciliation checks.

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
- Database-driven anomaly detection and validation.

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

These are synthetic records and business assumptions, not real customer or official YottaFlex data.

## 5. Points Processing

The system supports:

1. Points accrual from eligible orders.
2. Points reversal for completed returns.
3. Points redemption against active rewards.
4. Expiry of eligible points lots.
5. Transaction-level allocation tracking.
6. Account balance reconciliation against the ledger.

## 6. Anomaly Scenarios and Detection

Five controlled anomaly scenarios are included:

1. **Account balance mismatch:** Account balance differs from ledger balance.
2. **Excess redemption:** Redemption exceeds available points.
3. **Missing return reversal:** Returned order retains earned points without the expected reversal.
4. **Duplicate expiry:** Points lot is expired more than once.
5. **Incorrect tier calculation:** Tier is calculated using gross spend instead of qualifying spend.

The anomaly input and ground-truth labels are stored separately.

### V1 and V2 Detection

The original V1 detector uses scenario evidence descriptions from the anomaly input.

An improved V2 detector performs database-driven checks against business rules rather than relying only on scenario descriptions.

V2 currently evaluates all five scenarios:

| Scenario | Detection check |
|---|---|
| ANOM-001 | Compares observed account balance with the actual transaction ledger balance. |
| ANOM-002 | Compares redemption points with the account's current balance. |
| ANOM-003 | Checks completed returns and compares observed reversal points with actual database reversal transactions. |
| ANOM-004 | Compares observed expiry allocation with the recorded expiry allocation. |
| ANOM-005 | Compares observed tier with the expected tier calculated from qualifying spend. |

**Latest V2 results:**

- Total anomaly records: 5
- Evaluated scenarios: 5
- Detected anomalies: 5
- Not evaluated: 0

The V2 output is saved to `data/anomalies/anomaly_detection_results_v2.csv`.

**Important limitations:**

- ANOM-002 uses current account balance as a proxy; it does not reconstruct historical available points at the exact redemption time.
- The current evaluation contains five injected positive anomaly cases and no normal control records.
- These results demonstrate detection of the five implemented scenarios, not general real-world detection accuracy.
- The V2 checks are based on the implemented business rules and available database evidence.

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

Configure the MySQL database connection using the environment variables expected by `config/db_config.py`.

Create the database using the SQL schema in `database/`.

## 9. Main Execution Commands

Run commands from the project root with the virtual environment active.

```powershell
python -m src.anomalies.anomaly_detector
python -m src.anomalies.anomaly_detector_v2
python -m src.anomalies.evaluate_detection
python -m src.validation.final_validation
python -m src.validation.export_project
```

**Warning:** The ledger and redemption/expiry processors have already been executed for this generated database. Do not rerun them against the same populated database.

The original anomaly injector can overwrite anomaly input and ground-truth files. Do not rerun it unless you intentionally want to regenerate those files.

## 10. Exports

- `exports/csv/` - table exports in CSV format
- `exports/json/` - table exports in JSON format
- `exports/sql/` - MySQL database dump

## 11. Validation and Testing

Latest validation results:

- Final validation checks passed: 11
- Final validation checks failed: 0
- Automated tests passed: 6

The final validation report is saved at `data/processed/final_validation_report.json`.

## 12. Limitations

- Data is synthetic and does not represent real customer records.
- Points debt tables currently contain no records.
- ANOM-002 uses current account balance rather than historical available balance.
- Normal control records are needed for a more complete anomaly detection evaluation.
- The dashboard and remaining features should be checked before release.

## 13. Reproducibility

The synthetic data uses random seed `20261022`.