"""XC VOD ``added`` must reflect the provider timestamp when it is valid.

Providers declare ``added`` in their VOD list payload (stored as
``basic_data.added`` on the relation). ``get_vod_streams`` and
``get_vod_info`` must use it so clients that sort by "date added" reflect the
provider date; only a missing or invalid value falls back to the local
import time.
"""
from uuid import uuid4

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.m3u.models import M3UAccount
from apps.output.views import xc_get_vod_info, xc_get_vod_streams
from apps.vod.models import Movie, M3UMovieRelation


class XcVodAddedTimestampTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username=f"xc-{uuid4().hex[:8]}",
            password="pass",
            custom_properties={"xc_password": "xcpass"},
        )
        self.request = self.factory.get("/player_api.php")
        self.account = M3UAccount.objects.create(
            name=f"acct-{uuid4().hex[:6]}",
            server_url="http://example.com",
            is_active=True,
        )

    def _relation(self, **kwargs):
        movie = Movie.objects.create(name=f"Movie {uuid4().hex[:6]}")
        return M3UMovieRelation.objects.create(
            m3u_account=self.account,
            movie=movie,
            stream_id=f"stream-{uuid4().hex[:6]}",
            **kwargs,
        )

    def test_vod_streams_uses_provider_added(self):
        self._relation(custom_properties={"basic_data": {"added": "1600000000"}})

        stream = xc_get_vod_streams(self.request, self.user)[0]

        self.assertEqual(stream["added"], "1600000000")

    def test_vod_streams_falls_back_without_basic_data(self):
        relation = self._relation()

        stream = xc_get_vod_streams(self.request, self.user)[0]

        self.assertEqual(stream["added"], str(int(relation.created_at.timestamp())))

    def test_vod_streams_falls_back_on_invalid_added(self):
        relation = self._relation(custom_properties={"basic_data": {"added": "n/a"}})

        stream = xc_get_vod_streams(self.request, self.user)[0]

        self.assertEqual(stream["added"], str(int(relation.created_at.timestamp())))

    def test_vod_info_uses_provider_added(self):
        # detailed_fetched + a fresh advanced refresh keep the info endpoint
        # from trying to fetch provider metadata during the test.
        relation = self._relation(
            custom_properties={
                "basic_data": {"added": "1600000000"},
                "detailed_fetched": True,
            },
            last_advanced_refresh=timezone.now(),
        )

        info = xc_get_vod_info(self.request, self.user, relation.movie_id)

        self.assertEqual(info["movie_data"]["added"], "1600000000")
