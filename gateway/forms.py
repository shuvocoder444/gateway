from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError


User = get_user_model()


class GatewayAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label='Username',
        widget=forms.TextInput(attrs={
            'autofocus': True,
            'autocomplete': 'username',
            'placeholder': 'Your username',
            'class': 'auth-input',
        }),
    )
    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'placeholder': 'Your password',
            'class': 'auth-input',
        }),
    )


class MerchantRegistrationForm(UserCreationForm):
    business_name = forms.CharField(
        max_length=255,
        label='Business name',
        widget=forms.TextInput(attrs={
            'autocomplete': 'organization',
            'placeholder': 'Your company or shop name',
            'class': 'auth-input',
        }),
    )
    email = forms.EmailField(
        label='Work email',
        widget=forms.EmailInput(attrs={
            'autocomplete': 'email',
            'placeholder': 'you@business.com',
            'class': 'auth-input',
        }),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')
        widgets = {
            'username': forms.TextInput(attrs={
                'autocomplete': 'username',
                'placeholder': 'Choose a username',
                'class': 'auth-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('password1', 'password2'):
            self.fields[field_name].widget.attrs.update({
                'class': 'auth-input',
                'autocomplete': 'new-password',
            })

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class PaymentQRCodeUploadForm(forms.Form):
    qr_code = forms.ImageField()

    def clean_qr_code(self):
        image = self.cleaned_data['qr_code']
        if image.size > 5 * 1024 * 1024:
            raise ValidationError('QR image must be 5 MB or smaller.')
        if getattr(image.image, 'format', '') not in {'PNG', 'JPEG', 'WEBP'}:
            raise ValidationError('Upload a PNG, JPG, or WebP QR image.')
        width, height = image.image.size
        if width > 5000 or height > 5000:
            raise ValidationError('QR image dimensions must be 5000 × 5000 pixels or less.')
        return image


class MerchantBrandingForm(forms.Form):
    checkout_display_name = forms.CharField(max_length=255, required=False)
    logo = forms.ImageField(required=False)
    checkout_copyright = forms.CharField(max_length=180, required=False)
    support_email = forms.EmailField(required=False)
    support_phone = forms.CharField(max_length=32, required=False)
    clear_logo = forms.BooleanField(required=False)

    def clean_logo(self):
        image = self.cleaned_data.get('logo')
        if image is None:
            return image
        if image.size > 5 * 1024 * 1024:
            raise ValidationError('Logo must be 5 MB or smaller.')
        if getattr(image.image, 'format', '') not in {'PNG', 'JPEG', 'WEBP'}:
            raise ValidationError('Upload a PNG, JPG, or WebP logo.')
        width, height = image.image.size
        if width > 3000 or height > 3000:
            raise ValidationError('Logo dimensions must be 3000 × 3000 pixels or less.')
        return image
