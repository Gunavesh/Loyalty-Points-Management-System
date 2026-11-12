# Data Dictionary

Generated from the current MySQL database schema.

## auditevent

| Column | Database type | Nullable | Key |
|---|---|---|---|
| audit_event_id | BIGINT | No | PK |
| entity_type | VARCHAR(60) | No |  |
| entity_id | VARCHAR(60) | No |  |
| event_type | VARCHAR(100) | No |  |
| event_timestamp | DATETIME | No |  |
| actor_type | ENUM | No |  |
| actor_id | VARCHAR(60) | Yes |  |
| event_details | JSON | Yes |  |
| created_at | TIMESTAMP | No |  |

## customer

| Column | Database type | Nullable | Key |
|---|---|---|---|
| customer_id | BIGINT | No | PK |
| customer_name | VARCHAR(150) | No |  |
| email | VARCHAR(255) | No |  |
| phone | VARCHAR(20) | Yes |  |
| registration_date | DATETIME | No |  |
| customer_status | ENUM | No |  |
| created_at | TIMESTAMP | No |  |

## customertierhistory

| Column | Database type | Nullable | Key |
|---|---|---|---|
| tier_history_id | BIGINT | No | PK |
| account_id | VARCHAR(40) | No | FK |
| previous_tier_id | INTEGER | Yes | FK |
| new_tier_id | INTEGER | No | FK |
| qualifying_spend_at_change | DECIMAL(14, 2) | No |  |
| changed_at | DATETIME | No |  |
| reason | VARCHAR(255) | Yes |  |

## expirybatch

| Column | Database type | Nullable | Key |
|---|---|---|---|
| expiry_batch_id | VARCHAR(30) | No | PK |
| batch_started_at | DATETIME | No |  |
| batch_completed_at | DATETIME | Yes |  |
| batch_status | ENUM | No |  |
| points_expired | BIGINT | No |  |
| records_processed | INTEGER | No |  |

## loyaltyaccount

| Column | Database type | Nullable | Key |
|---|---|---|---|
| account_id | VARCHAR(40) | No | PK |
| customer_id | BIGINT | No | FK |
| tier_id | INTEGER | No | FK |
| current_balance | BIGINT | No |  |
| qualifying_spend | DECIMAL(14, 2) | No |  |
| account_status | ENUM | No |  |
| opened_at | DATETIME | No |  |
| updated_at | TIMESTAMP | No |  |

## orderline

| Column | Database type | Nullable | Key |
|---|---|---|---|
| order_line_id | BIGINT | No | PK |
| order_id | VARCHAR(30) | No | FK |
| product_code | VARCHAR(50) | No |  |
| product_name | VARCHAR(150) | No |  |
| quantity | INTEGER | No |  |
| unit_price | DECIMAL(14, 2) | No |  |
| discount_amount | DECIMAL(14, 2) | No |  |
| line_net_amount | DECIMAL(14, 2) | No |  |

## orders

| Column | Database type | Nullable | Key |
|---|---|---|---|
| order_id | VARCHAR(30) | No | PK |
| customer_id | BIGINT | No | FK |
| order_date | DATETIME | No |  |
| order_status | ENUM | No |  |
| gross_amount | DECIMAL(14, 2) | No |  |
| discount_amount | DECIMAL(14, 2) | No |  |
| net_amount | DECIMAL(14, 2) | No |  |
| currency | CHAR(3) | No |  |
| created_at | TIMESTAMP | No |  |

## pointsallocation

| Column | Database type | Nullable | Key |
|---|---|---|---|
| allocation_id | BIGINT | No | PK |
| lot_id | BIGINT | No | FK |
| transaction_id | VARCHAR(30) | No | FK |
| allocation_type | ENUM | No |  |
| points_allocated | BIGINT | No |  |
| created_at | TIMESTAMP | No |  |

## pointsdebt

| Column | Database type | Nullable | Key |
|---|---|---|---|
| debt_id | BIGINT | No | PK |
| account_id | VARCHAR(40) | No | FK |
| source_return_line_id | BIGINT | No | FK |
| original_accrual_transaction_id | VARCHAR(30) | No | FK |
| points_owed | BIGINT | No |  |
| points_remaining | BIGINT | No |  |
| debt_status | ENUM | No |  |
| created_at | DATETIME | No |  |

## pointsdebtsettlement

| Column | Database type | Nullable | Key |
|---|---|---|---|
| settlement_id | BIGINT | No | PK |
| debt_id | BIGINT | No | FK |
| accrual_transaction_id | VARCHAR(30) | No | FK |
| points_settled | BIGINT | No |  |
| settled_at | DATETIME | No |  |

## pointslot

| Column | Database type | Nullable | Key |
|---|---|---|---|
| lot_id | BIGINT | No | PK |
| account_id | VARCHAR(40) | No | FK |
| accrual_transaction_id | VARCHAR(30) | No | FK |
| original_points | BIGINT | No |  |
| remaining_points | BIGINT | No |  |
| earned_at | DATETIME | No |  |
| expiry_date | DATETIME | No |  |
| lot_status | ENUM | No |  |

## pointstransaction

| Column | Database type | Nullable | Key |
|---|---|---|---|
| transaction_id | VARCHAR(30) | No | PK |
| account_id | VARCHAR(40) | No | FK |
| transaction_type | ENUM | No |  |
| points_change | BIGINT | No |  |
| transaction_date | DATETIME | No |  |
| order_id | VARCHAR(30) | Yes | FK |
| redemption_id | VARCHAR(30) | Yes | FK |
| expiry_batch_id | VARCHAR(30) | Yes | FK |
| reference_transaction_id | VARCHAR(30) | Yes | FK |
| description | VARCHAR(500) | Yes |  |
| idempotency_key | VARCHAR(150) | No |  |
| created_at | TIMESTAMP | No |  |
| return_line_id | BIGINT | Yes | FK |

## processedrequest

| Column | Database type | Nullable | Key |
|---|---|---|---|
| request_id | BIGINT | No | PK |
| idempotency_key | VARCHAR(150) | No |  |
| operation_type | VARCHAR(60) | No |  |
| account_id | VARCHAR(40) | Yes | FK |
| request_status | ENUM | No |  |
| response_details | JSON | Yes |  |
| created_at | TIMESTAMP | No |  |
| completed_at | DATETIME | Yes |  |

## redemption

| Column | Database type | Nullable | Key |
|---|---|---|---|
| redemption_id | VARCHAR(30) | No | PK |
| account_id | VARCHAR(40) | No | FK |
| reward_id | INTEGER | No | FK |
| points_redeemed | BIGINT | No |  |
| redemption_status | ENUM | No |  |
| redemption_date | DATETIME | No |  |
| idempotency_key | VARCHAR(150) | No |  |

## returnline

| Column | Database type | Nullable | Key |
|---|---|---|---|
| return_line_id | BIGINT | No | PK |
| return_id | VARCHAR(30) | No | FK |
| order_line_id | BIGINT | No | FK |
| returned_quantity | INTEGER | No |  |
| refund_amount | DECIMAL(14, 2) | No |  |

## returns

| Column | Database type | Nullable | Key |
|---|---|---|---|
| return_id | VARCHAR(30) | No | PK |
| order_id | VARCHAR(30) | No | FK |
| customer_id | BIGINT | No | FK |
| return_date | DATETIME | No |  |
| return_status | ENUM | No |  |
| reason | VARCHAR(255) | Yes |  |

## reward

| Column | Database type | Nullable | Key |
|---|---|---|---|
| reward_id | INTEGER | No | PK |
| reward_name | VARCHAR(150) | No |  |
| reward_description | TEXT | Yes |  |
| points_cost | BIGINT | No |  |
| reward_status | ENUM | No |  |
| stock_quantity | INTEGER | Yes |  |
| effective_from | DATETIME | No |  |
| effective_to | DATETIME | Yes |  |

## rule

| Column | Database type | Nullable | Key |
|---|---|---|---|
| rule_id | INTEGER | No | PK |
| rule_name | VARCHAR(100) | No |  |
| rule_type | ENUM | No |  |
| rule_description | TEXT | Yes |  |
| rule_value | DECIMAL(14, 4) | No |  |
| effective_from | DATETIME | No |  |
| effective_to | DATETIME | Yes |  |
| rule_status | ENUM | No |  |
| created_at | TIMESTAMP | No |  |

## ruleapplication

| Column | Database type | Nullable | Key |
|---|---|---|---|
| rule_application_id | BIGINT | No | PK |
| rule_id | INTEGER | No | FK |
| transaction_id | VARCHAR(30) | Yes | FK |
| order_id | VARCHAR(30) | Yes | FK |
| applied_at | DATETIME | No |  |
| applied_value | DECIMAL(14, 4) | No |  |
| calculation_details | JSON | Yes |  |

## tier

| Column | Database type | Nullable | Key |
|---|---|---|---|
| tier_id | INTEGER | No | PK |
| tier_name | VARCHAR(50) | No |  |
| minimum_qualifying_spend | DECIMAL(14, 2) | No |  |
| earning_rate | DECIMAL(8, 4) | No |  |
| effective_from | DATE | No |  |
| effective_to | DATE | Yes |  |
| tier_status | ENUM | No |  |
