"""Direct stream profile selection acts as opt-in alongside custom_properties."""

from django.test import TestCase

from apps.channels.models import StreamProfile
from apps.m3u.direct_source import account_exposes_direct_source, any_account_exposes_direct_source
from apps.m3u.models import M3UAccount
from core.models import DIRECT_PROFILE_NAME


class DirectStreamProfileMigrationTests(TestCase):
    def test_direct_stream_profile_seeded_by_migration(self):
        profile = StreamProfile.objects.filter(
            name=DIRECT_PROFILE_NAME, locked=True
        ).first()
        self.assertIsNotNone(profile)
        self.assertTrue(profile.is_direct())
        self.assertFalse(profile.is_proxy())
        self.assertFalse(profile.is_redirect())


class DirectStreamProfileOptInTests(TestCase):
    def setUp(self):
        self.profile = StreamProfile.objects.filter(
            name=DIRECT_PROFILE_NAME, locked=True
        ).first()
        if self.profile is None:
            self.profile = StreamProfile.objects.create(
                name=DIRECT_PROFILE_NAME,
                command="",
                parameters="",
                locked=True,
                is_active=True,
            )

    def test_account_with_direct_profile_opts_in(self):
        account = M3UAccount.objects.create(
            name="direct account",
            account_type=M3UAccount.Types.XC,
            server_url="https://example.test",
            username="alice",
            password="secret",
            stream_profile=self.profile,
        )
        self.assertTrue(account_exposes_direct_source(account))
        self.assertTrue(any_account_exposes_direct_source())

    def test_account_with_non_direct_profile_stays_opted_out(self):
        ffmpeg = StreamProfile.objects.filter(name="ffmpeg", locked=True).first()
        if ffmpeg is None:
            ffmpeg = StreamProfile.objects.create(
                name="ffmpeg", command="ffmpeg", parameters="", locked=True
            )
        account = M3UAccount.objects.create(
            name="non direct account",
            account_type=M3UAccount.Types.XC,
            server_url="https://example.test",
            username="alice",
            password="secret",
            stream_profile=ffmpeg,
        )
        self.assertFalse(account_exposes_direct_source(account))

    def test_account_without_profile_stays_opted_out(self):
        account = M3UAccount.objects.create(
            name="default account",
            account_type=M3UAccount.Types.XC,
            server_url="https://example.test",
            username="alice",
            password="secret",
        )
        self.assertFalse(account_exposes_direct_source(account))
        self.assertFalse(any_account_exposes_direct_source())
