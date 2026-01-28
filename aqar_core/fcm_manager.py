import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
import os
import logging

# إعداد الـ Logger لتسجيل الأخطاء بشكل احترافي
logger = logging.getLogger('django')

def ensure_firebase_initialized():
    if not firebase_admin._apps:
        try:
            # نحاول نجيب المسار من الإعدادات أو الافتراضي
            cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', os.path.join(settings.BASE_DIR, 'serviceAccountKey.json'))
            
            if not os.path.exists(cred_path):
                logger.error(f"🔥 ملف مفاتيح Firebase غير موجود: {cred_path}")
                return False

            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            logger.info("✅ تم الاتصال بـ Firebase بنجاح")
            return True
        except Exception as e:
            logger.error(f"❌ فشل الاتصال بـ Firebase: {e}")
            return False
    return True

def send_push_notification(user, title, body, link=None, icon_url=None):
    """
    إرسال إشعار للمستخدم (يدعم الويب والموبايل)
    """
    if not ensure_firebase_initialized():
        return

    if not user.fcm_token:
        logger.warning(f"🔕 المستخدم {user.username} ليس لديه FCM Token.")
        return

    # استخدام الرابط الافتراضي لو لم يتم تمرير رابط
    final_link = link if link else '/'

    try:
        # إعداد خيارات الويب (WebPush)
        # ملاحظة: WebpushFCMOptions يتطلب HTTPS، لو الرابط HTTP لا نضعه في الخيارات لتجنب الخطأ
        fcm_options = None
        if final_link.startswith('https'):
            fcm_options = messaging.WebpushFCMOptions(link=final_link)

        # بناء الرسالة
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
                image=icon_url 
            ),
            data={
                'url': final_link,         # للويب والتعامل اليدوي
                'click_action': 'FLUTTER_NOTIFICATION_CLICK', # للتطبيقات (Flutter)
                'sound': 'default'
            },
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    icon='ic_stat_r', # تأكد أن الأيقونة دي موجودة في تطبيق الأندرويد
                    color='#0f172a',
                    click_action='FLUTTER_NOTIFICATION_CLICK'
                ),
            ),
            webpush=messaging.WebpushConfig(
                headers={"Urgency": "high"},
                notification=messaging.WebpushNotification(
                    icon='/icons/icon-192x192.png',
                    badge='/icons/badge-72x72.png',
                ),
                fcm_options=fcm_options
            ),
            token=user.fcm_token,
        )

        response = messaging.send(message)
        logger.info(f"🚀 تم إرسال الإشعار للمستخدم {user.username}: {response}")
        return response

    except Exception as e:
        logger.error(f"❌ خطأ أثناء إرسال الإشعار للمستخدم {user.username}: {e}")
        return None