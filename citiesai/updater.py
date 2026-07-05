"""GitHub Releases update checker and installer launcher."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import config_dir, load_config
from .version import __version__

GITHUB_REPO = "XharvaK/CitiesAI"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases"
INSTALLER_PREFIX = "CitiesAI-Setup-"
INSTALLER_SUFFIX = ".exe"
CHECK_CACHE_HOURS = 6

_cache_lock = threading.Lock()
_cached_result: dict[str, Any] | None = None


@dataclass(frozen=True)
class UpdateCheckResult:
    ok: bool
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str = RELEASES_PAGE_URL
    download_url: str | None = None
    release_notes: str | None = None
    published_at: str | None = None
    installer_name: str | None = None
    installer_size: int | None = None
    error: str | None = None
    packaged: bool = False
    can_install: bool = False
    check_on_startup: bool = True
    dismissed_version: str | None = None
    checked_at: str | None = None
    from_cache: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "release_url": self.release_url,
            "download_url": self.download_url,
            "release_notes": self.release_notes,
            "published_at": self.published_at,
            "installer_name": self.installer_name,
            "installer_size": self.installer_size,
            "error": self.error,
            "packaged": self.packaged,
            "can_install": self.can_install,
            "check_on_startup": self.check_on_startup,
            "dismissed_version": self.dismissed_version,
            "checked_at": self.checked_at,
            "from_cache": self.from_cache,
        }


def is_packaged_build() -> bool:
    return bool(getattr(sys, "frozen", False))


def can_silent_install() -> bool:
    return is_packaged_build() and sys.platform == "win32"


def parse_version(version: str) -> tuple[int, ...]:
    cleaned = version.strip().lstrip("vV")
    parts: list[int] = []
    for piece in cleaned.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def compare_versions(current: str, latest: str) -> int:
    left = parse_version(current)
    right = parse_version(latest)
    width = max(len(left), len(right))
    left_padded = left + (0,) * (width - len(left))
    right_padded = right + (0,) * (width - len(right))
    if left_padded < right_padded:
        return -1
    if left_padded > right_padded:
        return 1
    return 0


def normalize_release_tag(tag: str) -> str:
    return tag.strip().lstrip("vV")


def find_installer_asset(release: dict[str, Any]) -> dict[str, Any] | None:
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        if name.startswith(INSTALLER_PREFIX) and name.endswith(INSTALLER_SUFFIX):
            return asset
    return None


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"CitiesAI/{__version__} (+https://github.com/{GITHUB_REPO})",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_json(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=_github_headers(), method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected GitHub response")
    return payload


def _parse_checked_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _should_use_cache(last_check_utc: str | None, *, force: bool) -> bool:
    if force:
        return False
    checked_at = _parse_checked_at(last_check_utc)
    if checked_at is None:
        return False
    return datetime.now(UTC) - checked_at < timedelta(hours=CHECK_CACHE_HOURS)


def _record_check_time() -> str:
    checked_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    cfg = load_config()
    cfg.update_last_check_utc = checked_at
    cfg.write()
    return checked_at


def _base_result(*, error: str | None = None) -> UpdateCheckResult:
    cfg = load_config()
    dismissed = cfg.update_dismissed_version or None
    return UpdateCheckResult(
        ok=error is None,
        current_version=__version__,
        release_url=RELEASES_PAGE_URL,
        error=error,
        packaged=is_packaged_build(),
        can_install=can_silent_install(),
        check_on_startup=cfg.check_updates_on_startup,
        dismissed_version=dismissed,
    )


def check_for_update(*, force: bool = False) -> UpdateCheckResult:
    cfg = load_config()
    dismissed = cfg.update_dismissed_version or None

    with _cache_lock:
        if not force and _cached_result is not None:
            cached = UpdateCheckResult(**_cached_result)
            if _should_use_cache(cached.checked_at, force=False):
                return UpdateCheckResult(
                    **{**cached.to_dict(), "from_cache": True, "check_on_startup": cfg.check_updates_on_startup}
                )

    if _should_use_cache(cfg.update_last_check_utc, force=force):
        with _cache_lock:
            if _cached_result is not None:
                cached = UpdateCheckResult(**_cached_result)
                return UpdateCheckResult(
                    **{**cached.to_dict(), "from_cache": True, "check_on_startup": cfg.check_updates_on_startup}
                )

    try:
        release = _fetch_json(RELEASES_LATEST_URL)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            result = _base_result(error="No GitHub release found yet.")
        else:
            result = _base_result(error=f"GitHub API returned {exc.code}.")
        _store_cache(result)
        return result
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        result = _base_result(error=f"Could not reach GitHub: {exc}")
        _store_cache(result)
        return result

    tag = normalize_release_tag(str(release.get("tag_name") or release.get("name") or ""))
    if not tag:
        result = _base_result(error="GitHub release is missing a version tag.")
        _store_cache(result)
        return result

    asset = find_installer_asset(release)
    download_url = str(asset.get("browser_download_url") or "") if asset else None
    installer_name = str(asset.get("name") or "") if asset else None
    installer_size = asset.get("size") if asset else None
    if isinstance(installer_size, int):
        pass
    else:
        installer_size = None

    update_available = compare_versions(__version__, tag) < 0
    if dismissed and dismissed == tag:
        update_available = False

    checked_at = _record_check_time()
    result = UpdateCheckResult(
        ok=True,
        current_version=__version__,
        latest_version=tag,
        update_available=update_available,
        release_url=str(release.get("html_url") or RELEASES_PAGE_URL),
        download_url=download_url or None,
        release_notes=str(release.get("body") or "") or None,
        published_at=str(release.get("published_at") or "") or None,
        installer_name=installer_name or None,
        installer_size=installer_size,
        packaged=is_packaged_build(),
        can_install=can_silent_install() and bool(download_url),
        check_on_startup=cfg.check_updates_on_startup,
        dismissed_version=dismissed,
        checked_at=checked_at,
    )
    _store_cache(result)
    return result


def _store_cache(result: UpdateCheckResult) -> None:
    payload = result.to_dict()
    payload["from_cache"] = False
    with _cache_lock:
        global _cached_result
        _cached_result = payload


def updates_dir() -> Path:
    path = config_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def download_installer(
    *,
    download_url: str,
    installer_name: str,
    expected_size: int | None = None,
) -> Path:
    if not download_url.startswith("https://"):
        raise ValueError("Installer download URL must use HTTPS.")
    if not installer_name.startswith(INSTALLER_PREFIX) or not installer_name.endswith(INSTALLER_SUFFIX):
        raise ValueError("Unexpected installer filename.")

    target = updates_dir() / installer_name
    request = urllib.request.Request(download_url, headers=_github_headers(), method="GET")
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    if expected_size is not None and len(data) != expected_size:
        raise RuntimeError("Downloaded installer size does not match the GitHub release asset.")
    target.write_bytes(data)
    return target


def launch_installer(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Installer not found: {path}")
    if sys.platform == "win32":
        subprocess.Popen(
            [str(path), "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
            close_fds=True,
        )
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)], close_fds=True)
        return
    subprocess.Popen(["xdg-open", str(path)], close_fds=True)


def save_update_settings(*, check_on_startup: bool | None = None) -> Path:
    cfg = load_config()
    if check_on_startup is not None:
        cfg.check_updates_on_startup = check_on_startup
    return cfg.write()


def dismiss_update(version: str) -> Path:
    cfg = load_config()
    cfg.update_dismissed_version = normalize_release_tag(version)
    return cfg.write()


def clear_update_cache() -> None:
    with _cache_lock:
        global _cached_result
        _cached_result = None


def run_startup_update_check() -> None:
    cfg = load_config()
    if not cfg.check_updates_on_startup:
        return
    try:
        check_for_update(force=False)
    except OSError:
        pass
