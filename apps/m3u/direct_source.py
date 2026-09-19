"""Opt-in provider URL exposure for XC `direct_source` and M3U output."""

from __future__ import annotations

from urllib.parse import urlparse

from core.utils import custom_properties_as_dict

EXPOSE_DIRECT_SOURCE_KEY = "expose_direct_source"

PROVIDER_VIDEO_URL_KEYS = (
    "direct_source",
    "url_video",
    "url_video_hd",
    "url_video_low",
    "url",
    "url_hd",
    "url_sd",
    "url_fhd",
    "url_uhd",
    "url_4k",
    "url_1080p",
    "url_720p",
)

_ABSOLUTE_SCHEMES = {
    "http",
    "https",
    "rtmp",
    "rtmps",
    "rtsp",
    "rtsps",
    "udp",
    "rtp",
}


def account_exposes_direct_source(account_or_props) -> bool:
    """Return True only when the account explicitly opted in."""
    if account_or_props is None:
        return False
    if isinstance(account_or_props, dict):
        props = custom_properties_as_dict(account_or_props)
    else:
        props = custom_properties_as_dict(
            getattr(account_or_props, "custom_properties", None)
        )
    return props.get(EXPOSE_DIRECT_SOURCE_KEY) is True


def any_account_exposes_direct_source() -> bool:
    from apps.m3u.models import M3UAccount

    return M3UAccount.objects.filter(
        custom_properties__expose_direct_source=True, is_active=True
    ).exists()


def exposing_accounts_by_id():
    from apps.m3u.models import M3UAccount

    return {
        account.id: account
        for account in M3UAccount.objects.filter(
            custom_properties__expose_direct_source=True, is_active=True
        )
    }


def is_complete_provider_url(value) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value:
        return False
    if any(char in value for char in "\r\n\x00"):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme.lower() in _ABSOLUTE_SCHEMES and bool(parsed.netloc)


def stored_provider_url(payload) -> str:
    """Return a complete URL from a stored provider payload, or ``""``."""
    if not isinstance(payload, dict):
        return ""
    found = _url_from_mapping(payload)
    if found:
        return found
    nested = payload.get("basic_data")
    if isinstance(nested, dict):
        return _url_from_mapping(nested)
    return ""


def _url_from_mapping(mapping: dict) -> str:
    for key in PROVIDER_VIDEO_URL_KEYS:
        candidate = mapping.get(key)
        if is_complete_provider_url(candidate):
            return candidate.strip()
    return ""


def derived_xc_playback_url(account, content_path, stream_id, extension) -> str:
    if not account or getattr(account, "account_type", None) != "XC":
        return ""
    if not stream_id:
        return ""
    try:
        from apps.m3u.credentials import (
            build_xc_playback_url,
            get_transformed_credentials,
        )

        creds = getattr(account, "_cached_transformed_creds", None)
        if creds is None:
            creds = get_transformed_credentials(account)
            try:
                account._cached_transformed_creds = creds
            except Exception:
                pass
        server_url, username, password = creds
        if not (server_url and username and password):
            return ""
        url = build_xc_playback_url(
            server_url,
            username,
            password,
            content_path=content_path,
            stream_id=str(stream_id),
            extension=extension or "mp4",
        )
        return url if is_complete_provider_url(url) else ""
    except Exception:
        return ""


def resolve_live_provider_url(stream, account) -> str:
    """Provider URL for a live stream. Never raises; returns ``""`` if unknown."""
    try:
        stored = stored_provider_url(getattr(stream, "custom_properties", None) or {})
        if stored:
            return stored
        stream_url = getattr(stream, "url", None)
        if is_complete_provider_url(stream_url):
            return stream_url.strip()
        stream_id = getattr(stream, "stream_id", None)
        return derived_xc_playback_url(account, "live", stream_id, "ts")
    except Exception:
        return ""


def resolve_vod_provider_url(relation, content_path: str) -> str:
    """Provider URL for a movie or episode relation."""
    try:
        stored = stored_provider_url(getattr(relation, "custom_properties", None) or {})
        if stored:
            return stored
        get_url = getattr(relation, "get_stream_url", None)
        if callable(get_url):
            url = get_url()
            if is_complete_provider_url(url):
                return url.strip()
        account = getattr(relation, "m3u_account", None)
        return derived_xc_playback_url(
            account,
            content_path,
            getattr(relation, "stream_id", None),
            getattr(relation, "container_extension", None) or "mp4",
        )
    except Exception:
        return ""


def resolve_vod_provider_url_from_parts(
    *,
    account,
    stored_payload,
    stream_id,
    container_extension,
    content_path,
) -> str:
    stored = stored_provider_url(stored_payload)
    if stored:
        return stored
    return derived_xc_playback_url(
        account, content_path, stream_id, container_extension or "mp4"
    )
