from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsOwnerOrReadOnly(BasePermission):
    """Anyone may read a listing; only its seller may change or delete it.

    Two methods, because DRF asks two separate questions:

    * ``has_permission`` runs before the object is fetched and is the only
      check a POST (create) gets, since there is no object yet.
    * ``has_object_permission`` runs on retrieve/update/destroy, once the view
      has the row in hand.

    The web views enforce ownership by filtering the queryset to
    ``seller=request.user``, so a non-owner gets a 404 and learns nothing. The
    API answers 403 instead, which is fine here: listings are public to read,
    so confirming that one exists gives nothing away, and a clear 403 is much
    easier to debug than a 404 from a URL the client just read from a list.
    """

    message = 'Only the seller can change this listing.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.seller_id == request.user.pk
