"""Opt-in expose_direct_source for XC catalogs and M3U output."""

from uuid import uuid4

from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from apps.accounts.models import User
from apps.channels.models import Channel, ChannelGroup, Stream
from apps.m3u.models import M3UAccount
from apps.output.views import (
    generate_m3u,
    xc_get_live_streams,
    xc_get_series_info,
    xc_get_vod_info,
    xc_get_vod_streams,
)
from apps.vod.models import (
    Episode,
    M3UEpisodeRelation,
    M3UMovieRelation,
    M3USeriesRelation,
    Movie,
    Series,
)


class ExposeDirectSourceXcTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username=f"xc-ds-{uuid4().hex[:8]}",
            password="pass",
            user_level=10,
            custom_properties={"xc_password": "xcpass"},
        )
        self.request = self.factory.get("/player_api.php")
        self.group = ChannelGroup.objects.create(name=f"Group {uuid4().hex[:8]}")

    def tearDown(self):
        cache.clear()

    def _account(self, name, *, expose=False, **kwargs):
        props = dict(kwargs.pop("custom_properties", {}) or {})
        if expose:
            props["expose_direct_source"] = True
        return M3UAccount.objects.create(
            name=name,
            server_url=kwargs.pop("server_url", "https://xc.example.com"),
            username=kwargs.pop("username", "alice"),
            password=kwargs.pop("password", "secret"),
            account_type=M3UAccount.Types.XC,
            is_active=True,
            custom_properties=props,
            **kwargs,
        )

    def test_live_and_movies_empty_when_not_opted_in(self):
        account = self._account(f"plain-{uuid4().hex[:6]}")
        channel = Channel.objects.create(
            name="Live",
            channel_number=1,
            channel_group=self.group,
            user_level=0,
        )
        stream = Stream.objects.create(
            name="Live",
            m3u_account=account,
            stream_id=11,
            url="https://xc.example.com/live/alice/secret/11.ts",
        )
        channel.streams.add(stream)
        movie = Movie.objects.create(name="Movie")
        M3UMovieRelation.objects.create(
            m3u_account=account,
            movie=movie,
            stream_id="21",
            last_advanced_refresh=timezone.now(),
            custom_properties={"detailed_fetched": True},
        )

        live = xc_get_live_streams(self.request, self.user)[0]
        vod = xc_get_vod_streams(self.request, self.user)[0]
        info = xc_get_vod_info(self.request, self.user, str(movie.id))

        self.assertEqual(live["direct_source"], "")
        self.assertEqual(vod["direct_source"], "")
        self.assertEqual(info["movie_data"]["direct_source"], "")

    def test_live_and_movies_use_provider_url_when_opted_in(self):
        account = self._account(f"expose-{uuid4().hex[:6]}", expose=True)
        channel = Channel.objects.create(
            name="Live Direct",
            channel_number=2,
            channel_group=self.group,
            user_level=0,
        )
        stream = Stream.objects.create(
            name="Live Direct",
            m3u_account=account,
            stream_id=12,
        )
        channel.streams.add(stream)
        movie = Movie.objects.create(name="Direct Movie")
        M3UMovieRelation.objects.create(
            m3u_account=account,
            movie=movie,
            stream_id="22",
            container_extension="mp4",
            last_advanced_refresh=timezone.now(),
            custom_properties={"detailed_fetched": True},
        )

        live = xc_get_live_streams(self.request, self.user)[0]
        vod = xc_get_vod_streams(self.request, self.user)[0]
        info = xc_get_vod_info(self.request, self.user, str(movie.id))

        self.assertEqual(
            live["direct_source"],
            "https://xc.example.com/live/alice/secret/12.ts",
        )
        self.assertEqual(
            vod["direct_source"],
            "https://xc.example.com/movie/alice/secret/22.mp4",
        )
        self.assertEqual(
            info["movie_data"]["direct_source"],
            "https://xc.example.com/movie/alice/secret/22.mp4",
        )

    def test_unresolvable_live_url_stays_empty(self):
        account = self._account(f"bad-{uuid4().hex[:6]}", expose=True)
        channel = Channel.objects.create(
            name="Broken",
            channel_number=3,
            channel_group=self.group,
            user_level=0,
        )
        stream = Stream.objects.create(
            name="Broken",
            m3u_account=account,
            url="/not-a-full-url.ts",
        )
        channel.streams.add(stream)

        live = xc_get_live_streams(self.request, self.user)[0]
        self.assertEqual(live["direct_source"], "")

    def test_episode_direct_source_when_opted_in(self):
        account = self._account(f"series-{uuid4().hex[:6]}", expose=True)
        series = Series.objects.create(name="Show")
        series_rel = M3USeriesRelation.objects.create(
            m3u_account=account,
            series=series,
            external_series_id="100",
            last_episode_refresh=timezone.now(),
            custom_properties={"episodes_fetched": True, "detailed_fetched": True},
        )
        episode = Episode.objects.create(
            series=series, name="Pilot", season_number=1, episode_number=1
        )
        M3UEpisodeRelation.objects.create(
            m3u_account=account,
            episode=episode,
            series_relation=series_rel,
            stream_id="888",
            container_extension="mp4",
        )

        info = xc_get_series_info(self.request, self.user, series_rel.id)
        ep = info["episodes"][1][0]
        self.assertEqual(
            ep["direct_source"],
            "https://xc.example.com/series/alice/secret/888.mp4",
        )


class ExposeDirectSourceM3UTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.group = ChannelGroup.objects.create(name=f"M3U {uuid4().hex[:8]}")

    def tearDown(self):
        cache.clear()

    def _playlist(self):
        request = self.factory.get("/output/m3u")
        with patch("apps.output.views.log_system_event"):
            response = generate_m3u(request, profile_name=None, user=None)
        return response.content.decode()

    def test_opted_in_account_emits_provider_url_others_keep_dispatcharr(self):
        exposing = M3UAccount.objects.create(
            name=f"expose-{uuid4().hex[:6]}",
            account_type=M3UAccount.Types.STADNARD,
            custom_properties={"expose_direct_source": True},
        )
        other = M3UAccount.objects.create(
            name=f"other-{uuid4().hex[:6]}",
            account_type=M3UAccount.Types.STADNARD,
        )
        direct_ch = Channel.objects.create(
            name="Direct Ch",
            channel_number=1,
            channel_group=self.group,
        )
        proxy_ch = Channel.objects.create(
            name="Proxy Ch",
            channel_number=2,
            channel_group=self.group,
        )
        direct_stream = Stream.objects.create(
            name="Direct",
            m3u_account=exposing,
            url="https://provider.example/live/direct.ts",
        )
        proxy_stream = Stream.objects.create(
            name="Proxy",
            m3u_account=other,
            url="https://provider.example/live/hidden.ts",
        )
        direct_ch.streams.add(direct_stream)
        proxy_ch.streams.add(proxy_stream)

        content = self._playlist()

        self.assertIn("https://provider.example/live/direct.ts", content)
        self.assertNotIn("https://provider.example/live/hidden.ts", content)
        self.assertIn(f"/proxy/ts/stream/{proxy_ch.uuid}", content)
        self.assertNotIn(f"/proxy/ts/stream/{direct_ch.uuid}", content)

    def test_not_opted_in_matches_dispatcharr_urls_only(self):
        account = M3UAccount.objects.create(
            name=f"plain-{uuid4().hex[:6]}",
            account_type=M3UAccount.Types.STADNARD,
        )
        channel = Channel.objects.create(
            name="Plain Ch",
            channel_number=1,
            channel_group=self.group,
        )
        stream = Stream.objects.create(
            name="Plain",
            m3u_account=account,
            url="https://provider.example/live/plain.ts",
        )
        channel.streams.add(stream)

        content = self._playlist()

        self.assertNotIn("https://provider.example/live/plain.ts", content)
        self.assertIn(f"/proxy/ts/stream/{channel.uuid}", content)
        self.assertNotIn(reverse("output:m3u_endpoint"), content)

    def test_unresolvable_url_falls_back_to_proxy(self):
        account = M3UAccount.objects.create(
            name=f"bad-{uuid4().hex[:6]}",
            account_type=M3UAccount.Types.STADNARD,
            custom_properties={"expose_direct_source": True},
        )
        channel = Channel.objects.create(
            name="Bad Ch",
            channel_number=1,
            channel_group=self.group,
        )
        stream = Stream.objects.create(
            name="Bad",
            m3u_account=account,
            url="/relative/path.ts",
        )
        channel.streams.add(stream)

        content = self._playlist()
        self.assertIn(f"/proxy/ts/stream/{channel.uuid}", content)
        self.assertNotIn("/relative/path.ts", content)

    def test_regression_byte_for_byte_when_not_opted_in(self):
        account1 = M3UAccount.objects.create(
            name=f"none-{uuid4().hex[:6]}",
            account_type=M3UAccount.Types.STADNARD,
        )
        ch1 = Channel.objects.create(
            name="Ch1",
            channel_number=1,
            channel_group=self.group,
        )
        st1 = Stream.objects.create(
            name="S1",
            m3u_account=account1,
            url="https://p.example/1.ts",
        )
        ch1.streams.add(st1)

        out1 = self._playlist()

        cache.clear()
        account1.custom_properties = {"expose_direct_source": False}
        account1.save()

        out2 = self._playlist()
        self.assertEqual(out1, out2)
