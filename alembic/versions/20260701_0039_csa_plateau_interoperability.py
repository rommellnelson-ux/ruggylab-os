"""add CSA Plateau patient and prescription links

Revision ID: 20260701_0039
Revises: 20260701_0038
"""

from alembic import op
import sqlalchemy as sa

revision = "20260701_0039"
down_revision = "20260701_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "csa_patient_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(length=30), nullable=False),
        sa.Column("external_patient_id", sa.String(length=100), nullable=False),
        sa.Column("external_dossier_no", sa.String(length=100), nullable=True),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system", "external_patient_id", name="uq_csa_external_patient"
        ),
        sa.UniqueConstraint("source_system", "patient_id", name="uq_csa_ruggylab_patient"),
    )
    op.create_index("ix_csa_patient_links_external_patient_id", "csa_patient_links", ["external_patient_id"])
    op.create_index("ix_csa_patient_links_external_dossier_no", "csa_patient_links", ["external_dossier_no"])
    op.create_index("ix_csa_patient_links_patient_id", "csa_patient_links", ["patient_id"])
    op.create_table(
        "csa_exam_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("csa_exam_code", sa.String(length=50), nullable=False),
        sa.Column("ruggylab_exam_code", sa.String(length=50), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "csa_exam_code",
            "ruggylab_exam_code",
            name="uq_csa_exam_mapping_pair",
        ),
    )
    op.create_index("ix_csa_exam_mappings_csa_exam_code", "csa_exam_mappings", ["csa_exam_code"])
    mappings = sa.table(
        "csa_exam_mappings",
        sa.column("csa_exam_code", sa.String()),
        sa.column("ruggylab_exam_code", sa.String()),
        sa.column("active", sa.Boolean()),
    )
    pairs = [
        ("BEDA005", "NFS"), ("BEDD001", "VS"), ("BNDA008", "GLYC"),
        ("BNDA009", "HBA1C"), ("BNDA012", "UREE"), ("BNDA013", "CREAT"),
        ("BNDA014", "UREE"), ("BNDA014", "CREAT"), ("BLDA007", "ALAT"),
        ("BLDA007", "ASAT"), ("BLDA005", "ALAT"), ("BLDA006", "ASAT"),
        ("BMDA003", "CRP"), ("BNDC001", "CALC"), ("BNDB002", "URIC"),
        ("BNDB001", "CHOL"), ("BNDB003", "TG"), ("BNDB005", "CHOL"),
        ("BNDB005", "TG"), ("BNDB005", "HDL"), ("BNDB005", "LDL"),
        ("BYDZ004", "AGHBS"), ("BGDE071", "HIV"), ("BGDC019", "WIDAL"),
        ("BFDA001", "ECBU"), ("BFDB006", "GE"), ("BFDB007", "GE"),
    ]
    op.bulk_insert(
        mappings,
        [
            {"csa_exam_code": source, "ruggylab_exam_code": target, "active": True}
            for source, target in pairs
        ],
    )
    op.create_table(
        "csa_prescription_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("external_prescription_id", sa.String(length=120), nullable=False),
        sa.Column("external_event_key", sa.String(length=180), nullable=False),
        sa.Column("exam_order_id", sa.Integer(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["exam_order_id"], ["exam_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_prescription_id", name="uq_csa_external_prescription"),
    )
    op.create_index("ix_csa_prescription_links_external_prescription_id", "csa_prescription_links", ["external_prescription_id"])
    op.create_index("ix_csa_prescription_links_exam_order_id", "csa_prescription_links", ["exam_order_id"])


def downgrade() -> None:
    op.drop_table("csa_prescription_links")
    op.drop_table("csa_exam_mappings")
    op.drop_table("csa_patient_links")
