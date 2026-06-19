"""Prescriptions d'examens (exam_orders) + comptabilité (invoices)

Revision ID: 20260618_0030
Revises: 20260618_0029
Create Date: 2026-06-18 00:00:30

Deux briques additives et idempotentes :
  - le « fil » du labo : exam_orders + exam_order_items (bon de demande
    d'analyses → échantillon → résultats par examen) ;
  - la comptabilité : invoices + invoice_lines + invoice_payments
    (facturation FCFA, répartition CMU, encaissements).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260618_0030"
down_revision = "20260618_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if "exam_orders" not in tables:
        op.create_table(
            "exam_orders",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
            sa.Column("prescriber", sa.String(150), nullable=True),
            sa.Column("clinical_info", sa.Text(), nullable=True),
            sa.Column("priority", sa.String(20), nullable=False, server_default="routine"),
            sa.Column("status", sa.String(20), nullable=False, server_default="prescribed"),
            sa.Column("ordered_at", sa.DateTime(), nullable=False),
            sa.Column("sample_id", sa.Integer(), sa.ForeignKey("samples.id"), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
        op.create_index("ix_exam_orders_patient_id", "exam_orders", ["patient_id"])
        op.create_index("ix_exam_orders_status", "exam_orders", ["status"])

    if "exam_order_items" not in tables:
        op.create_table(
            "exam_order_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("exam_orders.id"), nullable=False),
            sa.Column("exam_code", sa.String(50), nullable=False),
            sa.Column("exam_label", sa.String(150), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("result_id", sa.Integer(), sa.ForeignKey("results.id"), nullable=True),
        )
        op.create_index("ix_exam_order_items_order_id", "exam_order_items", ["order_id"])

    if "invoices" not in tables:
        op.create_table(
            "invoices",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("invoice_number", sa.String(40), nullable=False, unique=True),
            sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=True),
            sa.Column("patient_label", sa.String(150), nullable=True),
            sa.Column(
                "exam_order_id", sa.Integer(), sa.ForeignKey("exam_orders.id"), nullable=True
            ),
            sa.Column("patient_type", sa.String(20), nullable=False, server_default="UNINSURED"),
            sa.Column("insurance_id", sa.String(50), nullable=True),
            sa.Column("gross_total_xof", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("discount_xof", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("net_total_xof", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("cnam_part_xof", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("patient_due_xof", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("paid_xof", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("status", sa.String(20), nullable=False, server_default="issued"),
            sa.Column("issued_at", sa.DateTime(), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
        op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"], unique=True)
        op.create_index("ix_invoices_status", "invoices", ["status"])

    if "invoice_lines" not in tables:
        op.create_table(
            "invoice_lines",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
            sa.Column("exam_code", sa.String(50), nullable=True),
            sa.Column("label", sa.String(150), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("unit_price_xof", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("line_total_xof", sa.Numeric(12, 2), nullable=False, server_default="0"),
        )
        op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    if "invoice_payments" not in tables:
        op.create_table(
            "invoice_payments",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
            sa.Column("amount_xof", sa.Numeric(12, 2), nullable=False),
            sa.Column("method", sa.String(20), nullable=False, server_default="CASH"),
            sa.Column("reference", sa.String(100), nullable=True),
            sa.Column("paid_at", sa.DateTime(), nullable=False),
            sa.Column("received_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )
        op.create_index("ix_invoice_payments_invoice_id", "invoice_payments", ["invoice_id"])


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    for tbl in ("invoice_payments", "invoice_lines", "invoices", "exam_order_items", "exam_orders"):
        if tbl in tables:
            op.drop_table(tbl)
