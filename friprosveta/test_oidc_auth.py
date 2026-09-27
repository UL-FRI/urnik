from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from friprosveta.auth import URNIKOIDCAuthenticationBackend


class OIDCExistingUserTest(TestCase):
    @override_settings(
        OIDC_OP_AUTHORIZATION_ENDPOINT="https://idp.invalid/authorize",
        OIDC_OP_TOKEN_ENDPOINT="https://idp.invalid/token",
        OIDC_OP_USER_ENDPOINT="https://idp.invalid/userinfo",
        OIDC_OP_JWKS_ENDPOINT="https://idp.invalid/jwks",
        OIDC_RP_CLIENT_ID="test-client",
        OIDC_RP_CLIENT_SECRET="test-secret",
    )
    def test_callback_logs_in_existing_user_with_null_profile_claims(self):
        user = User.objects.create_user(
            username="user@fri.uni-lj.si", email="old@example.com"
        )
        response = self.client.get(reverse("oidc_authentication_init"))
        params = parse_qs(urlsplit(response["Location"]).query)
        claims = {"upn": user.username, "email": None, "given_name": None}

        with (
            patch.object(
                URNIKOIDCAuthenticationBackend,
                "get_token",
                return_value={"id_token": "test-id-token", "access_token": "test-access"},
            ),
            patch.object(
                URNIKOIDCAuthenticationBackend,
                "verify_token",
                return_value={"sub": "test-sub"},
            ),
            patch.object(
                URNIKOIDCAuthenticationBackend, "get_userinfo", return_value=claims
            ),
        ):
            response = self.client.get(
                reverse("oidc_authentication_callback"),
                {"code": "test-code", "state": params["state"][0]},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_null_profile_claims_do_not_break_login_or_erase_existing_values(self):
        user = User.objects.create_user(
            username="user@fri.uni-lj.si",
            email="old@example.com",
            first_name="Existing",
            last_name="Student",
        )
        claims = {
            "upn": user.username,
            "email": None,
            "given_name": None,
            "family_name": None,
        }
        backend = URNIKOIDCAuthenticationBackend()

        with patch.object(backend, "get_userinfo", return_value=claims):
            authenticated_user = backend.get_or_create_user(None, None, {})

        self.assertEqual(authenticated_user.pk, user.pk)
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")
        self.assertEqual(user.first_name, "Existing")
        self.assertEqual(user.last_name, "Student")

    def test_supplied_profile_claims_update_existing_user(self):
        user = User.objects.create_user(
            username="user@fri.uni-lj.si", email="old@example.com"
        )
        backend = URNIKOIDCAuthenticationBackend()

        backend.update_user(
            user,
            {
                "given_name": "Updated",
                "family_name": "Student",
                "email": "new@example.com",
            },
        )

        user.refresh_from_db()
        self.assertEqual(
            (user.first_name, user.last_name, user.email),
            ("Updated", "Student", "new@example.com"),
        )
