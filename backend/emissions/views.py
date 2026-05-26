import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AuditEvent, EmissionActivity, IngestionBatch, Organization
from .serializers import (
    EmissionActivityDetailSerializer,
    EmissionActivitySerializer,
    IngestionBatchDetailSerializer,
    IngestionBatchSerializer,
)
from .services.ingestion import ingest_sap, ingest_travel, ingest_utility, load_emission_factors


def request_actor(request):
    return request.user if request.user and request.user.is_authenticated else None


def request_organization(request):
    if request.user and request.user.is_authenticated and hasattr(request.user, "userprofile"):
        return request.user.userprofile.organization
    organization, _ = Organization.objects.get_or_create(name="Demo Enterprise Client")
    return organization


def snapshot(activity):
    return {
        "normalized_quantity": str(activity.normalized_quantity) if activity.normalized_quantity is not None else None,
        "normalized_unit": activity.normalized_unit,
        "co2e_kg": str(activity.co2e_kg) if activity.co2e_kg is not None else None,
        "confidence": activity.confidence,
        "flags": activity.flags,
        "details": activity.details,
        "status": activity.status,
    }


class EmissionActivityViewSet(viewsets.ModelViewSet):
    serializer_class = EmissionActivitySerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        queryset = (
            EmissionActivity.objects.select_related(
                "organization",
                "batch",
                "raw_record",
                "emission_factor",
            )
            .prefetch_related("audit_events")
            .order_by("-created_at")
        )
        for field in ["source_type", "status", "confidence"]:
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{field: value})
        scope = self.request.query_params.get("scope")
        if scope:
            queryset = queryset.filter(scope=scope)
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return EmissionActivityDetailSerializer
        return EmissionActivitySerializer

    def partial_update(self, request, *args, **kwargs):
        activity = self.get_object()
        if activity.is_locked:
            return Response(
                {"detail": "Locked activities cannot be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        before = snapshot(activity)
        patch_data = request.data.copy()
        reason = patch_data.pop("reason", "")
        if isinstance(reason, list):
            reason = reason[0] if reason else ""
        serializer = self.get_serializer(activity, data=patch_data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        activity.refresh_from_db()
        activity.edited_by = request_actor(request)
        activity.edited_at = timezone.now()
        activity.save(update_fields=["edited_by", "edited_at", "updated_at"])
        AuditEvent.objects.create(
            organization=activity.organization,
            activity=activity,
            actor=request_actor(request),
            action=AuditEvent.Action.EDITED,
            before=before,
            after=snapshot(activity),
            reason=reason,
        )
        return Response(self.get_serializer(activity).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        activity = self.get_object()
        if activity.is_locked:
            return Response(
                {"detail": "Locked activities cannot be approved again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        before = snapshot(activity)
        activity.status = EmissionActivity.Status.APPROVED
        activity.approved_by = request_actor(request)
        activity.approved_at = timezone.now()
        activity.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        AuditEvent.objects.create(
            organization=activity.organization,
            activity=activity,
            actor=request_actor(request),
            action=AuditEvent.Action.APPROVED,
            before=before,
            after=snapshot(activity),
            reason=request.data.get("reason", ""),
        )
        return Response(self.get_serializer(activity).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        activity = self.get_object()
        if activity.is_locked:
            return Response(
                {"detail": "Locked activities cannot be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        before = snapshot(activity)
        activity.status = EmissionActivity.Status.REJECTED
        activity.rejected_by = request_actor(request)
        activity.rejected_at = timezone.now()
        activity.save(update_fields=["status", "rejected_by", "rejected_at", "updated_at"])
        AuditEvent.objects.create(
            organization=activity.organization,
            activity=activity,
            actor=request_actor(request),
            action=AuditEvent.Action.REJECTED,
            before=before,
            after=snapshot(activity),
            reason=request.data.get("reason", ""),
        )
        return Response(self.get_serializer(activity).data)

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        activity = self.get_object()
        if activity.is_locked:
            return Response(
                {"detail": "Activity is already locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if activity.status != EmissionActivity.Status.APPROVED:
            return Response(
                {"detail": "Only approved activities can be locked for audit."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        before = snapshot(activity)
        activity.status = EmissionActivity.Status.LOCKED
        activity.locked_at = timezone.now()
        activity.save(update_fields=["status", "locked_at", "updated_at"])
        AuditEvent.objects.create(
            organization=activity.organization,
            activity=activity,
            actor=request_actor(request),
            action=AuditEvent.Action.LOCKED,
            before=before,
            after=snapshot(activity),
            reason=request.data.get("reason", ""),
        )
        return Response(self.get_serializer(activity).data)


class IngestionBatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        return (
            IngestionBatch.objects.select_related("organization")
            .prefetch_related("activities")
            .annotate(
                raw_record_count=Count("raw_records", distinct=True),
                activity_count=Count("activities", distinct=True),
                failed_record_count=Count(
                    "raw_records",
                    filter=Q(raw_records__parse_status="failed"),
                    distinct=True,
                ),
                warning_record_count=Count(
                    "raw_records",
                    filter=Q(raw_records__parse_status="warning"),
                    distinct=True,
                ),
            )
            .order_by("-ingested_at")
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return IngestionBatchDetailSerializer
        return IngestionBatchSerializer


class IngestionUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    INGESTERS = {
        IngestionBatch.SourceType.SAP: ingest_sap,
        IngestionBatch.SourceType.UTILITY: ingest_utility,
        IngestionBatch.SourceType.TRAVEL: ingest_travel,
    }

    def post(self, request):
        source_type = request.data.get("source_type")
        uploaded_file = request.FILES.get("file")
        if source_type not in self.INGESTERS:
            return Response(
                {"detail": "source_type must be one of SAP, UTILITY, or TRAVEL."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(uploaded_file, UploadedFile):
            return Response(
                {"detail": "Upload a source file using the 'file' field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suffix = Path(uploaded_file.name).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as temporary:
            for chunk in uploaded_file.chunks():
                temporary.write(chunk)
            temporary.flush()
            try:
                organization = request_organization(request)
                load_emission_factors(settings.PROJECT_ROOT / "data")
                counts = self.INGESTERS[source_type](
                    organization,
                    settings.PROJECT_ROOT / "data",
                    uploaded_by=request_actor(request),
                    source_path=temporary.name,
                    original_filename=uploaded_file.name,
                )
            except Exception as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        batch = (
            IngestionBatch.objects.filter(organization=organization, source_type=source_type)
            .order_by("-ingested_at")
            .first()
        )
        return Response(
            {
                "batch": IngestionBatchSerializer(batch).data if batch else None,
                "raw_records": counts.raw_records,
                "activities": counts.activities,
                "warnings": counts.warnings,
                "failed": counts.failed,
            },
            status=status.HTTP_201_CREATED,
        )
