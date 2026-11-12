"""Initial control plane schema

Creates the multi-user control-plane tables (users, households, gateways,
devices, intents, decisions, model registry, schedules, multi-WAN links,
audit log, pairing codes, observations). Legacy telemetry tables owned by
``network.telemetry.metrics_store`` are left untouched.

Revision ID: 0001_initial_control_plane
Revises:
Create Date: 2026-11-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_control_plane"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    op.create_table(
        "households",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_households_owner_id"), "households", ["owner_id"], unique=False)

    op.create_table(
        "household_members",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("household_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_household_members_household_id"), "household_members", ["household_id"], unique=False)
    op.create_index(op.f("ix_household_members_user_id"), "household_members", ["user_id"], unique=False)

    op.create_table(
        "gateways",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("household_id", sa.String(), nullable=False),
        sa.Column("gateway_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("public_key_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("version", sa.String(length=32), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("capabilities", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="unpaired"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offline_buffered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gateway_id"),
    )
    op.create_index(op.f("ix_gateways_household_id"), "gateways", ["household_id"], unique=False)
    op.create_index(op.f("ix_gateways_gateway_id"), "gateways", ["gateway_id"], unique=True)

    op.create_table(
        "pairing_codes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("gateway_id", sa.String(length=64), nullable=True),
        sa.Column("household_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_pairing_codes_code"), "pairing_codes", ["code"], unique=True)
    op.create_index(op.f("ix_pairing_codes_gateway_id"), "pairing_codes", ["gateway_id"], unique=False)
    op.create_index(op.f("ix_pairing_codes_household_id"), "pairing_codes", ["household_id"], unique=False)

    op.create_table(
        "devices",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("gateway_id", sa.String(), nullable=False),
        sa.Column("household_id", sa.String(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("local_alias", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("member_id", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("connection_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upload_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("download_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_upload_rate_mbps", sa.Float(), nullable=True),
        sa.Column("current_download_rate_mbps", sa.Float(), nullable=True),
        sa.Column("current_qoe", sa.Float(), nullable=True),
        sa.Column("traffic_class", sa.String(length=32), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("associated_policy", sa.String(length=128), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["gateway_id"], ["gateways.gateway_id"]),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_devices_gateway_id"), "devices", ["gateway_id"], unique=False)
    op.create_index(op.f("ix_devices_household_id"), "devices", ["household_id"], unique=False)
    op.create_index(op.f("ix_devices_device_id"), "devices", ["device_id"], unique=False)
    op.create_index(op.f("ix_devices_member_id"), "devices", ["member_id"], unique=False)

    op.create_table(
        "intents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("gateway_id", sa.String(), nullable=False),
        sa.Column("household_id", sa.String(), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("traffic_class", sa.String(length=32), nullable=True),
        sa.Column("objective", sa.String(length=200), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("urgency", sa.String(length=32), nullable=False, server_default="normal"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("min_service_floor_mbps", sa.Float(), nullable=True),
        sa.Column("allowed_trade_offs", sa.Text(), nullable=True),
        sa.Column("approval_state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["gateway_id"], ["gateways.gateway_id"]),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_intents_gateway_id"), "intents", ["gateway_id"], unique=False)
    op.create_index(op.f("ix_intents_household_id"), "intents", ["household_id"], unique=False)
    op.create_index(op.f("ix_intents_device_id"), "intents", ["device_id"], unique=False)

    op.create_table(
        "decisions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("gateway_id", sa.String(), nullable=False),
        sa.Column("household_id", sa.String(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("input_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_versions", sa.Text(), nullable=True),
        sa.Column("model_confidence", sa.Float(), nullable=True),
        sa.Column("capacity_estimate_mbps", sa.Float(), nullable=True),
        sa.Column("capacity_uncertainty_mbps", sa.Float(), nullable=True),
        sa.Column("forecast_mbps", sa.Float(), nullable=True),
        sa.Column("qoe_before", sa.Text(), nullable=True),
        sa.Column("qoe_after", sa.Text(), nullable=True),
        sa.Column("fairness_before", sa.Float(), nullable=True),
        sa.Column("fairness_after", sa.Float(), nullable=True),
        sa.Column("selected_policy", sa.Text(), nullable=True),
        sa.Column("policy_constraints", sa.Text(), nullable=True),
        sa.Column("enforcement_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("kernel_readback", sa.Text(), nullable=True),
        sa.Column("verification_result", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.Column("rollback_status", sa.String(length=32), nullable=False, server_default="not_required"),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["gateway_id"], ["gateways.gateway_id"]),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_decisions_gateway_id"), "decisions", ["gateway_id"], unique=False)
    op.create_index(op.f("ix_decisions_household_id"), "decisions", ["household_id"], unique=False)

    op.create_table(
        "model_registry",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("model_type", sa.String(length=64), nullable=False),
        sa.Column("training_dataset_provenance", sa.Text(), nullable=True),
        sa.Column("feature_schema", sa.Text(), nullable=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_results", sa.Text(), nullable=True),
        sa.Column("inference_latency_ms", sa.Float(), nullable=True),
        sa.Column("model_health", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("last_inference_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("fallback_behaviour", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_registry_name"), "model_registry", ["name"], unique=False)

    op.create_table(
        "schedules",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("household_id", sa.String(), nullable=False),
        sa.Column("gateway_id", sa.String(length=64), nullable=True),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("traffic_class", sa.String(length=32), nullable=True),
        sa.Column("expected_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("expected_bandwidth_mbps", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="user"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_schedules_household_id"), "schedules", ["household_id"], unique=False)
    op.create_index(op.f("ix_schedules_gateway_id"), "schedules", ["gateway_id"], unique=False)
    op.create_index(op.f("ix_schedules_device_id"), "schedules", ["device_id"], unique=False)

    op.create_table(
        "multi_wan_links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("gateway_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("link_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("capacity_download_mbps", sa.Float(), nullable=True),
        sa.Column("capacity_upload_mbps", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("loss_percent", sa.Float(), nullable=True),
        sa.Column("data_cost_tier", sa.String(length=32), nullable=True),
        sa.Column("user_limit_mbps", sa.Float(), nullable=True),
        sa.Column("preferred", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("backup", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["gateway_id"], ["gateways.gateway_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_multi_wan_links_gateway_id"), "multi_wan_links", ["gateway_id"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("gateway_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_gateway_id"), "audit_logs", ["gateway_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)

    op.create_table(
        "observations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("gateway_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("quality", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_observations_gateway_id"), "observations", ["gateway_id"], unique=False)
    op.create_index(op.f("ix_observations_client_id"), "observations", ["client_id"], unique=False)
    op.create_index(op.f("ix_observations_observed_at"), "observations", ["observed_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_observations_observed_at"), table_name="observations")
    op.drop_index(op.f("ix_observations_client_id"), table_name="observations")
    op.drop_index(op.f("ix_observations_gateway_id"), table_name="observations")
    op.drop_table("observations")
    op.drop_index(op.f("ix_audit_logs_user_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_gateway_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_multi_wan_links_gateway_id"), table_name="multi_wan_links")
    op.drop_table("multi_wan_links")
    op.drop_index(op.f("ix_schedules_device_id"), table_name="schedules")
    op.drop_index(op.f("ix_schedules_gateway_id"), table_name="schedules")
    op.drop_index(op.f("ix_schedules_household_id"), table_name="schedules")
    op.drop_table("schedules")
    op.drop_index(op.f("ix_model_registry_name"), table_name="model_registry")
    op.drop_table("model_registry")
    op.drop_index(op.f("ix_decisions_household_id"), table_name="decisions")
    op.drop_index(op.f("ix_decisions_gateway_id"), table_name="decisions")
    op.drop_table("decisions")
    op.drop_index(op.f("ix_intents_device_id"), table_name="intents")
    op.drop_index(op.f("ix_intents_household_id"), table_name="intents")
    op.drop_index(op.f("ix_intents_gateway_id"), table_name="intents")
    op.drop_table("intents")
    op.drop_index(op.f("ix_devices_member_id"), table_name="devices")
    op.drop_index(op.f("ix_devices_device_id"), table_name="devices")
    op.drop_index(op.f("ix_devices_household_id"), table_name="devices")
    op.drop_index(op.f("ix_devices_gateway_id"), table_name="devices")
    op.drop_table("devices")
    op.drop_index(op.f("ix_pairing_codes_household_id"), table_name="pairing_codes")
    op.drop_index(op.f("ix_pairing_codes_gateway_id"), table_name="pairing_codes")
    op.drop_index(op.f("ix_pairing_codes_code"), table_name="pairing_codes")
    op.drop_table("pairing_codes")
    op.drop_index(op.f("ix_gateways_gateway_id"), table_name="gateways")
    op.drop_index(op.f("ix_gateways_household_id"), table_name="gateways")
    op.drop_table("gateways")
    op.drop_index(op.f("ix_household_members_user_id"), table_name="household_members")
    op.drop_index(op.f("ix_household_members_household_id"), table_name="household_members")
    op.drop_table("household_members")
    op.drop_index(op.f("ix_households_owner_id"), table_name="households")
    op.drop_table("households")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
