from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import *
import json

User = get_user_model()

# --- 1. Serializers المساعدة (Features & Images) ---
class FeatureSerializer(serializers.ModelSerializer):
    class Meta: 
        model = Feature
        fields = ['id', 'name', 'input_type', 'icon', 'options_list', 'is_quick_filter']

class ListingFeatureSerializer(serializers.ModelSerializer):
    feature_name = serializers.CharField(source='feature.name', read_only=True)
    icon = serializers.CharField(source='feature.icon', read_only=True)
    input_type = serializers.CharField(source='feature.input_type', read_only=True)
    
    class Meta: 
        model = ListingFeature
        fields = ['id', 'feature', 'feature_name', 'icon', 'input_type', 'value']

class ListingImageSerializer(serializers.ModelSerializer):
    class Meta: 
        model = ListingImage
        fields = ['id', 'image']

class CategorySerializer(serializers.ModelSerializer):
    allowed_features = FeatureSerializer(many=True, read_only=True)
    class Meta: 
        model = Category
        fields = ['id', 'name', 'slug', 'allowed_features']

# --- 2. الجغرافيا ---
class GovernorateSerializer(serializers.ModelSerializer):
    class Meta: model = Governorate; fields = '__all__'
class CitySerializer(serializers.ModelSerializer):
    class Meta: model = City; fields = '__all__'
class MajorZoneSerializer(serializers.ModelSerializer):
    class Meta: model = MajorZone; fields = '__all__'
class SubdivisionSerializer(serializers.ModelSerializer):
    class Meta: model = Subdivision; fields = '__all__'

# --- 3. Listing Serializer (العقار) ---
class ListingSerializer(serializers.ModelSerializer):
    images = ListingImageSerializer(many=True, read_only=True)
    dynamic_features = ListingFeatureSerializer(source='features_values', many=True, read_only=True)
    
    # حقول العرض فقط (لتسهيل القراءة في الفرونت)
    governorate_name = serializers.CharField(source='governorate.name', read_only=True)
    city_name = serializers.CharField(source='city.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    major_zone_name = serializers.CharField(source='major_zone.name', read_only=True, allow_null=True)
    subdivision_name = serializers.CharField(source='subdivision.name', read_only=True, allow_null=True)
    
    # حقول تفاعلية
    is_favorite = serializers.SerializerMethodField()
    contact_info = serializers.SerializerMethodField() # ✅ لجلب الرقم الصحيح (مالك/وكيل)

    # حقول الكتابة (استقبال البيانات من الفورم)
    features_data = serializers.CharField(write_only=True, required=False)
    external_images = serializers.ListField(child=serializers.URLField(), write_only=True, required=False, allow_empty=True)
    external_video = serializers.URLField(write_only=True, required=False, allow_null=True, allow_blank=True)
    external_id_card = serializers.URLField(write_only=True, required=False, allow_null=True, allow_blank=True)
    external_contract = serializers.URLField(write_only=True, required=False, allow_null=True, allow_blank=True)
    deleted_image_ids = serializers.ListField(child=serializers.IntegerField(), write_only=True, required=False)

    class Meta: 
        model = Listing
        fields = '__all__'
        read_only_fields = [
            'slug', 'reference_code', 'created_at', 'updated_at', 
            'views_count', 'whatsapp_clicks', 'call_clicks' # التحليلات للقراءة فقط هنا
        ]

    def get_is_favorite(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # تم تعديل related_name في الموديل لـ favorited_by لكن favorites ستعمل أيضاً لو لم يتم تغييرها
            # الأفضل استخدام الاستعلام المباشر للأمان
            return Favorite.objects.filter(user=request.user, listing=obj).exists()
        return False

    def get_contact_info(self, obj):
        return obj.get_contact_info()

    def create(self, validated_data):
        features_json = validated_data.pop('features_data', None)
        external_images = validated_data.pop('external_images', [])
        external_video = validated_data.pop('external_video', None)
        external_id_card = validated_data.pop('external_id_card', None)
        external_contract = validated_data.pop('external_contract', None)
        validated_data.pop('deleted_image_ids', []) 

        listing = Listing.objects.create(**validated_data)

        # حفظ الصور
        if external_images:
            for url in external_images:
                ListingImage.objects.create(listing=listing, image=url)
            
            # تعيين أول صورة كـ Thumbnail إذا لم توجد
            if not listing.thumbnail and listing.images.exists():
                listing.thumbnail = listing.images.first().image
                listing.save()

        if external_video: listing.video = external_video
        if external_id_card: listing.id_card_image = external_id_card
        if external_contract: listing.contract_image = external_contract
        
        listing.save()

        if features_json: self._save_features(listing, features_json)
        return listing

    def update(self, instance, validated_data):
        features_input = validated_data.pop('features_data', None)
        external_images = validated_data.pop('external_images', [])
        external_video = validated_data.pop('external_video', None)
        external_id_card = validated_data.pop('external_id_card', None)
        external_contract = validated_data.pop('external_contract', None)
        deleted_image_ids = validated_data.pop('deleted_image_ids', [])
        validated_data.pop('uploaded_images', []) # تنظيف

        # تحديث الحقول الأساسية
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # تحديث الملفات
        if 'external_video' in self.initial_data: instance.video = external_video
        if external_id_card: instance.id_card_image = external_id_card
        if external_contract: instance.contract_image = external_contract

        instance.save()

        # حذف الصور القديمة
        if deleted_image_ids:
            ListingImage.objects.filter(id__in=deleted_image_ids, listing=instance).delete()

        # إضافة صور جديدة
        if external_images:
             for url in external_images:
                ListingImage.objects.create(listing=instance, image=url)
        
        # التأكد من وجود Thumbnail
        if not instance.thumbnail and instance.images.exists():
            instance.thumbnail = instance.images.first().image
            instance.save()

        if features_input: self._save_features(instance, features_input)
            
        return instance

    def _save_features(self, listing, features_input):
        try:
            if isinstance(features_input, str):
                features_dict = json.loads(features_input)
            else:
                features_dict = features_input
            
            for feature_id, value in features_dict.items():
                if value: 
                    try:
                        feature_obj = Feature.objects.get(id=int(feature_id))
                        ListingFeature.objects.update_or_create(
                            listing=listing, 
                            feature=feature_obj, 
                            defaults={'value': str(value)}
                        )
                    except (Feature.DoesNotExist, ValueError): 
                        pass
        except Exception as e:
            print(f"Error saving features: {e}")

# --- 4. التفضيلات والترويج ---
class FavoriteSerializer(serializers.ModelSerializer):
    listing = ListingSerializer(read_only=True)
    class Meta: model = Favorite; fields = '__all__'

class PromotionImageSerializer(serializers.ModelSerializer):
    class Meta: model = PromotionImage; fields = ['id', 'image']

class TransformationSerializer(serializers.ModelSerializer):
    class Meta: model = Transformation; fields = ['id', 'before_image', 'after_image', 'title']

class PromotionUnitSerializer(serializers.ModelSerializer):
    listing_id = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    
    class Meta:
        model = PromotionUnit
        fields = ['id', 'listing_id', 'title', 'image', 'price', 'type']
    
    # ✅ تم تأمين هذه الدوال لعدم حدوث خطأ إذا كان العقار محذوفاً
    def get_listing_id(self, obj): 
        return obj.linked_listing.id if obj.linked_listing else None
    
    def get_title(self, obj): 
        return obj.custom_title or (obj.linked_listing.title if obj.linked_listing else "وحدة")
    
    def get_image(self, obj): 
        if obj.linked_listing and obj.linked_listing.thumbnail:
            return obj.linked_listing.thumbnail.url
        return None
        
    def get_price(self, obj): 
        return obj.linked_listing.price if obj.linked_listing else 0
        
    def get_type(self, obj): 
        return obj.linked_listing.category.name if (obj.linked_listing and obj.linked_listing.category) else "وحدة"

class PromotionSerializer(serializers.ModelSerializer):
    gallery = PromotionImageSerializer(many=True, read_only=True)
    transformations = TransformationSerializer(many=True, read_only=True)
    units = PromotionUnitSerializer(many=True, read_only=True)
    final_url = serializers.SerializerMethodField()
    display_price = serializers.SerializerMethodField()
    
    class Meta: 
        model = Promotion
        fields = '__all__'
        
    def get_final_url(self, obj):
        if obj.promo_type == 'LISTING' and obj.target_listing: 
            return f"/listings/{obj.target_listing.id}"
        return f"/promotions/{obj.slug}"
        
    def get_display_price(self, obj):
        if obj.promo_type == 'LISTING' and obj.target_listing: 
            return obj.target_listing.price
        return obj.price_start_from

# --- 5. ✅ Analytics Serializer (جديد) ---
class AnalyticsLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticsLog
        fields = ['id', 'event_type', 'listing', 'promotion', 'created_at']
        read_only_fields = ['id', 'created_at']