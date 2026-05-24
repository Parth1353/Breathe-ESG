from django.contrib import admin

from .models import (
    AuditEvent,
    EmissionActivity,
    EmissionFactor,
    IngestionBatch,
    Organization,
    RawSourceRecord,
    UserProfile,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name"]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "role"]
    list_filter = ["role", "organization"]


@admin.register(IngestionBatch)
class IngestionBatchAdmin(admin.ModelAdmin):
    list_display = ["source_type", "original_filename", "organization", "status", "ingested_at"]
    list_filter = ["source_type", "status", "organization"]
    search_fields = ["original_filename", "file_hash"]


@admin.register(RawSourceRecord)
class RawSourceRecordAdmin(admin.ModelAdmin):
    list_display = ["source_record_key", "batch", "parse_status", "created_at"]
    list_filter = ["parse_status", "batch__source_type"]
    search_fields = ["source_record_key"]


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ["factor_key", "activity_type", "scope", "factor_value", "factor_unit", "is_default"]
    list_filter = ["activity_type", "scope", "is_default"]
    search_fields = ["factor_key", "source_name"]


@admin.register(EmissionActivity)
class EmissionActivityAdmin(admin.ModelAdmin):
    list_display = ["source_type", "activity_type", "scope", "co2e_kg", "confidence", "status"]
    list_filter = ["source_type", "activity_type", "scope", "confidence", "status"]
    search_fields = ["raw_record__source_record_key"]


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ["action", "activity", "actor", "created_at"]
    list_filter = ["action", "created_at"]
