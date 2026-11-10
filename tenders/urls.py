from rest_framework.routers import DefaultRouter

from .views import DocumentViewSet, JobViewSet, MyBidsViewSet

router = DefaultRouter(trailing_slash=False)
router.register("jobs", JobViewSet, basename="job")
router.register("documents", DocumentViewSet, basename="document")
router.register("my-bids", MyBidsViewSet, basename="my-bids")

urlpatterns = router.urls
