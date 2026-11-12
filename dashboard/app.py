

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))




import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from config.db_config import engine

st.set_page_config(
    page_title="Loyalty Points Management",
    page_icon="⭐",
    layout="wide"
)

st.title("⭐ Loyalty Points Management System")
st.caption("Customer loyalty, points ledger, redemptions and anomaly monitoring")

@st.cache_data(ttl=60)
def read_query(query, params=None):
    with engine.connect() as connection:
        return pd.read_sql(text(query), connection, params=params)

def show_metric(label, query, column):
    try:
        data = read_query(query)
        value = data.iloc[0][column]
        st.metric(label, f"{value:,}" if pd.notna(value) else "0")
    except Exception as error:
        st.metric(label, "Unavailable")
        st.caption(str(error))

try:
    read_query("SELECT 1")
    st.success("Database connected successfully")
except Exception as error:
    st.error("Database connection failed")
    st.exception(error)
    st.stop()

# Overview
st.header("1. Business Overview")

c1, c2, c3, c4 = st.columns(4)

with c1:
    show_metric("Customers", "SELECT COUNT(*) AS total FROM customer", "total")

with c2:
    show_metric("Orders", "SELECT COUNT(*) AS total FROM orders", "total")

with c3:
    show_metric(
        "Points earned",
        """SELECT COALESCE(SUM(points_change),0) AS total
           FROM pointstransaction
           WHERE transaction_type='ACCRUAL'""",
        "total"
    )

with c4:
    show_metric(
        "Points redeemed",
        """SELECT COALESCE(ABS(SUM(points_change)),0) AS total
           FROM pointstransaction
           WHERE transaction_type='REDEMPTION'""",
        "total"
    )

st.divider()

# Transaction analytics
st.header("2. Transaction Analytics")

try:
    transactions = read_query("""
        SELECT transaction_type, COUNT(*) AS transaction_count,
               SUM(points_change) AS points
        FROM pointstransaction
        GROUP BY transaction_type
        ORDER BY transaction_type
    """)

    if not transactions.empty:
        left, right = st.columns(2)

        with left:
            st.subheader("Transaction types")
            fig = px.bar(
                transactions,
                x="transaction_type",
                y="transaction_count",
                color="transaction_type",
                title="Transaction count by type"
            )
            st.plotly_chart(fig, use_container_width=True)

        with right:
            st.subheader("Points movement")
            fig = px.bar(
                transactions,
                x="transaction_type",
                y="points",
                color="transaction_type",
                title="Net points by transaction type"
            )
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(transactions, use_container_width=True)
except Exception as error:
    st.warning(f"Transaction analytics unavailable: {error}")

st.divider()

# Customer lookup
st.header("3. Customer Account Details")

customer_id = st.text_input(
    "Enter customer ID",
    placeholder="Example: CUST-000001"
)

if customer_id.strip():
    try:
        customer = read_query("""
            SELECT c.customer_id, c.first_name, c.last_name,
                   c.email, c.customer_status,
                   a.account_id, a.current_balance,
                   a.qualifying_spend, t.tier_name
            FROM customer c
            JOIN loyaltyaccount a ON c.customer_id = a.customer_id
            LEFT JOIN tier t ON a.tier_id = t.tier_id
            WHERE c.customer_id = :customer_id
        """, {"customer_id": customer_id.strip()})

        if customer.empty:
            st.warning("No customer found with that ID.")
        else:
            st.dataframe(customer, use_container_width=True)

            account_id = customer.iloc[0]["account_id"]

            history = read_query("""
                SELECT transaction_id, transaction_type,
                       points_change, transaction_date,
                       order_id, description
                FROM pointstransaction
                WHERE account_id = :account_id
                ORDER BY transaction_date DESC
                LIMIT 100
            """, {"account_id": account_id})

            st.subheader("Recent points history")
            st.dataframe(history, use_container_width=True)

    except Exception as error:
        st.error(f"Customer lookup failed: {error}")

st.divider()

# Redemptions
st.header("4. Redemption Monitoring")

try:
    redemptions = read_query("""
        SELECT redemption_status, COUNT(*) AS total
        FROM redemption
        GROUP BY redemption_status
    """)

    st.dataframe(redemptions, use_container_width=True)

    if not redemptions.empty:
        fig = px.pie(
            redemptions,
            names="redemption_status",
            values="total",
            title="Redemption status distribution"
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as error:
    st.warning(f"Redemption information unavailable: {error}")

st.divider()

# Anomaly monitoring
st.header("5. Anomaly Monitoring")

try:
    anomaly_path = "data/anomalies/anomaly_detection_results.csv"
    anomalies = pd.read_csv(anomaly_path)

    st.metric("Detected anomaly cases", len(anomalies))
    st.dataframe(anomalies, use_container_width=True)

except FileNotFoundError:
    st.warning("Anomaly detection results file was not found.")
except Exception as error:
    st.warning(f"Anomaly results unavailable: {error}")

st.divider()

# Data quality
st.header("6. Data Quality and Reconciliation")

try:
    report = read_query("""
        SELECT
            COUNT(*) AS total_accounts,
            SUM(CASE WHEN a.current_balance < 0 THEN 1 ELSE 0 END)
                AS negative_balances,
            SUM(
                CASE WHEN a.current_balance <>
                    COALESCE(l.ledger_balance, 0)
                THEN 1 ELSE 0 END
            ) AS balance_mismatches
        FROM loyaltyaccount a
        LEFT JOIN (
            SELECT account_id, SUM(points_change) AS ledger_balance
            FROM pointstransaction
            GROUP BY account_id
        ) l ON a.account_id = l.account_id
    """)

    st.dataframe(report, use_container_width=True)

    mismatches = int(report.iloc[0]["balance_mismatches"])
    negative = int(report.iloc[0]["negative_balances"])

    if mismatches == 0 and negative == 0:
        st.success("Account and ledger reconciliation passed.")
    else:
        st.error("Data quality issues detected. Review the reconciliation results.")

except Exception as error:
    st.warning(f"Reconciliation unavailable: {error}")

st.caption("Loyalty Points Management System | Read-only monitoring dashboard")
