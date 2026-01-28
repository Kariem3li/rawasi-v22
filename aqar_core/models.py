from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.core.validators import RegexValidator

# 1. BaseModel (الأب الروحي لكل الموديلات)
class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء", db_index=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        verbose_name="بواسطة",
        related_name="%(app_label)s_%(class)s_created_by"
    )
    class Meta: abstract = True

# 2. User (المستخدم الموحد)
class User(AbstractUser):
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$', message="رقم الهاتف يجب أن يكون بالصيغة الصحيحة: '+999999999'.")
    phone_number = models.CharField(validators=[phone_regex], max_length=20, unique=True, null=True, blank=True, verbose_name="رقم الهاتف")
    whatsapp_link = models.CharField(max_length=255, blank=True, verbose_name="رابط الواتساب")
    
    is_agent = models.BooleanField(default=False, verbose_name="هل هو موظف (مسوق)؟")
    interests = models.TextField(null=True, blank=True, verbose_name="الاهتمامات")

    CLIENT_TYPES = [('Buyer', 'مشترِي'), ('Seller', 'بائع'), ('Investor', 'مستثمر'), ('Marketer', 'مسوق')]
    client_type = models.CharField(max_length=10, choices=CLIENT_TYPES, default='Buyer', verbose_name="نوع العميل", db_index=True)
    
    interested_in_rent = models.BooleanField(default=False, verbose_name="مهتم بالإيجار")
    interested_in_buy = models.BooleanField(default=True, verbose_name="مهتم بالشراء")

    # توكن الإشعارات
    fcm_token = models.TextField(null=True, blank=True, verbose_name="FCM Token")
    is_owner = models.BooleanField(
        default=False, 
        verbose_name="مالك الموقع (Super Admin)",
        help_text="⛔ تحذير: هذا المستخدم محمي ولا يمكن حذفه نهائياً."
    )

    def save(self, *args, **kwargs):
        # توليد رابط واتساب تلقائي لو مش موجود
        if self.phone_number and not self.whatsapp_link:
            clean_number = self.phone_number.replace('+', '').replace(' ', '')
            self.whatsapp_link = f"https://wa.me/{clean_number}"
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # 🛡️ حماية المالك من الحذف الخطأ
        if self.is_owner:
            raise ValidationError("⛔ لا يمكن حذف مالك الموقع! قم بإلغاء صلاحية المالك أولاً.")
        super().delete(*args, **kwargs)

# 3. الإشعارات (Notifications)
class Notification(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', verbose_name="المستخدم", db_index=True)
    title = models.CharField(max_length=255, verbose_name="عنوان الإشعار")
    message = models.TextField(verbose_name="نص الرسالة")
    is_read = models.BooleanField(default=False, verbose_name="تمت القراءة؟", db_index=True)
    
    TYPE_CHOICES = [('System', 'إداري'), ('Listing', 'عقار'), ('Offer', 'عرض')]
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='System')
    
    # حقل إضافي للربط (مثلاً يفتح صفحة العقار عند الضغط)
    action_url = models.CharField(max_length=255, null=True, blank=True, verbose_name="رابط التوجيه")

    class Meta:
        verbose_name = "إشعار"
        verbose_name_plural = "الإشعارات"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.username}"

# 4. إعدادات الموقع العامة (Key-Value Store)
class SiteSetting(models.Model):
    key = models.CharField(max_length=100, unique=True, verbose_name="المفتاح (Code)") 
    value = models.TextField(verbose_name="القيمة") # ✅ تم التحويل لـ TextField لاستيعاب النصوص الطويلة
    description = models.CharField(max_length=255, null=True, blank=True, verbose_name="وصف الإعداد")

    class Meta:
        verbose_name = "إعداد عام"
        verbose_name_plural = "⚙️ إعدادات الموقع"

    def __str__(self):
        return f"{self.key} : {self.value[:50]}"

    def save(self, *args, **kwargs):
        cache.delete(f'site_setting_{self.key}') # مسح الكاش عند التعديل
        super().save(*args, **kwargs)

    @staticmethod
    def get_value(key, default=None):
        # دالة مساعدة لجلب الإعدادات من الكاش لعدم تحميل الداتابيز
        cached_value = cache.get(f'site_setting_{key}')
        if cached_value: return cached_value
        
        try:
            val = SiteSetting.objects.get(key=key).value
            cache.set(f'site_setting_{key}', val, timeout=86400) # كاش لمدة يوم
            return val
        except SiteSetting.DoesNotExist:
            return default

# 5. الإعلانات العامة (Push Notifications Helper)
class Announcement(models.Model):
    AUDIENCE_CHOICES = [
        ('ALL', 'الكل'),
        ('Buyer', 'المشترين فقط'),
        ('Seller', 'الملاك/البائعين فقط'),
        ('Broker', 'السماسرة فقط'),
    ]

    title = models.CharField(max_length=200, verbose_name="عنوان الرسالة")
    message = models.TextField(verbose_name="نص الرسالة")
    target_audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='ALL', verbose_name="الجمهور المستهدف")
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإرسال")
    
    is_sent = models.BooleanField(default=False, verbose_name="تم الإرسال؟", editable=False)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "إشعار جماعي"
        verbose_name_plural = "📣 إرسال إشعارات جماعية"

# 6. معلومات التواصل (Singleton Model)
class ContactInfo(models.Model):
    support_phone = models.CharField(max_length=20, default='01000000000', verbose_name="رقم الاتصال")
    whatsapp_number = models.CharField(max_length=20, default='20100000000', verbose_name="رقم الواتساب (بدون +)")
    facebook_url = models.URLField(blank=True, null=True, verbose_name="فيسبوك")
    instagram_url = models.URLField(blank=True, null=True, verbose_name="إنستجرام")
    
    class Meta:
        verbose_name = "بيانات التواصل"
        verbose_name_plural = "📞 بيانات التواصل (صف واحد فقط)"

    def __str__(self):
        return "بيانات التواصل الرئيسية"

    def save(self, *args, **kwargs):
        if not self.pk and ContactInfo.objects.exists():
            raise ValidationError("يوجد بالفعل بيانات تواصل مسجلة. قم بتعديل الموجودة بدلاً من إنشاء جديدة.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("لا يمكن حذف بيانات التواصل الأساسية، يمكنك تعديلها فقط.")