
-- ============================================================
-- LOYALTY POINTS MANAGEMENT SYSTEM
-- MySQL 8.0+
-- Database: loyalty_points_db
-- ============================================================

USE loyalty_points_db;

SET NAMES utf8mb4;

-- 1. CUSTOMER
CREATE TABLE IF NOT EXISTS Customer (
    customer_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20),
    registration_date DATETIME NOT NULL,
    customer_status ENUM('ACTIVE', 'INACTIVE', 'SUSPENDED') NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. TIER
CREATE TABLE IF NOT EXISTS Tier (
    tier_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tier_name VARCHAR(50) NOT NULL UNIQUE,
    minimum_qualifying_spend DECIMAL(14,2) NOT NULL,
    earning_rate DECIMAL(8,4) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    tier_status ENUM('ACTIVE', 'INACTIVE') NOT NULL DEFAULT 'ACTIVE',
    CHECK (minimum_qualifying_spend >= 0),
    CHECK (earning_rate >= 0),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
) ENGINE=InnoDB;

-- 3. LOYALTY ACCOUNT
CREATE TABLE IF NOT EXISTS LoyaltyAccount (
    account_id VARCHAR(40) PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL UNIQUE,
    tier_id INT UNSIGNED NOT NULL,
    current_balance BIGINT NOT NULL DEFAULT 0,
    qualifying_spend DECIMAL(14,2) NOT NULL DEFAULT 0,
    account_status ENUM('ACTIVE', 'FROZEN', 'CLOSED') NOT NULL DEFAULT 'ACTIVE',
    opened_at DATETIME NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_account_customer
        FOREIGN KEY (customer_id) REFERENCES Customer(customer_id),
    CONSTRAINT fk_account_tier
        FOREIGN KEY (tier_id) REFERENCES Tier(tier_id),
    CHECK (current_balance >= 0),
    CHECK (qualifying_spend >= 0)
) ENGINE=InnoDB;

-- 4. RULE
CREATE TABLE IF NOT EXISTS Rule (
    rule_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rule_name VARCHAR(100) NOT NULL,
    rule_type ENUM('EARNING', 'REDEMPTION', 'EXPIRY', 'TIER') NOT NULL,
    rule_description TEXT,
    rule_value DECIMAL(14,4) NOT NULL,
    effective_from DATETIME NOT NULL,
    effective_to DATETIME,
    rule_status ENUM('ACTIVE', 'INACTIVE') NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
) ENGINE=InnoDB;

-- 5. ORDERS
CREATE TABLE IF NOT EXISTS Orders (
    order_id VARCHAR(30) PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_date DATETIME NOT NULL,
    order_status ENUM(
        'PLACED', 'PAID', 'PARTIALLY_RETURNED', 'RETURNED', 'CANCELLED'
    ) NOT NULL,
    gross_amount DECIMAL(14,2) NOT NULL,
    discount_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
    net_amount DECIMAL(14,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'INR',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES Customer(customer_id),
    CHECK (gross_amount >= 0),
    CHECK (discount_amount >= 0),
    CHECK (net_amount >= 0),
    CHECK (gross_amount >= discount_amount)
) ENGINE=InnoDB;

CREATE INDEX idx_orders_customer_date
    ON Orders(customer_id, order_date);

-- 6. ORDER LINE
CREATE TABLE IF NOT EXISTS OrderLine (
    order_line_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    product_code VARCHAR(50) NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(14,2) NOT NULL,
    discount_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
    line_net_amount DECIMAL(14,2) NOT NULL,
    CONSTRAINT fk_orderline_order
        FOREIGN KEY (order_id) REFERENCES Orders(order_id),
    CHECK (quantity > 0),
    CHECK (unit_price >= 0),
    CHECK (discount_amount >= 0),
    CHECK (line_net_amount >= 0)
) ENGINE=InnoDB;

CREATE INDEX idx_orderline_order ON OrderLine(order_id);

-- 7. REWARD
CREATE TABLE IF NOT EXISTS Reward (
    reward_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    reward_name VARCHAR(150) NOT NULL,
    reward_description TEXT,
    points_cost BIGINT UNSIGNED NOT NULL,
    reward_status ENUM('ACTIVE', 'INACTIVE', 'OUT_OF_STOCK')
        NOT NULL DEFAULT 'ACTIVE',
    stock_quantity INT UNSIGNED,
    effective_from DATETIME NOT NULL,
    effective_to DATETIME,
    CHECK (points_cost > 0),
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
) ENGINE=InnoDB;

-- 8. EXPIRY BATCH
CREATE TABLE IF NOT EXISTS ExpiryBatch (
    expiry_batch_id VARCHAR(30) PRIMARY KEY,
    batch_started_at DATETIME NOT NULL,
    batch_completed_at DATETIME,
    batch_status ENUM('STARTED', 'COMPLETED', 'FAILED')
        NOT NULL DEFAULT 'STARTED',
    points_expired BIGINT UNSIGNED NOT NULL DEFAULT 0,
    records_processed INT UNSIGNED NOT NULL DEFAULT 0,
    CHECK (batch_completed_at IS NULL OR
           batch_completed_at >= batch_started_at)
) ENGINE=InnoDB;

-- 9. POINTS TRANSACTION: IMMUTABLE LEDGER
CREATE TABLE IF NOT EXISTS PointsTransaction (
    transaction_id VARCHAR(30) PRIMARY KEY,
    account_id VARCHAR(40) NOT NULL,
    transaction_type ENUM(
        'ACCRUAL', 'REDEMPTION', 'RETURN_REVERSAL',
        'EXPIRY', 'ADJUSTMENT'
    ) NOT NULL,
    points_change BIGINT NOT NULL,
    transaction_date DATETIME NOT NULL,
    order_id VARCHAR(30),
    redemption_id VARCHAR(30),
    expiry_batch_id VARCHAR(30),
    reference_transaction_id VARCHAR(30),
    description VARCHAR(500),
    idempotency_key VARCHAR(150) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_transaction_account
        FOREIGN KEY (account_id) REFERENCES LoyaltyAccount(account_id),
    CONSTRAINT fk_transaction_order
        FOREIGN KEY (order_id) REFERENCES Orders(order_id),
    CONSTRAINT fk_transaction_expiry
        FOREIGN KEY (expiry_batch_id)
        REFERENCES ExpiryBatch(expiry_batch_id),
    CONSTRAINT fk_transaction_reference
        FOREIGN KEY (reference_transaction_id)
        REFERENCES PointsTransaction(transaction_id),
    CHECK (points_change <> 0)
) ENGINE=InnoDB;

CREATE INDEX idx_transaction_account_date
    ON PointsTransaction(account_id, transaction_date);

CREATE INDEX idx_transaction_order
    ON PointsTransaction(order_id);

-- 10. POINTS LOT: TRACKS INDIVIDUAL EARNED POINTS
CREATE TABLE IF NOT EXISTS PointsLot (
    lot_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    account_id VARCHAR(40) NOT NULL,
    accrual_transaction_id VARCHAR(30) NOT NULL UNIQUE,
    original_points BIGINT UNSIGNED NOT NULL,
    remaining_points BIGINT UNSIGNED NOT NULL,
    earned_at DATETIME NOT NULL,
    expiry_date DATETIME NOT NULL,
    lot_status ENUM('ACTIVE', 'PARTIALLY_USED', 'CONSUMED', 'EXPIRED')
        NOT NULL DEFAULT 'ACTIVE',
    CONSTRAINT fk_lot_account
        FOREIGN KEY (account_id) REFERENCES LoyaltyAccount(account_id),
    CONSTRAINT fk_lot_accrual
        FOREIGN KEY (accrual_transaction_id)
        REFERENCES PointsTransaction(transaction_id),
    CHECK (original_points > 0),
    CHECK (remaining_points <= original_points),
    CHECK (expiry_date > earned_at)
) ENGINE=InnoDB;

CREATE INDEX idx_lot_expiry
    ON PointsLot(account_id, expiry_date, lot_status);

-- 11. REDEMPTION
CREATE TABLE IF NOT EXISTS Redemption (
    redemption_id VARCHAR(30) PRIMARY KEY,
    account_id VARCHAR(40) NOT NULL,
    reward_id INT UNSIGNED NOT NULL,
    points_redeemed BIGINT UNSIGNED NOT NULL,
    redemption_status ENUM(
        'PENDING', 'COMPLETED', 'FAILED', 'CANCELLED'
    ) NOT NULL,
    redemption_date DATETIME NOT NULL,
    idempotency_key VARCHAR(150) NOT NULL UNIQUE,
    CONSTRAINT fk_redemption_account
        FOREIGN KEY (account_id) REFERENCES LoyaltyAccount(account_id),
    CONSTRAINT fk_redemption_reward
        FOREIGN KEY (reward_id) REFERENCES Reward(reward_id),
    CHECK (points_redeemed > 0)
) ENGINE=InnoDB;

-- Add redemption reference after Redemption exists
ALTER TABLE PointsTransaction
    ADD CONSTRAINT fk_transaction_redemption
    FOREIGN KEY (redemption_id) REFERENCES Redemption(redemption_id);

-- 12. POINT ALLOCATION: WHICH LOTS WERE CONSUMED
CREATE TABLE IF NOT EXISTS PointsAllocation (
    allocation_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    lot_id BIGINT UNSIGNED NOT NULL,
    transaction_id VARCHAR(30) NOT NULL,
    allocation_type ENUM('REDEMPTION', 'RETURN_REVERSAL', 'EXPIRY')
        NOT NULL,
    points_allocated BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_allocation_lot
        FOREIGN KEY (lot_id) REFERENCES PointsLot(lot_id),
    CONSTRAINT fk_allocation_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES PointsTransaction(transaction_id),
    CHECK (points_allocated > 0),
    UNIQUE KEY uq_lot_transaction_type
        (lot_id, transaction_id, allocation_type)
) ENGINE=InnoDB;

-- 13. RETURN
CREATE TABLE IF NOT EXISTS Returns (
    return_id VARCHAR(30) PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    return_date DATETIME NOT NULL,
    return_status ENUM('REQUESTED', 'APPROVED', 'REJECTED', 'COMPLETED')
        NOT NULL,
    reason VARCHAR(255),
    CONSTRAINT fk_return_order
        FOREIGN KEY (order_id) REFERENCES Orders(order_id),
    CONSTRAINT fk_return_customer
        FOREIGN KEY (customer_id) REFERENCES Customer(customer_id)
) ENGINE=InnoDB;

-- 14. RETURN LINE
CREATE TABLE IF NOT EXISTS ReturnLine (
    return_line_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    return_id VARCHAR(30) NOT NULL,
    order_line_id BIGINT UNSIGNED NOT NULL,
    returned_quantity INT UNSIGNED NOT NULL,
    refund_amount DECIMAL(14,2) NOT NULL,
    CONSTRAINT fk_returnline_return
        FOREIGN KEY (return_id) REFERENCES Returns(return_id),
    CONSTRAINT fk_returnline_orderline
        FOREIGN KEY (order_line_id) REFERENCES OrderLine(order_line_id),
    CHECK (returned_quantity > 0),
    CHECK (refund_amount >= 0)
) ENGINE=InnoDB;

-- 15. CUSTOMER TIER HISTORY
CREATE TABLE IF NOT EXISTS CustomerTierHistory (
    tier_history_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    account_id VARCHAR(40) NOT NULL,
    previous_tier_id INT UNSIGNED,
    new_tier_id INT UNSIGNED NOT NULL,
    qualifying_spend_at_change DECIMAL(14,2) NOT NULL,
    changed_at DATETIME NOT NULL,
    reason VARCHAR(255),
    CONSTRAINT fk_tierhistory_account
        FOREIGN KEY (account_id) REFERENCES LoyaltyAccount(account_id),
    CONSTRAINT fk_tierhistory_old_tier
        FOREIGN KEY (previous_tier_id) REFERENCES Tier(tier_id),
    CONSTRAINT fk_tierhistory_new_tier
        FOREIGN KEY (new_tier_id) REFERENCES Tier(tier_id),
    CHECK (qualifying_spend_at_change >= 0)
) ENGINE=InnoDB;

-- 16. AUDIT EVENT
CREATE TABLE IF NOT EXISTS AuditEvent (
    audit_event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    entity_type VARCHAR(60) NOT NULL,
    entity_id VARCHAR(60) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_timestamp DATETIME NOT NULL,
    actor_type ENUM('CUSTOMER', 'SYSTEM', 'OPERATOR', 'ADMIN') NOT NULL,
    actor_id VARCHAR(60),
    event_details JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 17. RULE APPLICATION HISTORY
CREATE TABLE IF NOT EXISTS RuleApplication (
    rule_application_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    rule_id INT UNSIGNED NOT NULL,
    transaction_id VARCHAR(30),
    order_id VARCHAR(30),
    applied_at DATETIME NOT NULL,
    applied_value DECIMAL(14,4) NOT NULL,
    calculation_details JSON,
    CONSTRAINT fk_ruleapplication_rule
        FOREIGN KEY (rule_id) REFERENCES Rule(rule_id),
    CONSTRAINT fk_ruleapplication_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES PointsTransaction(transaction_id),
    CONSTRAINT fk_ruleapplication_order
        FOREIGN KEY (order_id) REFERENCES Orders(order_id)
) ENGINE=InnoDB;

-- 18. CONCURRENCY / IDEMPOTENCY REQUEST LOG
CREATE TABLE IF NOT EXISTS ProcessedRequest (
    request_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    idempotency_key VARCHAR(150) NOT NULL UNIQUE,
    operation_type VARCHAR(60) NOT NULL,
    account_id VARCHAR(40),
    request_status ENUM('STARTED', 'SUCCEEDED', 'FAILED') NOT NULL,
    response_details JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    CONSTRAINT fk_request_account
        FOREIGN KEY (account_id) REFERENCES LoyaltyAccount(account_id)
) ENGINE=InnoDB;
