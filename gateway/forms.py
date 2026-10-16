from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm


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
