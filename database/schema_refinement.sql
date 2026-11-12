
USE loyalty_points_db;

-- 1. Validate order totals
ALTER TABLE orders
ADD CONSTRAINT chk_orders_net_reconciliation
CHECK (net_amount = gross_amount - discount_amount);

ALTER TABLE orderline
ADD CONSTRAINT chk_orderline_total_reconciliation
CHECK (
    discount_amount <= quantity * unit_price
    AND line_net_amount =
        ROUND((quantity * unit_price) - discount_amount, 2)
);

-- 2. Link a reversal to its exact return line
ALTER TABLE pointstransaction
ADD COLUMN return_line_id BIGINT UNSIGNED NULL;

ALTER TABLE pointstransaction
ADD CONSTRAINT fk_transaction_return_line
FOREIGN KEY (return_line_id)
REFERENCES returnline(return_line_id);

-- 3. Record outstanding points debt
CREATE TABLE pointsdebt (
    debt_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    account_id VARCHAR(40) NOT NULL,
    source_return_line_id BIGINT UNSIGNED NOT NULL,
    original_accrual_transaction_id VARCHAR(30) NOT NULL,
    points_owed BIGINT UNSIGNED NOT NULL,
    points_remaining BIGINT UNSIGNED NOT NULL,
    debt_status ENUM(
        'OPEN', 'PARTIALLY_SETTLED', 'SETTLED'
    ) NOT NULL DEFAULT 'OPEN',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_debt_account
        FOREIGN KEY (account_id)
        REFERENCES loyaltyaccount(account_id),

    CONSTRAINT fk_debt_return_line
        FOREIGN KEY (source_return_line_id)
        REFERENCES returnline(return_line_id),

    CONSTRAINT fk_debt_original_accrual
        FOREIGN KEY (original_accrual_transaction_id)
        REFERENCES pointstransaction(transaction_id),

    CONSTRAINT uq_debt_return_line
        UNIQUE (source_return_line_id),

    CONSTRAINT chk_debt_points
        CHECK (
            points_owed > 0
            AND points_remaining <= points_owed
        )
);

-- 4. Record how future accruals settle outstanding debt
CREATE TABLE pointsdebtsettlement (
    settlement_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    debt_id BIGINT UNSIGNED NOT NULL,
    accrual_transaction_id VARCHAR(30) NOT NULL,
    points_settled BIGINT UNSIGNED NOT NULL,
    settled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_settlement_debt
        FOREIGN KEY (debt_id)
        REFERENCES pointsdebt(debt_id),

    CONSTRAINT fk_settlement_accrual
        FOREIGN KEY (accrual_transaction_id)
        REFERENCES pointstransaction(transaction_id),

    CONSTRAINT uq_debt_accrual
        UNIQUE (debt_id, accrual_transaction_id),

    CONSTRAINT chk_settlement_points
        CHECK (points_settled > 0)
);

-- 5. Add useful lookup indexes
CREATE INDEX idx_transaction_account_date
ON pointstransaction(account_id, transaction_date);

CREATE INDEX idx_points_lot_expiry
ON pointslot(expiry_date, lot_status);

CREATE INDEX idx_redemption_account_status
ON redemption(account_id, status);

CREATE INDEX idx_returns_order
ON returns(order_id, return_date);
