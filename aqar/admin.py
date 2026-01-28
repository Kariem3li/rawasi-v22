from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from .models import *
from aqar_core.models import Notification
try:
    from aqar_core.fcm_manager import send_push_notification
except ImportError:
    def send_push_notification(*args, **kwargs): pass

# ✅ 1. عرض التحليلات (Analytics Log)
@admin.register(AnalyticsLog)
class AnalyticsLogAdmin(admin.ModelAdmin):
    # 🚀 تحسين الأداء: جلب البيانات المرتبطة في استعلام واحد
    list_select_related = ('user', 'listing', 'promotion')
    
    list_display = ('event_type_colored', 'get_target_name', 'get_visitor_info', 'get_total_ad_views', 'created_at')
    list_filter = ('event_type', 'created_at', ('user', admin.RelatedOnlyFieldListFilter))
    search_fields = ('user__username', 'user__first_name', 'user__phone_number', 'listing__title', 'promotion__title', 'ip_address')
    readonly_fields = ('event_type', 'listing', 'promotion', 'user', 'ip_address', 'created_at')

    def get_visitor_info(self, obj):
        if obj.user:
            name = f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username
            phone = getattr(obj.user, 'phone_number', "لا يوجد رقم")
            return format_html(
                '<div style="line-height: 1.2;">'
                '<span style="font-weight:bold; color:#2c3e50;">👤 {}</span><br>'
                '<span style="font-size:12px; color:#16a085;">📞 {}</span>'
                '</div>', name, phone
            )
        else:
            return format_html('<span style="color:#7f8c8d; font-size:12px;">👻 زائر غير مسجل<br>IP: {}</span>', obj.ip_address)
    get_visitor_info.short_description = "بيانات الزائر"

    def get_total_ad_views(self, obj):
        count = 0
        # ✅ حماية من الخطأ في حالة حذف العقار أو الإعلان
        if obj.listing: count = obj.listing.views_count
        elif obj.promotion: count = obj.promotion.views_count
        return format_html('<span style="background:#34495e; color:white; padding:3px 8px; border-radius:10px; font-weight:bold; font-size:12px;">👁️ {} مشاهدة</span>', count)
    get_total_ad_views.short_description = "إجمالي زيارات الإعلان"

    def event_type_colored(self, obj):
        colors = {'VIEW_LISTING': 'gray', 'VIEW_PROMO': 'gray', 'CLICK_WHATSAPP': 'green', 'CLICK_CALL': 'blue', 'CLICK_PROMO': 'orange'}
        return format_html('<span style="color:{}; font-weight:bold;">{}</span>', colors.get(obj.event_type, 'black'), obj.get_event_type_display())
    event_type_colored.short_description = "الحدث"

    def get_target_name(self, obj):
        if obj.listing: return f"عقار: {obj.listing.title}"
        elif obj.promotion: return f"إعلان: {obj.promotion.title}"
        return "-"
    get_target_name.short_description = "العنصر المستهدف"

# ✅ 2. Inlines للعقارات
class ListingFeatureInline(admin.TabularInline):
    model = ListingFeature
    extra = 1
    autocomplete_fields = ['feature'] # 🚀 يسرع البحث لو عندك مميزات كتير

class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0
    readonly_fields = ['image_preview']
    def image_preview(self, obj):
        return format_html('<img src="{}" style="width: 100px; height: auto;" />', obj.image.url) if obj.image else ""

# ✅ 3. لوحة تحكم العقارات (Listing Admin)
class ListingAdmin(admin.ModelAdmin):
    # 🚀 تحسين الأداء هام جداً هنا
    list_select_related = ('agent', 'category', 'governorate', 'city')
    
    list_display = ('title', 'status_badge', 'price', 'views_count', 'whatsapp_clicks', 'get_publisher_summary', 'created_at')
    list_filter = ('status', 'offer_type', 'category', 'governorate', 'is_finance_eligible')
    search_fields = ('title', 'reference_code', 'owner_phone', 'owner_name', 'agent__username', 'agent__phone_number')
    
    inlines = [ListingFeatureInline, ListingImageInline]
    actions = ['approve_listings', 'reject_listings']

    fieldsets = (
        ('📊 إحصائيات وحالة الإعلان', {
            'fields': ('status', 'is_finance_eligible', 'views_count', 'whatsapp_clicks', 'call_clicks')
        }),
        ('👤 بيانات الناشر والتواصل', {
            'fields': ('get_publisher_details', 'get_customer_contact_number'), 
            'description': 'هنا تظهر بيانات الموظف/الناشر، والرقم الذي سيظهر للعملاء (الزوار) على الموقع.'
        }),
        ('📝 بيانات المالك (للتوثيق الداخلي)', {
            'fields': ('agent', 'owner_name', 'owner_phone')
        }),
        ('🏠 التفاصيل الأساسية', {
            'fields': ('title', 'category', 'offer_type', 'price', 'area_sqm', 'description')
        }),
        ('تفاصيل الموقع والوحدة', {
            'fields': ('governorate', 'city', 'major_zone', 'subdivision', 'project_name', 'building_number', 'floor_number', 'apartment_number', 'bedrooms', 'bathrooms')
        }),
        ('الموقع على الخريطة', {
            'fields': ('google_maps_url', 'latitude', 'longitude'),
            'description': 'يمكنك وضع رابط جوجل ماب مباشرة، أو إدخال خطوط الطول والعرض يدوياً.'
        }),
        ('الوثائق والوسائط', {
            'fields': ('thumbnail', 'video', 'youtube_url', 'custom_map_image', 'id_card_image', 'contract_image')
        }),
    )
    
    readonly_fields = ['get_publisher_details', 'get_customer_contact_number', 'views_count', 'whatsapp_clicks', 'call_clicks', 'created_at']

    def get_publisher_details(self, obj):
        if obj.agent:
            return format_html(
                """<div style='background-color:#e3f2fd; padding:10px; border-radius:5px; border:1px solid #90caf9;'>
                    <strong>الاسم:</strong> {} <br>
                    <strong>رقم الهاتف:</strong> {} <br>
                </div>""",
                obj.agent.first_name + " " + obj.agent.last_name if obj.agent.first_name else obj.agent.username,
                getattr(obj.agent, 'phone_number', "لا يوجد رقم"),
            )
        return "لا يوجد وكيل (ناشر)"
    get_publisher_details.short_description = "بيانات الناشر"

    def get_customer_contact_number(self, obj):
        contact_phone = obj.owner_phone or (getattr(obj.agent, 'phone_number', "غير محدد") if obj.agent else "غير محدد")
        return format_html(
            """<div style='background-color:#e8f5e9; padding:10px; border-radius:5px; border:1px solid #a5d6a7;'>
                <span style='font-size:14px; font-weight:bold; color:green;'>📞 الرقم الظاهر: {}</span>
                <br><a href='https://wa.me/2{}' target='_blank' style='display:inline-block; margin-top:5px; color:#fff; background-color:#25D366; padding:3px 8px; border-radius:4px; text-decoration:none;'>تجربة واتساب</a>
            </div>""",
            contact_phone, contact_phone.replace(" ", "") if contact_phone != "غير محدد" else ""
        )
    get_customer_contact_number.short_description = "رقم التواصل للعملاء"

    def get_publisher_summary(self, obj):
        return obj.agent.username if obj.agent else "-"
    get_publisher_summary.short_description = "الناشر"

    def status_badge(self, obj):
        colors = {'Pending': 'orange', 'Available': 'green', 'Sold': 'red'}
        return format_html(f'<span style="color:white; background:{colors.get(obj.status, "gray")}; padding:3px 8px; border-radius:5px;">{obj.get_status_display()}</span>')
    status_badge.short_description = "الحالة"

    def approve_listings(self, request, queryset):
        queryset.update(status='Available')
        count = 0
        for listing in queryset:
            if listing.agent:
                # يمكنك تفعيل التنبيهات هنا إذا كان نظام التنبيهات جاهزاً
                pass
                count += 1
        self.message_user(request, f"تم نشر {count} إعلان بنجاح.")
    approve_listings.short_description = "✅ قبول ونشر"

    def reject_listings(self, request, queryset):
        queryset.update(status='Pending')
        self.message_user(request, "تم تعليق الإعلانات.")
    reject_listings.short_description = "⛔ تعليق / رفض"

admin.site.register(Listing, ListingAdmin)

# ✅ 4. Inlines للإعلانات (Promotions)
class PromotionImageInline(admin.TabularInline):
    model = PromotionImage
    extra = 1
    readonly_fields = ['image_preview']
    def image_preview(self, obj):
        return format_html('<img src="{}" style="width: 100px; height: auto;" />', obj.image.url) if obj.image else ""

class TransformationInline(admin.StackedInline):
    model = Transformation
    extra = 1
    classes = ('collapse',)
    verbose_name = "صورة قبل وبعد"
    verbose_name_plural = "معرض صور التشطيبات"

class PromotionUnitInline(admin.TabularInline):
    model = PromotionUnit
    extra = 1
    verbose_name = "وحدة"
    verbose_name_plural = "أنواع الوحدات"

# ✅ 5. لوحة تحكم الإعلانات (Promotion Admin)
@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('title', 'promo_type', 'is_active', 'views_count', 'clicks_count', 'display_order', 'created_at')
    list_filter = ('promo_type', 'is_active')
    list_editable = ('is_active', 'display_order')
    search_fields = ('title', 'description', 'developer_name')
    readonly_fields = ('views_count', 'clicks_count', 'whatsapp_clicks', 'call_clicks')
    
    inlines = [PromotionImageInline, TransformationInline, PromotionUnitInline] 
    
    fieldsets = (
        ('الإحصائيات', {
            'fields': ('views_count', 'clicks_count', 'whatsapp_clicks', 'call_clicks')
        }),
        ('الإعدادات الأساسية', {
            'fields': ('title', 'subtitle', 'promo_type', 'cover_image', 'developer_logo', 'master_plan', 'is_active', 'display_order')
        }),
        ('ربط بعقار (اختياري)', {
            'fields': ('target_listing',),
        }),
        ('تفاصيل المشروع', {
            'fields': ('description', 'video', 'details_video', 'youtube_url', 'video_url', 'developer_name', 'payment_system', 'delivery_date', 'project_features', 'price_start_from')
        }),
        ('الموقع والخريطة', {
            'fields': ('latitude', 'longitude', 'location_url'),
        }),
        ('معلومات التواصل', {
            'fields': ('phone_number', 'whatsapp_number')
        }),
    )

# ✅ 6. تسجيل باقي الموديلات
@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'input_type', 'is_quick_filter', 'icon')
    list_filter = ('category', 'input_type', 'is_quick_filter')
    list_editable = ('is_quick_filter', 'input_type', 'icon')
    search_fields = ('name',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

admin.site.register(Governorate)
admin.site.register(City)
admin.site.register(MajorZone)
admin.site.register(Subdivision)