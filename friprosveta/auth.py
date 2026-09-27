from django.contrib.auth import get_user_model
from django.db.models import Q
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


def oidc_username_from_claims(email, claims=None):
    if claims is None and isinstance(email, dict):
        claims = email
        email = claims.get("email")

    if claims is None:
        claims = {}

    return (
        email
        or claims.get("email")
        or claims.get("upn")
        or claims.get("preferred_username")
        or claims.get("sub")
        or ""
    )


class URNIKOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def filter_users_by_claims(self, claims):
        User = get_user_model()
        email = claims.get("email")
        upn = claims.get("upn") or claims.get("preferred_username")
        subject = claims.get("sub")

        query = Q()
        if email:
            query |= Q(email__iexact=email) | Q(username__iexact=email)
        if upn:
            query |= Q(username__iexact=upn) | Q(email__iexact=upn)
        if subject:
            query |= Q(username__iexact=subject)

        return User.objects.filter(query) if query else User.objects.none()

    def update_user(self, user, claims):
        update_fields = []
        for claim, field in (
            ("given_name", "first_name"),
            ("family_name", "last_name"),
            ("email", "email"),
        ):
            value = claims.get(claim)
            if value:
                setattr(user, field, value)
                update_fields.append(field)
        if update_fields:
            user.save(update_fields=update_fields)
        return user
