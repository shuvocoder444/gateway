from rest_framework import authentication, exceptions
from .models import Merchant, Device


class MerchantAPIKeyAuthentication(authentication.BaseAuthentication):
    """
    Authenticates merchant API requests via X-API-KEY request header.
    Attaches merchant instance to `request.merchant` and `request.user`.
    """
    def authenticate(self, request):
        api_key = request.headers.get('X-API-KEY') or request.META.get('HTTP_X_API_KEY')
        if not api_key:
            return None

        try:
            merchant = Merchant.objects.get(api_key=api_key, is_active=True)
        except Merchant.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid or inactive API Key.')

        request.merchant = merchant
        # Return a dummy user or merchant representation and auth credentials
        return (merchant, api_key)

    def authenticate_header(self, request):
        return 'X-API-KEY'


class DeviceTokenAuthentication(authentication.BaseAuthentication):
    """
    Authenticates Android forwarder bridge via X-DEVICE-TOKEN header.
    Attaches device and device.merchant to request.
    """
    def authenticate(self, request):
        token = request.headers.get('X-DEVICE-TOKEN') or request.META.get('HTTP_X_DEVICE_TOKEN')
        if not token:
            return None

        try:
            device = Device.objects.select_related('merchant').get(
                device_token=token,
                is_active=True,
                merchant__is_active=True
            )
        except Device.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid or inactive Device Token.')

        request.device = device
        request.merchant = device.merchant
        return (device, token)

    def authenticate_header(self, request):
        return 'X-DEVICE-TOKEN'
