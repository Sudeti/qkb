from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import UserProfile

User = get_user_model()


class SignUpForm(UserCreationForm):
    """Enhanced signup form with email and terms"""
    
    email = forms.EmailField(
        max_length=254,
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email Address',
            'autofocus': True
        })
    )
    
    agree_terms = forms.BooleanField(
        required=True,
        error_messages={
            'required': 'You must agree to the terms and conditions.'
        },
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    institution = forms.CharField(
        max_length=300,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Institution'
        })
    )
    
    position = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Position or Role'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customize widget attributes for inherited fields
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Username'
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm Password'
        })
    
    class Meta:
        model = User
        fields = ('email', 'username', 'password1', 'password2', 'agree_terms', 'institution', 'position')
    
    def clean_email(self):
        """Ensure email is unique and lowercase"""
        email = self.cleaned_data.get('email', '').lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError('This email address is already registered.')
        return email
    
    def clean_username(self):
        """Strip whitespace and let Django's UserCreationForm handle uniqueness"""
        # Get and strip username
        username = self.cleaned_data.get('username', '')
        if isinstance(username, str):
            username = username.strip()
        
        if not username:
            raise ValidationError('Username is required.')
        
        # Check uniqueness explicitly (Django's parent method does this too, but be explicit)
        if User.objects.filter(username=username).exists():
            raise ValidationError('This username is already taken.')
        
        return username


class LoginForm(AuthenticationForm):
    """Custom login form with Bootstrap styling"""
    username = forms.CharField(
        label='Username',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username',
            'autofocus': True
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )
    
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class ResendVerificationForm(forms.Form):
    """Form to resend verification email"""
    email = forms.EmailField(
        max_length=254,
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email Address'
        })
    )


class ProfileUpdateForm(forms.ModelForm):
    """Form to update user profile"""
    first_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    institution = forms.CharField(
        max_length=300,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    position = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    bio = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4})
    )
    
    class Meta:
        model = UserProfile
        fields = ['first_name', 'last_name', 'phone', 'institution', 'position', 'bio', 'avatar']
        widgets = {
            'avatar': forms.FileInput(attrs={'class': 'form-control'})
        }
