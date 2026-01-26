from django.contrib.auth import get_user_model
from django.db.models import Q
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


def oidc_username_from_claims(claims):
    return (
        claims.get("email")
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
        user.first_name = claims.get("given_name", user.first_name)
        user.last_name = claims.get("family_name", user.last_name)
        user.email = claims.get("email", user.email)
        user.save(update_fields=["first_name", "last_name", "email"])
        return user
