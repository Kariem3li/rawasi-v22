from rest_framework import serializers
from django.contrib.auth import get_user_model
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer, UserSerializer as BaseUserSerializer
from .models import Notification, SiteSetting

User = get_user_model()

# ==========================================
# 1. خاص بـ Djoser (التسجيل والتوثيق)
# ==========================================

class CustomUserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = ('id', 'phone_number', 'password', 'first_name', 'last_name', 'client_type')
        extra_kwargs = {
            'phone_number': {'required': True},
            'email': {'required': False},
            'first_name': {'required': True}, # مهم عشان شكل الموقع
            'last_name': {'required': True},
        }

    def validate(self, attrs):
        # جعل اسم المستخدم هو نفسه رقم الهاتف تلقائياً
        if 'phone_number' in attrs:
            attrs['username'] = attrs['phone_number']
        return super().validate(attrs)

class CustomUserSerializer(BaseUserSerializer):
    """
    هذا السيريالايزر يستخدمه المستخدم عندما يطلب بياناته الشخصية (/auth/users/me/)
    """
    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = (
            'id', 'username', 'first_name', 'last_name', 'phone_number', 'email',
            'client_type', 'whatsapp_link', 'interests', 
            'interested_in_rent', 'interested_in_buy', 'is_agent', 'is_staff'
        )
        read_only_fields = ('is_staff', 'is_agent', 'whatsapp_link') 

# ==========================================
# 2. الاستخدام العام (Public Usage)
# ==========================================

class PublicAgentSerializer(serializers.ModelSerializer):
    """
    لعرض بيانات الوكيل أو المالك للعامة (بدون بيانات حساسة)
    """
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'whatsapp_link', 'phone_number', 'is_agent']

class SiteSettingSerializer(serializers.ModelSerializer):
    class Meta: 
        model = SiteSetting
        fields = ['key', 'value']

class NotificationSerializer(serializers.ModelSerializer):
    class Meta: 
        model = Notification
        fields = '__all__'
        read_only_fields = ['created_at', 'is_read'] # المستخدم لا ينشئ إشعارات لنفسه