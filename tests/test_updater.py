from __future__ import annotations

import pytest

from citiesai.updater import (
    UpdateCheckResult,
    check_for_update,
    clear_update_cache,
    compare_versions,
    find_installer_asset,
    normalize_release_tag,
    parse_version,
)


def test_parse_version() -> None:
    assert parse_version("0.6.1") == (0, 6, 1)
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.0.0-beta") == (1, 0, 0)


def test_compare_versions() -> None:
    assert compare_versions("0.6.0", "0.6.1") < 0
    assert compare_versions("0.6.1", "0.6.1") == 0
    assert compare_versions("0.7.0", "0.6.9") > 0


def test_compare_versions_double_digit_minor() -> None:
    assert compare_versions("0.6.2", "0.10.0") < 0
    assert compare_versions("0.6.10", "0.6.9") > 0


def test_validate_download_url_rejects_unknown_host() -> None:
    from citiesai.updater import _validate_download_url

    with pytest.raises(ValueError, match="not allowed"):
        _validate_download_url("https://evil.example/setup.exe")


def test_normalize_release_tag() -> None:
    assert normalize_release_tag("v0.6.1") == "0.6.1"


def test_find_installer_asset() -> None:
    release = {
        "assets": [
            {"name": "checksums.txt", "browser_download_url": "https://example.com/a"},
            {"name": "CitiesAI-Setup-0.6.2.exe", "browser_download_url": "https://example.com/setup"},
        ]
    }
    asset = find_installer_asset(release)
    assert asset is not None
    assert asset["name"] == "CitiesAI-Setup-0.6.2.exe"


def test_check_for_update_newer_release(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_update_cache()
    release = {
        "tag_name": "v0.8.0",
        "html_url": "https://github.com/XharvaK/CitiesAI/releases/tag/v0.8.0",
        "published_at": "2026-07-05T12:00:00Z",
        "body": "Beta release",
        "assets": [
            {
                "name": "CitiesAI-Setup-0.8.0.exe",
                "browser_download_url": "https://github.com/XharvaK/CitiesAI/releases/download/v0.8.0/CitiesAI-Setup-0.8.0.exe",
                "size": 12345,
            }
        ],
    }

    monkeypatch.setattr("citiesai.updater._fetch_latest_release", lambda **_: (release, None))
    monkeypatch.setattr("citiesai.updater._record_check_time", lambda: "2026-07-05T12:00:00Z")
    monkeypatch.setattr("citiesai.updater.__version__", "0.6.1", raising=False)

    result = check_for_update(force=True)
    assert result.ok is True
    assert result.latest_version == "0.8.0"
    assert result.update_available is True
    assert result.installer_name == "CitiesAI-Setup-0.8.0.exe"


def test_check_for_update_dismissed_version(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    clear_update_cache()
    from citiesai import config as config_mod

    config_dir = tmp_path / "CitiesAI"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    config_file.write_text('[updates]\ndismissed_version = "0.8.0"\n', encoding="utf-8")
    monkeypatch.setattr(config_mod, "config_path", lambda: config_file)

    release = {
        "tag_name": "v0.8.0",
        "html_url": "https://github.com/XharvaK/CitiesAI/releases/tag/v0.8.0",
        "assets": [
            {
                "name": "CitiesAI-Setup-0.8.0.exe",
                "browser_download_url": "https://example.com/setup.exe",
                "size": 100,
            }
        ],
    }
    monkeypatch.setattr("citiesai.updater._fetch_latest_release", lambda **_: (release, None))
    monkeypatch.setattr("citiesai.updater._record_check_time", lambda: "2026-07-05T12:00:00Z")
    monkeypatch.setattr("citiesai.updater.__version__", "0.6.1", raising=False)

    result = check_for_update(force=True)
    assert result.update_available is False


def test_fetch_latest_tag_via_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai import updater as updater_mod

    class FakeResponse:
        def __init__(self, url: str) -> None:
            self._url = url

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def geturl(self) -> str:
            return self._url

    def fake_open(request: object, timeout: float = 20.0) -> FakeResponse:
        return FakeResponse("https://github.com/XharvaK/CitiesAI/releases/tag/v0.6.1")

    monkeypatch.setattr(updater_mod.urllib.request, "urlopen", fake_open)
    assert updater_mod._fetch_latest_tag_via_redirect() == "v0.6.1"


def test_check_for_update_api_403_uses_redirect_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_update_cache()
    from citiesai import updater as updater_mod

    def fake_fetch_latest_release(*, timeout: float = 20.0) -> tuple[dict | None, str | None]:
        return updater_mod._minimal_release_from_tag("v0.6.1"), "GitHub API rate limit reached."

    monkeypatch.setattr(updater_mod, "_fetch_latest_release", fake_fetch_latest_release)
    monkeypatch.setattr(updater_mod, "_record_check_time", lambda: "2026-07-05T12:00:00Z")
    monkeypatch.setattr(updater_mod, "__version__", "0.6.1", raising=False)

    result = check_for_update(force=True)
    assert result.ok is True
    assert result.update_available is False
    assert result.latest_version == "0.6.1"
    assert "No updates available" in (result.status_message or "")


def test_status_message_when_ahead_of_github() -> None:
    from citiesai.updater import _status_message

    msg = _status_message(current="0.7.0", latest="0.6.2", update_available=False)
    assert msg == "No updates available"


def test_status_message_up_to_date_is_short() -> None:
    from citiesai.updater import _status_message

    assert _status_message(current="0.8.0", latest="0.8.0", update_available=False) == (
        "No updates available"
    )
    assert "you're on" not in _status_message(
        current="0.8.0", latest="0.8.0", update_available=False
    ).lower()
    assert "—" not in _status_message(current="0.8.0", latest="0.8.0", update_available=False)


def test_api_update_check(monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai.gui.api import api_update_check

    sample = UpdateCheckResult(
        ok=True,
        current_version="0.6.1",
        latest_version="0.6.1",
        update_available=False,
        checked_at="2026-07-05T12:00:00Z",
    )
    monkeypatch.setattr("citiesai.gui.api.check_for_update", lambda *, force=False: sample)
    payload = api_update_check(force=True)
    assert payload["ok"] is True
    assert payload["current_version"] == "0.6.1"
    assert payload["update_available"] is False
