from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.shortcuts import render, redirect
from django import forms
from django.contrib import messages
from django.contrib.admin import helpers 
from .models import User, Notification, SiteSetting, Announcement, ContactInfo

# محاولة استيراد FCM لتجنب توقف الأدمن إذا لم يكن الملف جاهزاً
try:
    from .fcm_manager import send_push_notification 
except ImportError:
    def send_push_notification(*args, **kwargs): pass

# 1. فورم الإشعارات الجماعية
class BroadcastForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    title = forms.CharField(max_length=100, label="عنوان الإشعار", widget=forms.TextInput(attrs={'class': 'vTextField', 'placeholder': 'تحديث هام'}))
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 4, 'class': 'vLargeTextField', 'placeholder': 'اكتب نص الرسالة هنا...'}), label="نص الرسالة")

# 2. تخصيص لوحة المستخدمين
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'phone_number', 'client_type', 'is_agent', 'is_staff', 'date_joined')
    list_filter = ('client_type', 'is_staff', 'is_active', 'is_agent')
    search_fields = ('username', 'phone_number', 'first_name', 'email')
    ordering = ('-date_joined',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('بيانات إضافية', {
            'fields': ('phone_number', 'client_type', 'whatsapp_link', 'is_agent', 'interests')
        }),
        ('تفضيلات العميل', {
            'fields': ('interested_in_rent', 'interested_in_buy')
        }),
        ('بيانات النظام', {
            'fields': ('fcm_token', 'is_owner')
        }),
    )
    
    # حماية السوبر أدمن من التعديل الخطأ
    readonly_fields = ['last_login', 'date_joined']

    actions = ['send_broadcast_notification']

    def send_broadcast_notification(self, request, queryset):
        # التأكد من وجود مستخدمين
        if not queryset.exists():
            self.message_user(request, "لم يتم تحديد أي مستخدم!", level=messages.WARNING)
            return

        if 'apply' in request.POST:
            form = BroadcastForm(request.POST)
            if form.is_valid():
                title = form.cleaned_data['title']
                message = form.cleaned_data['message']
                
                notifications_to_create = []
                push_count = 0
                
                for user in queryset:
                    # تجهيز الإشعار لقاعدة البيانات
                    notifications_to_create.append(
                        Notification(user=user, title=title, message=message, notification_type='System')
                    )
                    
                    # محاولة إرسال للموبايل
                    if user.fcm_token:
                        try:
                            send_push_notification(user, title, message)
                            push_count += 1
                        except: pass
                
                # إدخال جماعي سريع (Bulk Create)
                Notification.objects.bulk_create(notifications_to_create)
                
                self.message_user(request, f"✅ تم الإرسال لـ {len(notifications_to_create)} مستخدم ({push_count} موبايل).")
                return redirect(request.get_full_path())
        else:
            form = BroadcastForm(initial={'_selected_action': request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)})

        # ملاحظة: تأكد من وجود ملف 'admin/broadcast_message.html' أو استخدم قالب جانغو الافتراضي
        return render(request, 'admin/broadcast_message.html', {
            'items': queryset, 
            'form': form, 
            'title': 'إرسال إشعار للمستخدمين المحددين',
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
        })

    send_broadcast_notification.short_description = "📢 إرسال إشعار فوري للمحددين"

# 3. لوحة الإشعارات
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('title', 'user__username', 'user__phone_number')
    date_hierarchy = 'created_at'

# 4. الإعلانات الإدارية (البرودكاست العام)
@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'target_audience', 'sent_at', 'status_icon')
    readonly_fields = ('is_sent', 'sent_at')
    list_filter = ('target_audience', 'is_sent')
    actions = ['resend_announcement']

    def status_icon(self, obj):
        return "✅ تم الإرسال" if obj.is_sent else "⏳ في الانتظار"
    status_icon.short_description = "الحالة"

    def save_model(self, request, obj, form, change):
        # لو دي أول مرة (create) ومش تعديل
        if not change and not obj.is_sent:
            self._send_bulk(obj)
            obj.is_sent = True
        
        super().save_model(request, obj, form, change)

    def resend_announcement(self, request, queryset):
        count = 0
        for announcement in queryset:
            self._send_bulk(announcement)
            count += 1
        self.message_user(request, f"تم إعادة إرسال {count} إعلان.")
    resend_announcement.short_description = "🔄 إعادة إرسال الإعلان"

    def _send_bulk(self, obj):
        users = User.objects.filter(is_active=True)
        if obj.target_audience != 'ALL':
            users = users.filter(client_type=obj.target_audience)
        
        notifications = [
            Notification(user=u, title=obj.title, message=obj.message, notification_type='System')
            for u in users
        ]
        Notification.objects.bulk_create(notifications)
        
        # إرسال Push في الخلفية (يمكن تحسينه لاحقاً بـ Celery)
        for u in users:
            try:
                if u.fcm_token: send_push_notification(u, obj.title, obj.message)
            except: pass

@admin.register(ContactInfo)
class ContactInfoAdmin(admin.ModelAdmin):
    list_display = ('support_phone', 'whatsapp_number')
    def has_add_permission(self, request):
        return not ContactInfo.objects.exists()

@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value_preview', 'description')
    search_fields = ('key', 'value')
    list_editable = ('description',)
    
    def value_preview(self, obj):
        return obj.value[:50] + "..." if len(obj.value) > 50 else obj.value
    value_preview.short_description = "القيمة"

admin.site.register(User, CustomUserAdmin)