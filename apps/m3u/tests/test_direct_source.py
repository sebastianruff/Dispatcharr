"""Resolve provider stream URLs for expose_direct_source opt-in."""

from django.test import SimpleTestCase, TestCase

from apps.channels.models import Stream
from apps.m3u.direct_source import (
    account_exposes_direct_source,
    resolve_live_provider_url,
    resolve_vod_provider_url,
    stored_provider_url,
)
from apps.m3u.models import M3UAccount
from apps.vod.models import Episode, M3UEpisodeRelation, M3UMovieRelation, Movie, Series


class AccountExposesDirectSourceTests(SimpleTestCase):
    def test_default_is_false(self):
        self.assertFalse(account_exposes_direct_source(None))
        self.assertFalse(account_exposes_direct_source({}))
        self.assertFalse(account_exposes_direct_source({"expose_direct_source": False}))

    def test_true_opt_in(self):
        self.assertTrue(account_exposes_direct_source({"expose_direct_source": True}))


class StoredProviderUrlTests(SimpleTestCase):
    def test_metadata_urls_are_not_playback_sources(self):
        self.assertEqual(stored_provider_url({
            "url_website": "https://example.test/program",
            "url_subtitle": "https://example.test/subtitles.xml",
        }), "")

    def test_malformed_url_falls_through_to_valid_video(self):
        for invalid in ("http://[broken", "https://example.test/a\n#EXTINF:-1,b"):
            with self.subTest(invalid=invalid):
                self.assertEqual(stored_provider_url({
                    "direct_source": invalid,
                    "url_video_hd": "https://example.test/video.mp4",
                }), "https://example.test/video.mp4")

    def test_prefers_direct_source_then_url_video_then_url(self):
        self.assertEqual(
            stored_provider_url(
                {
                    "direct_source": "https://p.example/d.ts",
                    "url_video": "https://p.example/v.ts",
                    "url": "https://p.example/u.ts",
                }
            ),
            "https://p.example/d.ts",
        )
        self.assertEqual(
            stored_provider_url(
                {
                    "url_video": "https://p.example/v.ts",
                    "url": "https://p.example/u.ts",
                }
            ),
            "https://p.example/v.ts",
        )
        self.assertEqual(
            stored_provider_url({"url": "https://p.example/u.ts"}),
            "https://p.example/u.ts",
        )

    def test_quality_variant_after_named_keys(self):
        self.assertEqual(
            stored_provider_url({"url_hd": "https://p.example/hd.ts"}),
            "https://p.example/hd.ts",
        )

    def test_rejects_empty_and_partial_urls(self):
        self.assertEqual(stored_provider_url({"direct_source": ""}), "")
        self.assertEqual(stored_provider_url({"url": "/live/1.ts"}), "")
        self.assertEqual(stored_provider_url({"url": "http://"}), "")
        self.assertEqual(stored_provider_url({"url": None}), "")

    def test_reads_nested_basic_data(self):
        self.assertEqual(
            stored_provider_url(
                {"basic_data": {"direct_source": "https://p.example/d.ts"}}
            ),
            "https://p.example/d.ts",
        )


class ResolveLiveProviderUrlTests(TestCase):
    def test_uses_stored_stream_url_for_std_account(self):
        account = M3UAccount.objects.create(
            name="STD direct",
            account_type=M3UAccount.Types.STADNARD,
            server_url="https://list.example/list.m3u",
            custom_properties={"expose_direct_source": True},
        )
        stream = Stream.objects.create(
            name="STD",
            m3u_account=account,
            url="https://provider.example/stream/abc",
        )

        self.assertEqual(
            resolve_live_provider_url(stream, account),
            "https://provider.example/stream/abc",
        )

    def test_derives_xc_url_from_stream_id_when_payload_empty(self):
        account = M3UAccount.objects.create(
            name="XC derive",
            account_type=M3UAccount.Types.XC,
            server_url="https://myserver.fun/server1/player_api.php",
            username="alice",
            password="secret",
            custom_properties={"expose_direct_source": True},
        )
        stream = Stream.objects.create(
            name="Live",
            m3u_account=account,
            stream_id=12345,
            url="",
        )

        self.assertEqual(
            resolve_live_provider_url(stream, account),
            "https://myserver.fun/server1/live/alice/secret/12345.ts",
        )

    def test_prefers_payload_over_derived_xc_url(self):
        account = M3UAccount.objects.create(
            name="XC stored",
            account_type=M3UAccount.Types.XC,
            server_url="https://myserver.fun/server1",
            username="alice",
            password="secret",
            custom_properties={"expose_direct_source": True},
        )
        stream = Stream.objects.create(
            name="Live",
            m3u_account=account,
            stream_id=12345,
            custom_properties={"direct_source": "https://cdn.example/live.ts"},
        )

        self.assertEqual(
            resolve_live_provider_url(stream, account),
            "https://cdn.example/live.ts",
        )

    def test_unresolvable_returns_empty(self):
        account = M3UAccount.objects.create(
            name="XC empty",
            account_type=M3UAccount.Types.XC,
            server_url="https://myserver.fun",
            username="alice",
            password="secret",
            custom_properties={"expose_direct_source": True},
        )
        stream = Stream.objects.create(
            name="Live",
            m3u_account=account,
            url="/relative.ts",
        )

        self.assertEqual(resolve_live_provider_url(stream, account), "")


class ResolveVodProviderUrlTests(TestCase):
    def setUp(self):
        self.account = M3UAccount.objects.create(
            name="VOD XC",
            account_type=M3UAccount.Types.XC,
            server_url="https://myserver.fun/server1",
            username="alice",
            password="secret",
            custom_properties={"expose_direct_source": True},
        )

    def test_movie_prefers_basic_data_then_derives(self):
        movie = Movie.objects.create(name="Stored Movie")
        stored = M3UMovieRelation.objects.create(
            m3u_account=self.account,
            movie=movie,
            stream_id="999",
            container_extension="mkv",
            custom_properties={"basic_data": {"url": "https://cdn.example/movie.mkv"}},
        )
        self.assertEqual(
            resolve_vod_provider_url(stored, "movie"),
            "https://cdn.example/movie.mkv",
        )

        derived_movie = Movie.objects.create(name="Derived Movie")
        derived = M3UMovieRelation.objects.create(
            m3u_account=self.account,
            movie=derived_movie,
            stream_id="1000",
            container_extension="mkv",
        )
        self.assertEqual(
            resolve_vod_provider_url(derived, "movie"),
            "https://myserver.fun/server1/movie/alice/secret/1000.mkv",
        )

    def test_episode_derives_or_stays_empty(self):
        series = Series.objects.create(name="Show")
        episode = Episode.objects.create(
            series=series, name="Pilot", season_number=1, episode_number=1
        )
        with_id = M3UEpisodeRelation.objects.create(
            m3u_account=self.account,
            episode=episode,
            stream_id="888",
            container_extension="mp4",
        )
        self.assertEqual(
            resolve_vod_provider_url(with_id, "series"),
            "https://myserver.fun/server1/series/alice/secret/888.mp4",
        )

        other = Episode.objects.create(
            series=series, name="No ID", season_number=1, episode_number=2
        )
        no_id = M3UEpisodeRelation.objects.create(
            m3u_account=self.account,
            episode=other,
            stream_id="",
        )
        self.assertEqual(resolve_vod_provider_url(no_id, "series"), "")
