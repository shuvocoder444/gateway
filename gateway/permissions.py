from rest_framework import permissions


class HasMerchantAPIKey(permissions.BasePermission):
    """
    Allows access only to requests with a valid, active Merchant API Key.
    """
    message = "Valid X-API-KEY required."

    def has_permission(self, request, view):
        return bool(
            getattr(request, 'merchant', None) and
            request.merchant.is_active
        )


class HasDeviceToken(permissions.BasePermission):
    """
    Allows access only to registered forwarder devices with a valid, active Device Token.
    """
    message = "Valid X-DEVICE-TOKEN required."

    def has_permission(self, request, view):
        return bool(
            getattr(request, 'device', None) and
            request.device.is_active and
            request.merchant and
            request.merchant.is_active
        )
