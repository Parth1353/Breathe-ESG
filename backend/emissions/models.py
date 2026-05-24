import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        ANALYST = "analyst", "Analyst"
        VIEWER = "viewer", "Viewer"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ANALYST)

    def __str__(self):
        return f"{self.user} ({self.organization})"


class IngestionBatch(models.Model):
    class SourceType(models.TextChoices):
        SAP = "SAP", "SAP"
        UTILITY = "UTILITY", "Utility"
        TRAVEL = "TRAVEL", "Travel"

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    original_filename = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_batches",
    )
    ingested_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    error_summary = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "source_type"]),
            models.Index(fields=["file_hash"]),
        ]

    def __str__(self):
        return f"{self.source_type} import: {self.original_filename}"


class RawSourceRecord(models.Model):
    class ParseStatus(models.TextChoices):
        PARSED = "parsed", "Parsed"
        WARNING = "warning", "Warning"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="raw_records")
    source_row_number = models.IntegerField(null=True, blank=True)
    source_record_key = models.CharField(max_length=255)
    raw_payload = models.JSONField()
    parse_status = models.CharField(
        max_length=20,
        choices=ParseStatus.choices,
        default=ParseStatus.PARSED,
    )
    parse_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "source_record_key"]),
            models.Index(fields=["batch", "parse_status"]),
        ]

    def __str__(self):
        return self.source_record_key


class EmissionFactor(models.Model):
    class ActivityType(models.TextChoices):
        FUEL = "FUEL", "Fuel"
        ELECTRICITY = "ELECTRICITY", "Electricity"
        FLIGHT = "FLIGHT", "Flight"
        HOTEL = "HOTEL", "Hotel"
        CAR_RENTAL = "CAR_RENTAL", "Car rental"
        RAIL = "RAIL", "Rail"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    factor_key = models.CharField(max_length=255, unique=True)
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    scope = models.PositiveSmallIntegerField()
    scope3_category = models.PositiveSmallIntegerField(null=True, blank=True)
    factor_value = models.DecimalField(max_digits=18, decimal_places=8)
    factor_unit = models.CharField(max_length=80)
    geography = models.CharField(max_length=120, blank=True)
    source_name = models.CharField(max_length=255)
    effective_year = models.PositiveSmallIntegerField(default=2024)
    is_default = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["activity_type", "scope"]),
            models.Index(fields=["is_default"]),
        ]

    def __str__(self):
        return self.factor_key


class EmissionActivity(TimeStampedModel):
    class SourceType(models.TextChoices):
        SAP = "SAP", "SAP"
        UTILITY = "UTILITY", "Utility"
        TRAVEL = "TRAVEL", "Travel"

    class ActivityType(models.TextChoices):
        FUEL = "FUEL", "Fuel"
        ELECTRICITY = "ELECTRICITY", "Electricity"
        FLIGHT = "FLIGHT", "Flight"
        HOTEL = "HOTEL", "Hotel"
        CAR_RENTAL = "CAR_RENTAL", "Car rental"
        RAIL = "RAIL", "Rail"

    class Confidence(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending review"
        NEEDS_INFO = "needs_info", "Needs info"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        LOCKED = "locked", "Locked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="activities")
    raw_record = models.OneToOneField(
        RawSourceRecord,
        on_delete=models.CASCADE,
        related_name="activity",
    )
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    scope = models.PositiveSmallIntegerField()
    scope3_category = models.PositiveSmallIntegerField(null=True, blank=True)
    activity_start_date = models.DateField(null=True, blank=True)
    activity_end_date = models.DateField(null=True, blank=True)
    raw_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    raw_unit = models.CharField(max_length=40, blank=True)
    normalized_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    normalized_unit = models.CharField(max_length=40, blank=True)
    conversion_factor_used = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    emission_factor = models.ForeignKey(
        EmissionFactor,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    emission_factor_value = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    emission_factor_unit = models.CharField(max_length=80, blank=True)
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    confidence = models.CharField(max_length=20, choices=Confidence.choices, default=Confidence.HIGH)
    flags = models.JSONField(default=dict, blank=True)
    details = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_activities",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rejected_activities",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="edited_activities",
    )
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "source_type"]),
            models.Index(fields=["scope", "status"]),
            models.Index(fields=["activity_type", "confidence"]),
        ]
        verbose_name_plural = "Emission activities"

    @property
    def is_locked(self):
        return self.status == self.Status.LOCKED or self.locked_at is not None

    def __str__(self):
        return f"{self.source_type} {self.activity_type} {self.co2e_kg} kg CO2e"


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Created"
        EDITED = "edited", "Edited"
        FLAGGED = "flagged", "Flagged"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        LOCKED = "locked", "Locked"
        UNLOCKED_BY_ADMIN = "unlocked_by_admin", "Unlocked by admin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    activity = models.ForeignKey(EmissionActivity, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["organization", "action"]),
            models.Index(fields=["activity", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} {self.activity_id}"
