from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    NotificationViewSet, UpdateFCMTokenView, 
    contact_info, # تأكد أن هذه الدالة موجودة في views.py
    # RegisterView, CustomAuthToken # ❌ تم حذفهم لأننا سنستخدم Djoser
)

app_name = 'aqar_core'

router = DefaultRouter()
router.register(r'notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    # ✅ مسارات المصادقة الجاهزة من Djoser (تسجيل، دخول، تفعيل، تغيير كلمة سر)
    # تأكد أنك ضفت 'djoser' في INSTALLED_APPS في settings.py
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.authtoken')), 
    
    # ✅ مساراتك الخاصة
    path('update-fcm/', UpdateFCMTokenView.as_view(), name='update-fcm'),
    path('contact-info/', contact_info, name='contact-info'),
    
    # باقي المسارات (Notifications)
    path('', include(router.urls)),
]