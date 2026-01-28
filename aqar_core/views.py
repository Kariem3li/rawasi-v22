from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404

from .models import Notification, ContactInfo
# استيراد السيريالايزر النظيف الذي اعتمدناه سابقاً
from .serializers import (
    NotificationSerializer, 
    CustomUserSerializer, 
    CustomUserCreateSerializer
)

User = get_user_model()

# 1. معلومات التواصل (للفوتر والاتصال)
@api_view(['GET'])
@permission_classes([AllowAny])
def contact_info(request):
    # نأخذ آخر تحديث لبيانات التواصل
    info = ContactInfo.objects.last()
    
    if info:
        return Response({
            'support_phone': info.support_phone,
            'whatsapp_number': info.whatsapp_number,
            'facebook_url': info.facebook_url,
            'instagram_url': info.instagram_url,
        })
    else:
        # قيم افتراضية لمنع الكراش
        return Response({
            'support_phone': '01000000000',
            'whatsapp_number': '201000000000',
            'facebook_url': '',
            'instagram_url': '',
        })

# 2. إدارة الإشعارات
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # المستخدم يرى إشعاراته فقط
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return Response({'status': 'success', 'message': 'تم قراءة جميع الإشعارات'})

# 3. تحديث توكن الفايربيس (للموبايل والويب)
class UpdateFCMTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        fcm_token = request.data.get('fcm_token')
        if fcm_token:
            request.user.fcm_token = fcm_token
            request.user.save()
            return Response({'status': 'updated', 'message': 'تم تحديث التوكن بنجاح'})
        return Response({'error': 'Token is required'}, status=400)

# 4. إدارة المستخدمين (خاص بلوحة تحكم الأدمن Dashboard)
class UserViewSet(viewsets.ModelViewSet):
    """
    هذا الـ ViewSet مخصص للمشرفين فقط لإدارة المستخدمين والموظفين
    """
    queryset = User.objects.all()
    permission_classes = [IsAdminUser] # ⛔ للأدمن فقط
    filter_backends = [filters.SearchFilter]
    search_fields = ['phone_number', 'username', 'first_name', 'email']

    def get_serializer_class(self):
        # عند الإنشاء نستخدم سيريالايزر يتعامل مع الباسورد
        if self.action == 'create':
            return CustomUserCreateSerializer
        # في العرض نستخدم السيريالايزر العادي
        return CustomUserSerializer

    def create(self, request, *args, **kwargs):
        # نستخدم السيريالايزر المخصص للإنشاء
        serializer = CustomUserCreateSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # 1. تفعيل صلاحيات الموظف لو تم اختيارها
            if request.data.get('is_staff'):
                user.is_staff = True
            
            # 2. تعيين الصلاحيات (Role/Group)
            role_id = request.data.get('role') # يفضل إرسال ID الجروب
            if role_id:
                try:
                    group = Group.objects.get(id=role_id)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    pass
            
            user.save()
            return Response(CustomUserSerializer(user).data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # 🛡️ حماية المالك السوبر (أنت)
        if instance.is_owner:
            return Response(
                {"detail": "⛔ عذراً، هذا الحساب محمي (Super Owner) ولا يمكن حذفه."}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # حماية النفس (عشان الأدمن ميمسحش نفسه بالغلط ويقفل الداشبورد في وشه)
        if instance == request.user:
             return Response(
                {"detail": "لا يمكن حذف حسابك الحالي وأنت مسجل الدخول به."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        return super().destroy(request, *args, **kwargs)

    # نقطة إضافية لجلب قائمة الأدوار المتاحة للفرونت إند
    @action(detail=False, methods=['get'])
    def roles(self, request):
        groups = Group.objects.values('id', 'name')
        return Response(groups)