from rest_framework import permissions

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    سماح بالقراءة للجميع، ولكن التعديل والحذف لصاحب العقار (أو الأدمن) فقط.
    """
    def has_object_permission(self, request, view, obj):
        # القراءة مسموحة للكل (GET, HEAD, OPTIONS)
        if request.method in permissions.SAFE_METHODS:
            return True

        # الكتابة مسموحة فقط لو المستخدم هو الـ agent المسجل للعقار أو هو أدمن
        return obj.agent == request.user or request.user.is_staff