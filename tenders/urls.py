from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import DocumentViewSet, JobViewSet, MyBidsViewSet, price_index_view

router = DefaultRouter(trailing_slash=False)
router.register("jobs", JobViewSet, basename="job")
router.register("documents", DocumentViewSet, basename="document")
router.register("my-bids", MyBidsViewSet, basename="my-bids")

urlpatterns = [path("price-index", price_index_view)] + router.urls
