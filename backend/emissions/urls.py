from rest_framework.routers import DefaultRouter

from .views import EmissionActivityViewSet, IngestionBatchViewSet

router = DefaultRouter()
router.register("activities", EmissionActivityViewSet, basename="activity")
router.register("batches", IngestionBatchViewSet, basename="batch")

urlpatterns = router.urls
