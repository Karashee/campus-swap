from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import (
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('login/', views.CampusLoginView.as_view(), name='login'),
    # POST only: Django 5+ removed GET logout, which is why the navbar uses a form.
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Password change
    path(
        'password/change/',
        auth_views.PasswordChangeView.as_view(
            template_name='registration/password_change_form.html',
            form_class=StyledPasswordChangeForm,
            # Django's default success_url is the un-namespaced name.
            success_url=reverse_lazy('accounts:password_change_done'),
        ),
        name='password_change',
    ),
    path(
        'password/change/done/',
        auth_views.PasswordChangeDoneView.as_view(
            template_name='registration/password_change_done.html'
        ),
        name='password_change_done',
    ),

    # Password reset (email goes to the console in development)
    path(
        'password/reset/',
        auth_views.PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            form_class=StyledPasswordResetForm,
            success_url=reverse_lazy('accounts:password_reset_done'),
        ),
        name='password_reset',
    ),
    path(
        'password/reset/sent/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='registration/password_reset_done.html'
        ),
        name='password_reset_done',
    ),
    path(
        'password/reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='registration/password_reset_confirm.html',
            form_class=StyledSetPasswordForm,
            success_url=reverse_lazy('accounts:password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'password/reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='registration/password_reset_complete.html'
        ),
        name='password_reset_complete',
    ),

    # Profiles
    path('profile/edit/', views.ProfileUpdateView.as_view(), name='profile_edit'),
    path('profile/<str:username>/', views.profile_detail, name='profile'),
]
