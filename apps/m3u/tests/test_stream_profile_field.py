"""M3U account stream_profile round-trip through serializer."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from apps.channels.models import StreamProfile
from apps.m3u.models import M3UAccount
from apps.m3u.serializers import M3UAccountSerializer


class M3UAccountStreamProfileFieldTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="m3u_sp_admin",
            password="x",
            user_level=User.UserLevel.ADMIN,
        )
        self.profile = StreamProfile.objects.create(
            name="Direct", command="", parameters="", locked=True
        )
        self.account = M3UAccount.objects.create(
            name="Account with profile",
            server_url="http://example.test",
            account_type="STD",
        )
        self.factory = APIRequestFactory()

    def test_profile_id_is_serialized(self):
        self.account.stream_profile = self.profile
        self.account.save()
        request = self.factory.get("/api/m3u/accounts/")
        request.user = self.admin
        data = M3UAccountSerializer(
            self.account, context={"request": request}
        ).data
        self.assertEqual(data.get("stream_profile"), self.profile.id)

    def test_null_profile_serializes_as_null(self):
        request = self.factory.get("/api/m3u/accounts/")
        request.user = self.admin
        data = M3UAccountSerializer(
            self.account, context={"request": request}
        ).data
        self.assertIsNone(data.get("stream_profile"))
