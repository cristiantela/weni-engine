import requests
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

from weni.storages import AvatarUserMediaStorage


class UserManager(BaseUserManager):
    def _create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("The given email must be set")
        if not username:
            raise ValueError("The given nick must be set")

        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_superuser", False)

        return self._create_user(email, username, password, **extra_fields)

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_staff", True)

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    first_name = models.CharField(_("first name"), max_length=30, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    email = models.EmailField(_("email"), unique=True, help_text=_("User's email."))

    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        help_text=_(
            "Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
        ),
        validators=[UnicodeUsernameValidator()],
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )

    photo = models.ImageField(
        _("photo user"), storage=AvatarUserMediaStorage(), null=True
    )

    language = models.CharField(
        verbose_name=_("Language"),
        max_length=64,
        choices=settings.LANGUAGES,
        default=settings.DEFAULT_LANGUAGE,
        help_text=_("The primary language used by this user"),
    )

    is_staff = models.BooleanField(_("staff status"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    joined_at = models.DateField(_("joined at"), auto_now_add=True)

    short_phone_prefix = models.IntegerField(
        verbose_name=_("Phone Prefix Country"),
        help_text=_("Phone prefix of the user"),
        null=True,
    )

    phone = models.BigIntegerField(
        verbose_name=_("Telephone Number"),
        help_text=_("Phone number of the user; include area code"),
        null=True,
    )

    objects = UserManager()

    @property
    def token_generator(self):
        return PasswordResetTokenGenerator()

    def check_password_reset_token(self, token):
        return self.token_generator.check_token(self, token)

    def send_change_password_email(self):
        if not settings.SEND_EMAILS:
            return False  # pragma: no cover
        context = {"name": self.first_name}
        send_mail(
            _("Password changed"),
            render_to_string("authentication/emails/change_password.txt"),
            None,
            [self.email],
            html_message=render_to_string(
                "authentication/emails/change_password.html", context
            ),
        )

    def send_request_flow_user_info(self):
        if not settings.SEND_REQUEST_FLOW:
            return False  # pragma: no cover
        requests.post(
            url=f"{settings.FLOWS_URL}api/v2/flow_starts.json",
            json={
                "flow": "cf0bca76-eeed-4d36-ad3e-4b80b06c6d21",
                "params": {
                    "first_name": self.first_name,
                    "last_name": self.last_name,
                    "email": self.email,
                    "language": self.language,
                    "short_phone_prefix": self.short_phone_prefix,
                    "phone": self.phone,
                },
                "urns": [f"mailto:{self.email}"],
            },
            headers={"Authorization": "Token 3a5987a13a9ce0960d1b4d25521f060a9c68026b"},
        )

    @property
    def photo_url(self):
        if self.photo and hasattr(self.photo, "url"):
            return self.photo.url
