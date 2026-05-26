from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import EmissionActivityViewSet, IngestionBatchViewSet, IngestionUploadView

router = DefaultRouter()
router.register("activities", EmissionActivityViewSet, basename="activity")
router.register("batches", IngestionBatchViewSet, basename="batch")

urlpatterns = [
    path("ingestions/", IngestionUploadView.as_view(), name="ingestion-upload"),
] + router.urls
