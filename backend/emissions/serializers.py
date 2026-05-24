from rest_framework import serializers

from .models import AuditEvent, EmissionActivity, IngestionBatch, RawSourceRecord


class RawSourceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawSourceRecord
        fields = [
            "id",
            "source_row_number",
            "source_record_key",
            "raw_payload",
            "parse_status",
            "parse_errors",
            "created_at",
        ]


class AuditEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "actor_email",
            "action",
            "before",
            "after",
            "reason",
            "created_at",
        ]


class EmissionActivitySerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    batch_filename = serializers.CharField(source="batch.original_filename", read_only=True)
    emission_factor_key = serializers.CharField(source="emission_factor.factor_key", read_only=True)

    class Meta:
        model = EmissionActivity
        fields = [
            "id",
            "organization_name",
            "batch",
            "batch_filename",
            "raw_record",
            "source_type",
            "activity_type",
            "scope",
            "scope3_category",
            "activity_start_date",
            "activity_end_date",
            "raw_quantity",
            "raw_unit",
            "normalized_quantity",
            "normalized_unit",
            "conversion_factor_used",
            "emission_factor",
            "emission_factor_key",
            "emission_factor_value",
            "emission_factor_unit",
            "co2e_kg",
            "confidence",
            "flags",
            "details",
            "status",
            "approved_at",
            "rejected_at",
            "locked_at",
            "edited_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization_name",
            "batch",
            "batch_filename",
            "raw_record",
            "source_type",
            "activity_type",
            "scope",
            "scope3_category",
            "activity_start_date",
            "activity_end_date",
            "raw_quantity",
            "raw_unit",
            "conversion_factor_used",
            "emission_factor",
            "emission_factor_key",
            "emission_factor_value",
            "emission_factor_unit",
            "status",
            "approved_at",
            "rejected_at",
            "locked_at",
            "edited_at",
            "created_at",
            "updated_at",
        ]


class EmissionActivityDetailSerializer(EmissionActivitySerializer):
    raw_source_record = RawSourceRecordSerializer(source="raw_record", read_only=True)
    audit_events = AuditEventSerializer(many=True, read_only=True)

    class Meta(EmissionActivitySerializer.Meta):
        fields = EmissionActivitySerializer.Meta.fields + [
            "raw_source_record",
            "audit_events",
        ]


class IngestionBatchSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    raw_record_count = serializers.IntegerField(read_only=True)
    activity_count = serializers.IntegerField(read_only=True)
    failed_record_count = serializers.IntegerField(read_only=True)
    warning_record_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = IngestionBatch
        fields = [
            "id",
            "organization_name",
            "source_type",
            "original_filename",
            "file_hash",
            "ingested_at",
            "status",
            "error_summary",
            "raw_record_count",
            "activity_count",
            "failed_record_count",
            "warning_record_count",
        ]


class IngestionBatchDetailSerializer(IngestionBatchSerializer):
    activities = EmissionActivitySerializer(many=True, read_only=True)

    class Meta(IngestionBatchSerializer.Meta):
        fields = IngestionBatchSerializer.Meta.fields + ["activities"]
