"""GitHub Releases update checker and installer launcher."""

from __future__ import annotations

import hashlib
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
from urllib.parse import urlparse

from .config import config_dir, load_config
from .version import __version__

GITHUB_REPO = "XharvaK/CitiesAI"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_LATEST_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases"
INSTALLER_PREFIX = "CitiesAI-Setup-"
INSTALLER_SUFFIX = ".exe"
CHECK_CACHE_HOURS = 6
ALLOWED_DOWNLOAD_HOSTS = frozenset(
    {
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
)

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
    warning: str | None = None
    status_message: str | None = None
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
            "warning": self.warning,
            "status_message": self.status_message,
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


def _user_agent() -> str:
    return f"CitiesAI/{__version__} (+https://github.com/{GITHUB_REPO})"


def _github_headers(*, use_token: bool = True) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _user_agent(),
    }
    if use_token:
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_json(url: str, *, timeout: float = 20.0, use_token: bool = True) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=_github_headers(use_token=use_token), method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected GitHub response")
    return payload


def _fetch_latest_tag_via_redirect(*, timeout: float = 20.0) -> str | None:
    request = urllib.request.Request(
        RELEASES_LATEST_PAGE,
        headers={"User-Agent": _user_agent()},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    marker = "/releases/tag/"
    if marker not in final_url:
        return None
    raw = final_url.rsplit(marker, 1)[-1].split("?", 1)[0].split("#", 1)[0]
    return raw or None


def _installer_asset_for_tag(raw_tag: str) -> dict[str, Any]:
    version = normalize_release_tag(raw_tag)
    name = f"{INSTALLER_PREFIX}{version}{INSTALLER_SUFFIX}"
    download_url = f"https://github.com/{GITHUB_REPO}/releases/download/{raw_tag}/{name}"
    return {"name": name, "browser_download_url": download_url, "size": None}


def _minimal_release_from_tag(raw_tag: str) -> dict[str, Any]:
    return {
        "tag_name": raw_tag,
        "html_url": f"https://github.com/{GITHUB_REPO}/releases/tag/{raw_tag}",
        "assets": [_installer_asset_for_tag(raw_tag)],
        "body": "",
        "published_at": "",
    }


def _fetch_latest_release(*, timeout: float = 20.0) -> tuple[dict[str, Any] | None, str | None]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    attempts: list[bool] = [True] if token else [False]
    if token:
        attempts.append(False)

    last_error: str | None = None
    for use_token in attempts:
        try:
            return _fetch_json(RELEASES_LATEST_URL, timeout=timeout, use_token=use_token), None
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403} and use_token and token:
                last_error = "GitHub rejected the configured token; retrying without it."
                continue
            if exc.code == 404:
                return None, "No GitHub release found yet."
            if exc.code in {403, 429}:
                last_error = "GitHub API rate limit reached."
                break
            return None, f"GitHub API returned {exc.code}."
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return None, f"Could not reach GitHub: {exc}"

    raw_tag = _fetch_latest_tag_via_redirect(timeout=timeout)
    if raw_tag:
        warning = last_error or "Used GitHub release page fallback."
        return _minimal_release_from_tag(raw_tag), warning

    if last_error:
        return None, last_error
    return None, "Could not reach GitHub."


def _status_message(
    *,
    current: str,
    latest: str | None,
    update_available: bool,
    warning: str | None = None,
) -> str:
    if latest and not update_available:
        cmp = compare_versions(current, latest)
        if cmp >= 0:
            if cmp == 0:
                return f"No updates available — you're on the latest release (v{latest})."
            return f"No updates available — you're on v{current}."
        return f"You're on v{current}; latest on GitHub is v{latest}."
    if latest and update_available:
        return f"v{latest} is available on GitHub."
    if warning:
        return f"Could not verify updates right now. You're on v{current}."
    return f"You're on v{current}."


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

    release, warning = _fetch_latest_release()
    if release is None:
        result = _base_result(error=warning)
        result = UpdateCheckResult(
            **{
                **result.to_dict(),
                "status_message": _status_message(
                    current=__version__,
                    latest=None,
                    update_available=False,
                    warning=warning,
                ),
            }
        )
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
    status = _status_message(
        current=__version__,
        latest=tag,
        update_available=update_available,
        warning=warning,
    )
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
        warning=warning,
        status_message=status,
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


def _validate_download_url(download_url: str) -> None:
    if not download_url.startswith("https://"):
        raise ValueError("Installer download URL must use HTTPS.")
    host = urlparse(download_url).netloc.lower()
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(f"Installer download host not allowed: {host}")


def download_installer(
    *,
    download_url: str,
    installer_name: str,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
) -> Path:
    _validate_download_url(download_url)
    if not installer_name.startswith(INSTALLER_PREFIX) or not installer_name.endswith(INSTALLER_SUFFIX):
        raise ValueError("Unexpected installer filename.")

    target = updates_dir() / installer_name
    partial = target.with_suffix(target.suffix + ".partial")
    request = urllib.request.Request(
        download_url,
        headers=_github_headers(use_token=bool(os.environ.get("GITHUB_TOKEN"))),
        method="GET",
    )
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            digest.update(chunk)
            handle.write(chunk)
            total += len(chunk)
    if expected_size is not None and total != expected_size:
        partial.unlink(missing_ok=True)
        raise RuntimeError("Downloaded installer size does not match the GitHub release asset.")
    actual_hash = digest.hexdigest()
    if expected_sha256 and actual_hash.lower() != expected_sha256.lower():
        partial.unlink(missing_ok=True)
        raise RuntimeError("Downloaded installer SHA256 does not match the release checksum.")
    partial.replace(target)
    sidecar = target.with_suffix(target.suffix + ".sha256")
    sidecar.write_text(actual_hash + "\n", encoding="utf-8")
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
