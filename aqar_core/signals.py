from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import Notification
from .fcm_manager import send_push_notification
import logging

logger = logging.getLogger('django')

@receiver(post_save, sender=Notification)
def notification_created(sender, instance, created, **kwargs):
    """
    إرسال إشعار Firebase فقط بعد اكتمال عملية الحفظ في قاعدة البيانات
    """
    if created and instance.user.fcm_token: 
        # ✅ نستخدم on_commit عشان نضمن إن الداتابيز حفظت الإشعار قبل ما نبعته للموبايل
        transaction.on_commit(lambda: _send_fcm_safe(instance))

def _send_fcm_safe(instance):
    """
    دالة مساعدة لإرسال الإشعار والتعامل مع الأخطاء بصمت
    """
    try:
        # ✅ استخدام الرابط المخصص من الموديل (action_url) بدلاً من الثابت
        target_link = instance.action_url if instance.action_url else '/'
        
        send_push_notification(
            user=instance.user,
            title=instance.title,
            body=instance.message,
            link=target_link
        )
    except Exception as e:
        logger.error(f"❌ فشل إرسال الإشعار (Background Task): {e}")