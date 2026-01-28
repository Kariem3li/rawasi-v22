from django.db import models
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from smart_selects.db_fields import ChainedForeignKey
from aqar_core.models import BaseModel
import random, string
from django.db.models.signals import post_save
from django.dispatch import receiver
from cloudinary_storage.storage import VideoMediaCloudinaryStorage
# from cloudinary_storage.validators import validate_video 

User = get_user_model()

def generate_ref(): 
    return 'REF-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# دالة لتنظيم مسارات الصور بالفولدرات حسب التاريخ (أفضل للأداء)
def get_listing_image_path(instance, filename):
    return f'listings/{instance.listing.reference_code}/photos/{filename}'

def get_listing_doc_path(instance, filename):
    return f'listings/{instance.listing.reference_code}/docs/{filename}'

# --- 1. الجغرافيا المرنة ---
class Governorate(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="المحافظة")
    def __str__(self): return self.name

class City(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="المدينة")
    governorate = models.ForeignKey(Governorate, on_delete=models.CASCADE, related_name='cities')
    zone_label = models.CharField(max_length=50, default='حي', verbose_name="تسمية المنطقة الكبرى")
    subdivision_label = models.CharField(max_length=50, default='مجاورة', verbose_name="تسمية المنطقة الصغرى")
    def __str__(self): return self.name

class MajorZone(models.Model):
    name = models.CharField(max_length=150)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='zones')
    def __str__(self): return f"{self.name}"

class Subdivision(models.Model):
    name = models.CharField(max_length=150)
    major_zone = models.ForeignKey(MajorZone, on_delete=models.CASCADE, related_name='subdivisions')
    def __str__(self): return self.name

# --- 2. التصنيف الديناميكي ---
class Category(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="نوع العقار (شقة/أرض)")
    slug = models.SlugField(unique=True, allow_unicode=True)
    def __str__(self): return self.name

class Feature(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='allowed_features')
    name = models.CharField(max_length=100, verbose_name="الخاصية (مثل: رخصة حفر)")
    
    INPUT_TYPES = [
        ('text', 'نص عادي (Text)'),
        ('bool', 'نعم/لا (Switch)'),
        ('number', 'قيمة رقمية (Buttons + Input)'),
    ]
    input_type = models.CharField(max_length=10, choices=INPUT_TYPES, default='bool', verbose_name="نوع الإدخال")
    is_quick_filter = models.BooleanField(
        default=False, 
        verbose_name="عرض في الفلتر السريع؟",
        help_text="لو اخترت نعم، الميزة دي هتظهر كزرار في الشريط العلوي (لازم تكون رقمية)"
    )
    options_list = models.CharField(
        max_length=200, 
        blank=True, 
        null=True, 
        help_text="للنوع الرقمي فقط: اكتب الأرقام مفصولة بفاصلة، مثال: 1,2,3,4,5,6",
        verbose_name="الأرقام المقترحة"
    )
    ICON_CHOICES = [
        ('CheckCircle2', '✔ علامة صح (افتراضي)'),
        ('ArrowUpFromLine', '🛗 أسانسير / مصعد'),
        ('Zap', '⚡ كهرباء / عداد'),
        ('Wind', '💨 غاز طبيعي'),
        ('Waves', '💧 مياه / سباحة'),
        ('Trees', '🌳 حديقة / لاندسكيب'),
        ('Car', '🚗 جراج / موقف'),
        ('Wifi', '📶 واي فاي / إنترنت'),
        ('ShieldCheck', '🛡 أمن وحراسة'),
        ('Snowflake', '❄ تكييف'),
        ('Tv', '📺 تلفزيون / دش'),
        ('Paintbucket', '🎨 تشطيب / ديكور'),
        ('Dumbbell', '💪 جيم / رياضة'),
        ('Utensils', '🍽 مطبخ'),
        ('BedDouble', '🛏 غرفة نوم'),
        ('Bath', '🛁 حمام'),
    ]
    icon = models.CharField(max_length=50, choices=ICON_CHOICES, default='CheckCircle2', verbose_name="شكل الأيقونة")

    def __str__(self): return f"{self.name} ({self.category.name})"

# --- 3. العقار ---
class Listing(BaseModel):
    reference_code = models.CharField(max_length=20, default=generate_ref, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True, allow_unicode=True)
    
    # حقول الفلترة الأساسية (تمت إضافة Index لها للأداء)
    price = models.DecimalField(max_digits=15, decimal_places=2, db_index=True)
    area_sqm = models.IntegerField(db_index=True)
    
    description = models.TextField()
    custom_map_image = models.ImageField(upload_to='listings_maps/', null=True, blank=True)
    
    bedrooms = models.IntegerField(null=True, blank=True)
    bathrooms = models.IntegerField(null=True, blank=True)
    floor_number = models.IntegerField(null=True, blank=True)
    building_number = models.CharField(max_length=50, null=True, blank=True)
    apartment_number = models.CharField(max_length=50, null=True, blank=True)
    project_name = models.CharField(max_length=100, null=True, blank=True)

    # العلاقات الجغرافية
    governorate = models.ForeignKey(Governorate, on_delete=models.CASCADE, related_name='listings')
    city = ChainedForeignKey(City, chained_field="governorate", chained_model_field="governorate", show_all=False, auto_choose=True, related_name='listings')
    major_zone = ChainedForeignKey(MajorZone, chained_field="city", chained_model_field="city", show_all=False, auto_choose=True, related_name='listings')
    subdivision = ChainedForeignKey(Subdivision, chained_field="major_zone", chained_model_field="major_zone", show_all=False, null=True, blank=True, related_name='listings')
    
    google_maps_url = models.URLField(null=True, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='listings')
    agent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assigned_listings')
    
    offer_type = models.CharField(max_length=10, choices=[('Sale', 'بيع'), ('Rent', 'إيجار')], default='Sale', db_index=True)
    STATUS_CHOICES = [('Pending', 'قيد المراجعة'), ('Available', 'متاح'), ('Sold', 'تم البيع')]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending', db_index=True)    
    is_finance_eligible = models.BooleanField(default=False)

    thumbnail = models.ImageField(upload_to='listings/thumbnails/%Y/%m/', null=True, blank=True)
    video = models.FileField(upload_to='listings/videos/%Y/%m/', storage=VideoMediaCloudinaryStorage(), null=True, blank=True)   
    youtube_url = models.URLField(
        null=True, blank=True, 
        verbose_name="رابط فيديو يوتيوب",
        help_text="لو حطيت رابط هنا، هيتعرض مكان الفيديو المرفوع."
    )
    
    # بيانات المالك والوثائق (مؤمنة)
    id_card_image = models.ImageField(upload_to='secure_docs/%Y/%m/', null=True, blank=True)
    contract_image = models.ImageField(upload_to='secure_docs/%Y/%m/', null=True, blank=True)
    owner_name = models.CharField(max_length=100, null=True, blank=True)
    owner_phone = models.CharField(max_length=20, null=True, blank=True)

    # التحليلات
    views_count = models.PositiveIntegerField(default=0, verbose_name="عدد المشاهدات")
    whatsapp_clicks = models.PositiveIntegerField(default=0, verbose_name="نقرات الواتساب")
    call_clicks = models.PositiveIntegerField(default=0, verbose_name="نقرات الاتصال")

    class Meta:
        ordering = ['-created_at']
        # 🚀 فهارس مركبة لتسريع البحث المعقد
        indexes = [
            models.Index(fields=['offer_type', 'status', 'price']),
            models.Index(fields=['city', 'offer_type', 'status']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug: 
            self.slug = slugify(self.title, allow_unicode=True) + f"-{self.reference_code}"
        super().save(*args, **kwargs)

    def get_contact_info(self):
        # التحقق من وجود الوكيل وتوفر بياناته
        if self.agent and getattr(self.agent, 'phone_number', None):
            return {
                'phone': self.agent.phone_number, 
                # تأكد أن موديل المستخدم لديه حقل whatsapp_link أو قم ببنائه هنا
                'whatsapp': getattr(self.agent, 'whatsapp_link', f"https://wa.me/{self.agent.phone_number.replace('+', '')}")
            }
        return {'phone': '01000000000', 'whatsapp': 'https://wa.me/201000000000'}

# --- 4. الجداول الفرعية ---
class ListingFeature(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='features_values')
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
    value = models.CharField(max_length=255)

class ListingImage(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=get_listing_image_path) # استخدام دالة المسار الديناميكي
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # تعيين الصورة الأولى كصورة مصغرة تلقائياً إذا لم تكن موجودة
        if not self.listing.thumbnail:
            self.listing.thumbnail = self.image
            self.listing.save()

class ListingDocument(BaseModel):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='documents')
    document_file = models.FileField(upload_to=get_listing_doc_path)
    document_type = models.CharField(max_length=50)

class ZoneMap(models.Model):
    major_zone = models.ForeignKey(MajorZone, on_delete=models.CASCADE, related_name='maps')
    map_file = models.FileField(upload_to='master_plans/')
    description = models.CharField(max_length=255)

class Interaction(BaseModel):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='interactions')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='interactions')
    interaction_type = models.CharField(max_length=50) # Increased length slightly

class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites', verbose_name="المستخدم")
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='favorited_by', verbose_name="العقار")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "مفضل"
        verbose_name_plural = "المفضلة"
        unique_together = ('user', 'listing')

    def __str__(self):
        return f"{self.user} liked {self.listing.title}"

# --- 5. الإعلانات المميزة والترويجية (Slider & Promotions) ---
class Promotion(models.Model):
    class PromoType(models.TextChoices):
        PROJECT = 'PROJECT', 'مشروع عقاري'
        SERVICE = 'SERVICE', 'خدمة'
        GENERAL = 'GENERAL', 'إعلان عام'
        LISTING = 'LISTING', 'إعلان VIP'
    
    master_plan = models.ImageField(upload_to='promotions/master_plans/', null=True, blank=True)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=150, blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True, null=True, allow_unicode=True)
    promo_type = models.CharField(max_length=20, choices=PromoType.choices, default=PromoType.GENERAL)
    developer_logo = models.ImageField(upload_to='promotions/logos/', null=True, blank=True)
    cover_image = models.ImageField(upload_to='promotions/covers/')
    video = models.FileField(upload_to='promotions/videos/', storage=VideoMediaCloudinaryStorage(), null=True, blank=True)
    details_video = models.FileField(
        upload_to='promotions/details_videos/', 
        storage=VideoMediaCloudinaryStorage(), 
        null=True, blank=True, 
        verbose_name="فيديو التفاصيل (مرفوع)"
    )
    youtube_url = models.URLField(
        null=True, blank=True, 
        verbose_name="رابط فيديو يوتيوب",
        help_text="إذا تم وضع الرابط، سيتم عرضه بدلاً من الفيديو المرفوع في قسم التفاصيل."
    )
    video_url = models.URLField(null=True, blank=True)
    target_listing = models.ForeignKey(Listing, on_delete=models.CASCADE, null=True, blank=True, related_name='promotions')
    description = models.TextField(blank=True)
    developer_name = models.CharField(max_length=100, blank=True, null=True)
    payment_system = models.TextField(blank=True, null=True)
    delivery_date = models.CharField(max_length=50, blank=True, null=True)
    project_features = models.TextField(blank=True, null=True)
    price_start_from = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    location_url = models.URLField(blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    whatsapp_number = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    views_count = models.PositiveIntegerField(default=0, verbose_name="عدد المشاهدات")
    clicks_count = models.PositiveIntegerField(default=0, verbose_name="عدد النقرات")
    whatsapp_clicks = models.PositiveIntegerField(default=0, verbose_name="نقرات الواتساب")
    call_clicks = models.PositiveIntegerField(default=0, verbose_name="نقرات الاتصال")

    def save(self, *args, **kwargs):
        if not self.slug: self.slug = slugify(self.title, allow_unicode=True) + f"-{generate_ref()}"
        super().save(*args, **kwargs)
    def __str__(self): return self.title

class PromotionImage(models.Model):
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name='gallery')
    image = models.ImageField(upload_to='promotions/gallery/')

class Transformation(models.Model):
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name='transformations')
    before_image = models.ImageField(upload_to='promotions/before/', verbose_name="صورة قبل")
    after_image = models.ImageField(upload_to='promotions/after/', verbose_name="صورة بعد")
    title = models.CharField(max_length=100, blank=True, verbose_name="عنوان (مثال: الريسبشن)")
    def __str__(self): return f"تحول: {self.title or 'بدون عنوان'}"
    
class PromotionUnit(models.Model):
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, related_name='units')
    linked_listing = models.ForeignKey(
        'Listing', 
        on_delete=models.SET_NULL, # Set null is safer here in case listing is deleted
        null=True, blank=True,
        verbose_name="العقار المرتبط (النموذج)",
        help_text="اختر العقار الذي يمثل هذا النموذج (فيلا، شقة، إلخ)"
    )
    custom_title = models.CharField(max_length=100, blank=True, verbose_name="عنوان الوحدة (اختياري)")

    def __str__(self):
        if self.linked_listing:
            return self.custom_title or self.linked_listing.title
        return self.custom_title or "وحدة غير مرتبطة"

# ✅✅✅ AnalyticsLog (محسن) ✅✅✅
class AnalyticsLog(models.Model):
    EVENT_TYPES = [
        ('VIEW_LISTING', 'مشاهدة عقار'),
        ('VIEW_PROMO', 'مشاهدة إعلان'),
        ('CLICK_PROMO', 'ضغط على الإعلان'),
        ('CLICK_WHATSAPP', 'ضغط واتساب'),
        ('CLICK_CALL', 'ضغط اتصال'),
        ('SEARCH', 'بحث'),
    ]
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, verbose_name="نوع الحدث", db_index=True)
    
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, null=True, blank=True, verbose_name="العقار")
    promotion = models.ForeignKey(Promotion, on_delete=models.CASCADE, null=True, blank=True, verbose_name="الإعلان")
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="المستخدم")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP الزائر")
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="التوقيت", db_index=True)

    class Meta:
        verbose_name = "سجل التحليلات"
        verbose_name_plural = "سجلات التحليلات"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

@receiver(post_save, sender=User)
def sync_user_data_to_listings(sender, instance, created, **kwargs):
    if not created:
        Listing.objects.filter(agent=instance).update(
            owner_phone=instance.phone_number,
            owner_name=f"{instance.first_name} {instance.last_name}".strip() or instance.username
        )