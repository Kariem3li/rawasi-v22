from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ListingViewSet, GovernorateViewSet, CityViewSet, 
    MajorZoneViewSet, SubdivisionViewSet, CategoryViewSet, 
    FavoriteViewSet, PromotionViewSet , track_analytics, get_dashboard_stats
)

app_name = 'aqar' # ✅ إضافة مهمة عشان الـ Reverse URL

router = DefaultRouter()
router.register(r'listings', ListingViewSet, basename='listing')
router.register(r'promotions', PromotionViewSet, basename='promotion')
router.register(r'governorates', GovernorateViewSet)
router.register(r'cities', CityViewSet)
router.register(r'major-zones', MajorZoneViewSet)
router.register(r'subdivisions', SubdivisionViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'favorites', FavoriteViewSet, basename='favorite')

urlpatterns = [
    path('', include(router.urls)),
    path('analytics/track/', track_analytics, name='track-analytics'),
    path('analytics/dashboard/', get_dashboard_stats, name='dashboard-stats'),
]