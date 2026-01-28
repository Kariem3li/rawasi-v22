from rest_framework import viewsets, permissions, filters, status
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser, BasePermission, SAFE_METHODS
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.db.models import Q, F, Count, Sum
from django.db import transaction
from .models import *
from .serializers import *
from .filters import ListingFilter

# --- ViewSets الجغرافية ---
class GovernorateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Governorate.objects.all()
    serializer_class = GovernorateSerializer
    pagination_class = None

class CityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = City.objects.select_related('governorate').all()
    serializer_class = CitySerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['governorate']

class MajorZoneViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MajorZone.objects.select_related('city').all()
    serializer_class = MajorZoneSerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['city']

class SubdivisionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Subdivision.objects.select_related('major_zone').all()
    serializer_class = SubdivisionSerializer
    pagination_class = None
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['major_zone']

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.prefetch_related('allowed_features').all()
    serializer_class = CategorySerializer
    pagination_class = None
    
    @action(detail=True, methods=['get'])
    def features(self, request, pk=None):
        category = self.get_object()
        serializer = FeatureSerializer(category.allowed_features.all(), many=True)
        return Response(serializer.data)

# --- الصلاحيات ---
class IsOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS: return True
        return obj.agent == request.user or request.user.is_staff

# --- Listing ViewSet (محسن للأداء) ---
class ListingViewSet(viewsets.ModelViewSet):
    serializer_class = ListingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ListingFilter
    search_fields = ['title', 'description', 'reference_code', 'project_name']
    ordering_fields = ['price', 'created_at', 'area_sqm', 'views_count']
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        
        # 🚀 Eager Loading: جلب كل البيانات دفعة واحدة لمنع N+1 Problem
        queryset = Listing.objects.select_related(
            'governorate', 'city', 'category', 'agent', 'major_zone', 'subdivision'
        ).prefetch_related(
            'images',           
            'features_values',  
            'features_values__feature' 
        )

        # منطق الفلترة (مين يشوف إيه)
        if self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            # المشرف والمالك يشوفوا كل حاجة، الغريب يشوف المتاح فقط
            if user.is_staff:
                pass 
            elif user.is_authenticated:
                queryset = queryset.filter(Q(status='Available') | Q(agent=user))
            else:
                queryset = queryset.filter(status='Available')
        elif self.action == 'list':
            queryset = queryset.filter(status='Available')

        # فلترة المميزات الديناميكية (Dynamic Features Filtering)
        qp = self.request.query_params
        for key, value in qp.items():
            if not value or value == '0': continue
            
            # فلترة متعددة (Checkbox List)
            if key.startswith('multi_feat_'):
                try:
                    ids_str = key.replace('multi_feat_', '')
                    feature_ids = ids_str.split('-')
                    value = value.strip()
                    # لو القيمة رقم نبحث بالـ Regex عشان الدقة، لو نص نبحث بـ Contains
                    lookup = 'regex' if value.replace('.', '', 1).isdigit() else 'icontains'
                    
                    filter_kwargs = {
                        'features_values__feature_id__in': feature_ids,
                        f'features_values__value__{lookup}': fr'(^|\D){value}(\D|$)' if lookup == 'regex' else value
                    }
                    queryset = queryset.filter(**filter_kwargs)
                except: pass

            # فلترة مفردة (Specific Feature)
            elif key.startswith('feat_'):
                try:
                    feature_id = key.split('_')[1]
                    queryset = queryset.filter(
                        features_values__feature_id=feature_id,
                        features_values__value__icontains=value.strip()
                    )
                except: pass
        
        # ✅ distinct ضروري جداً هنا لمنع تكرار النتائج بعد الفلترة المعقدة
        return queryset.distinct().order_by('-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        # الأدمن ينشر فوراً، المستخدم العادي "قيد المراجعة"
        status = 'Available' if user.is_staff else 'Pending'
        
        # تحديد بيانات التواصل (إما المكتوبة يدوياً أو بيانات البروفايل)
        incoming_phone = serializer.validated_data.get('owner_phone', '')
        incoming_name = serializer.validated_data.get('owner_name', '')
        
        final_phone = incoming_phone if incoming_phone else getattr(user, 'phone_number', '')
        final_name = incoming_name if incoming_name else f"{user.first_name} {user.last_name}".strip() or user.username
        
        serializer.save(agent=user, status=status, owner_phone=final_phone, owner_name=final_name)

    def perform_update(self, serializer):
        user = self.request.user
        # لو المستخدم عدل إعلانه، يرجع "قيد المراجعة" تاني للأمان
        if not user.is_staff:
            serializer.save(status='Pending')
        else:
            serializer.save()

    @action(detail=False, methods=['get'])
    def my_listings(self, request):
        if not request.user.is_authenticated:
            return Response({'detail': 'غير مصرح'}, status=401)
        
        listings = Listing.objects.filter(agent=request.user).select_related(
            'governorate', 'city', 'category'
        ).prefetch_related('images').order_by('-created_at')
        
        page = self.paginate_queryset(listings)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(listings, many=True)
        return Response(serializer.data)

# --- المفضلة ---
class FavoriteViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FavoriteSerializer 
    
    def list(self, request):
        favorites = Favorite.objects.filter(user=request.user).select_related(
            'listing', 'listing__city', 'listing__governorate'
        ).prefetch_related('listing__images')
        
        # التعامل مع حالة أن العقار قد يكون محذوفاً ولكن في المفضلة
        valid_favorites = [f for f in favorites if f.listing] 
        return Response(self.get_serializer(valid_favorites, many=True).data)

    @action(detail=False, methods=['post'])
    def toggle(self, request):
        listing_id = request.data.get('listing_id')
        if not listing_id: return Response({'error': 'Listing ID required'}, status=400)
        
        listing = get_object_or_404(Listing, pk=listing_id)
        fav, created = Favorite.objects.get_or_create(user=request.user, listing=listing)
        
        if not created: 
            fav.delete()
            return Response({'status': 'removed', 'is_favorite': False})
        return Response({'status': 'added', 'is_favorite': True})

# --- العروض الترويجية ---
class PromotionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Promotion.objects.filter(is_active=True).order_by('display_order', '-created_at')
    serializer_class = PromotionSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['slug', 'promo_type', 'is_active']

# --- ✅ نظام التحليلات المتطور (Atomic Updates) ---
@api_view(['POST'])
@authentication_classes([TokenAuthentication, SessionAuthentication])
@permission_classes([AllowAny])
def track_analytics(request):
    """
    تسجيل الأحداث بشكل ذري (Atomic) لتجنب مشاكل التزامن
    """
    event_type = request.data.get('event_type')
    target_id = request.data.get('target_id')
    target_type = request.data.get('target_type') # 'listing' or 'promotion'
    
    if not target_id or not str(target_id).isdigit():
        return Response({'error': 'Invalid ID'}, status=400)

    # الحصول على IP بشكل دقيق
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

    # تحديد نوع الحدث للسجل
    log_event = 'VIEW_LISTING'
    if target_type == 'promotion':
        if event_type == 'VIEW': log_event = 'VIEW_PROMO'
        elif event_type == 'CLICK_DETAILS': log_event = 'CLICK_PROMO'
    
    if event_type == 'WHATSAPP': log_event = 'CLICK_WHATSAPP'
    elif event_type == 'CALL': log_event = 'CLICK_CALL'

    # حفظ السجل
    with transaction.atomic():
        log = AnalyticsLog(event_type=log_event, ip_address=ip)
        if request.user.is_authenticated: 
            log.user = request.user
        
        if target_type == 'listing':
            listing = get_object_or_404(Listing, id=target_id)
            log.listing = listing
            # تحديث العدادات باستخدام F expressions (أسرع وأكثر أماناً)
            if event_type == 'VIEW': Listing.objects.filter(id=target_id).update(views_count=F('views_count') + 1)
            elif event_type == 'WHATSAPP': Listing.objects.filter(id=target_id).update(whatsapp_clicks=F('whatsapp_clicks') + 1)
            elif event_type == 'CALL': Listing.objects.filter(id=target_id).update(call_clicks=F('call_clicks') + 1)

        elif target_type == 'promotion':
            promo = get_object_or_404(Promotion, id=target_id)
            log.promotion = promo
            if event_type == 'VIEW': Promotion.objects.filter(id=target_id).update(views_count=F('views_count') + 1)
            elif event_type == 'CLICK_DETAILS': Promotion.objects.filter(id=target_id).update(clicks_count=F('clicks_count') + 1)
            elif event_type == 'WHATSAPP': Promotion.objects.filter(id=target_id).update(whatsapp_clicks=F('whatsapp_clicks') + 1)
            elif event_type == 'CALL': Promotion.objects.filter(id=target_id).update(call_clicks=F('call_clicks') + 1)

        log.save()
    
    return Response({'status': 'tracked'})

# --- لوحة تحكم الأدمن (Dashboard) ---
@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_dashboard_stats(request):
    # 1. إحصائيات عامة
    total_listings = Listing.objects.count()
    total_users = User.objects.count()
    total_views = Listing.objects.aggregate(Sum('views_count'))['views_count__sum'] or 0
    
    # 2. القوائم الأكثر تفاعلاً
    top_viewed_listings = Listing.objects.order_by('-views_count')[:5]
    top_contacted_listings = Listing.objects.order_by('-whatsapp_clicks')[:5]
    top_promos = Promotion.objects.order_by('-clicks_count')[:5]
    
    return Response({
        'stats': {
            'total_listings': total_listings,
            'total_users': total_users,
            'total_views': total_views,
        },
        'top_viewed_listings': ListingSerializer(top_viewed_listings, many=True).data,
        'top_contacted_listings': ListingSerializer(top_contacted_listings, many=True).data,
        'top_promos': PromotionSerializer(top_promos, many=True).data
    })