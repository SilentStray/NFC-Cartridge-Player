#!/usr/bin/env python3
"""Inspect and control a native Plex client for an NFC cartridge player.

The helper reuses the credentials already stored by Home Assistant's official
Plex integration. It never writes to ``.storage`` and never prints a Plex token.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import re
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_CONFIG = Path("/config/cartridge_player/cartridge_config.json")
DEFAULT_CONFIG_ENTRIES = Path("/config/.storage/core.config_entries")
RUNTIME_LOCK_NAME = ".plex_native_player.lock"
RUNTIME_STATE_NAME = ".plex_native_player_state.json"
RUNTIME_LOCK_TIMEOUT_SECONDS = 30
PLACEHOLDER_VALUES = {
    "CHANGE_ME",
    "REPLACE_ME",
    "YOUR_PLEX_CLIENT_IDENTIFIER",
    "YOUR_PLEX_MEDIA_ID",
    "YOUR_PLEX_PART_ID",
    "YOUR_PLEX_RATING_KEY",
    "YOUR_PLEX_SERVER_MACHINE_IDENTIFIER",
}


def emit(payload: dict[str, Any]) -> None:
    """Write machine-readable output without logging credentials."""
    print(json.dumps(payload, indent=2, sort_keys=True))


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} was not found at {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} must contain a JSON object")
    return payload


def load_settings(path: Path) -> dict[str, Any]:
    return read_json(path, "Cartridge configuration")


def load_config_entries(path: Path) -> list[dict[str, Any]]:
    document = read_json(path, "Home Assistant config entries")
    entries = document.get("data", {}).get("entries", [])
    if not isinstance(entries, list):
        raise RuntimeError("Home Assistant config entries have an unexpected format")
    return [entry for entry in entries if isinstance(entry, dict)]


def plex_entries(path: Path) -> list[dict[str, Any]]:
    """Return sanitized Plex config-entry records.

    The private connection URL and token remain inside ``server_config`` and are
    used only when connecting. Callers must not print that dictionary.
    """
    records: list[dict[str, Any]] = []
    for entry in load_config_entries(path):
        if entry.get("domain") != "plex":
            continue
        data = entry.get("data", {})
        if not isinstance(data, dict):
            continue
        server_config = data.get("server_config", {})
        if not isinstance(server_config, dict):
            server_config = {}
        records.append(
            {
                "name": str(entry.get("title") or "PlexServer"),
                "machine_identifier": str(
                    data.get("server_id") or entry.get("unique_id") or ""
                ),
                "server_config": server_config,
            }
        )
    return records


def required_text(mapping: dict[str, Any], key: str, label: str) -> str:
    value = str(mapping.get(key, "")).strip()
    if not value or value.upper() in PLACEHOLDER_VALUES:
        raise RuntimeError(f"Set {label} ({key}) in cartridge_config.json")
    return value


def integer_value(value: Any, label: str, minimum: int = 0) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} must be an integer") from exc
    if result < minimum:
        raise RuntimeError(f"{label} must be at least {minimum}")
    return result


def request_id_value(value: int | None) -> int:
    """Return an orderable automation-run ID, defaulting to the current time."""
    if value in (None, 0):
        return time.time_ns() // 1_000
    return integer_value(value, "request_id", minimum=1)


def runtime_paths(config_path: Path) -> tuple[Path, Path]:
    return (
        config_path.parent / RUNTIME_STATE_NAME,
        config_path.parent / RUNTIME_LOCK_NAME,
    )


def read_runtime_state(path: Path) -> dict[str, int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"cancel_before": 0, "latest_play": 0}
    except json.JSONDecodeError as exc:
        raise RuntimeError("The playback arbitration state is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("The playback arbitration state must be a JSON object")
    return {
        "cancel_before": integer_value(
            payload.get("cancel_before", 0), "cancel_before", minimum=0
        ),
        "latest_play": integer_value(
            payload.get("latest_play", 0), "latest_play", minimum=0
        ),
    }


def write_runtime_state(path: Path, state: dict[str, int]) -> None:
    """Atomically replace the nonsensitive play/stop ordering state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(
                {
                    "cancel_before": state["cancel_before"],
                    "latest_play": state["latest_play"],
                    "version": 1,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def exclusive_runtime_lock(path: Path):
    """Serialize native dispatch/stop operations across helper processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    acquired = False
    deadline = time.monotonic() + RUNTIME_LOCK_TIMEOUT_SECONDS
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            while not acquired:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "Timed out waiting for playback arbitration lock"
                        ) from exc
                    time.sleep(0.05)
        else:
            import fcntl

            while not acquired:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "Timed out waiting for playback arbitration lock"
                        ) from exc
                    time.sleep(0.05)
        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def register_play_request(config_path: Path, request_id: int) -> tuple[Path, Path]:
    """Record the newest play request and reject one already canceled by stop."""
    state_path, lock_path = runtime_paths(config_path)
    with exclusive_runtime_lock(lock_path):
        state = read_runtime_state(state_path)
        if request_id <= state["cancel_before"]:
            raise RuntimeError("Playback request was canceled before it started")
        if request_id <= state["latest_play"]:
            raise RuntimeError(
                "Playback request duplicates or predates the newest play request"
            )
        state["latest_play"] = request_id
        write_runtime_state(state_path, state)
    return state_path, lock_path


def require_current_play_request(state_path: Path, request_id: int) -> None:
    state = read_runtime_state(state_path)
    if request_id <= state["cancel_before"]:
        raise RuntimeError("Playback request was canceled before native dispatch")
    if request_id != state["latest_play"]:
        raise RuntimeError("Playback request was superseded before native dispatch")


def normalize_uid(value: str) -> str:
    compact = re.sub(r"[^0-9A-F]", "", str(value).upper())
    if len(compact) < 8 or len(compact) % 2:
        raise RuntimeError(f"Invalid NFC UID: {value!r}")
    return "-".join(compact[index : index + 2] for index in range(0, len(compact), 2))


def safe_basename(value: str) -> str | None:
    """Return only a basename, regardless of the Plex server's path style."""
    if not value:
        return None
    return re.split(r"[\\/]", value)[-1] or None


def cartridge_for_uid(settings: dict[str, Any], uid: str) -> tuple[str, dict[str, Any]]:
    requested = normalize_uid(uid)
    cartridges = settings.get("cartridges", {})
    if not isinstance(cartridges, dict) or not cartridges:
        raise RuntimeError("No cartridges are defined in cartridge_config.json")

    matches: list[tuple[str, dict[str, Any]]] = []
    for configured_uid, mapping in cartridges.items():
        if not isinstance(mapping, dict):
            raise RuntimeError(f"Mapping for {configured_uid!r} must be a JSON object")
        normalized = normalize_uid(str(configured_uid))
        if normalized == requested:
            matches.append((normalized, mapping))

    if not matches:
        raise RuntimeError(f"NFC UID {requested} is not mapped to a Plex item")
    if len(matches) != 1:
        raise RuntimeError(f"NFC UID {requested} is configured more than once")
    return matches[0]


def searchable_cartridge(mapping: dict[str, Any]) -> dict[str, Any]:
    title = required_text(mapping, "title", "movie title")
    year = integer_value(mapping.get("year"), "Movie year", minimum=1874)
    library = required_text(mapping, "library", "Plex library name")
    return {"library": library, "title": title, "year": year}


def validated_cartridge(mapping: dict[str, Any]) -> dict[str, Any]:
    result = searchable_cartridge(mapping)
    rating_key = required_text(mapping, "rating_key", "Plex rating key")
    if not rating_key.isdigit():
        raise RuntimeError("Plex rating_key must contain digits only")
    media_index = integer_value(mapping.get("media_index"), "media_index", minimum=0)
    media_id = required_text(mapping, "media_id", "Plex media ID")
    part_id = required_text(mapping, "part_id", "Plex part ID")
    if not media_id.isdigit() or not part_id.isdigit():
        raise RuntimeError("Plex media_id and part_id must contain digits only")
    result.update(
        {
            "duration_ms": integer_value(
                mapping.get("duration_ms"), "duration_ms", minimum=1
            ),
            "file_basename": required_text(
                mapping, "file_basename", "selected media filename"
            ),
            "media_id": media_id,
            "media_index": media_index,
            "part_id": part_id,
            "rating_key": rating_key,
        }
    )
    return result


def server_details(settings: dict[str, Any]) -> dict[str, str]:
    section = settings.get("plex_server", {})
    if not isinstance(section, dict):
        raise RuntimeError("plex_server must be a JSON object")
    return {
        "name": str(section.get("name") or "PlexServer"),
        "machine_identifier": required_text(
            section, "machine_identifier", "Plex server machine identifier"
        ),
    }


def player_details(settings: dict[str, Any]) -> dict[str, str]:
    section = settings.get("player", {})
    if not isinstance(section, dict):
        raise RuntimeError("player must be a JSON object")
    base_url = required_text(section, "base_url", "native Plex player base URL").rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError("player.base_url must be an HTTP(S) URL")
    return {
        "base_url": base_url,
        "client_identifier": required_text(
            section, "client_identifier", "native Plex client identifier"
        ),
    }


def connect_server(settings: dict[str, Any], entries_path: Path):
    from plexapi.server import PlexServer
    import requests

    expected = server_details(settings)
    matching = [
        record
        for record in plex_entries(entries_path)
        if record["machine_identifier"] == expected["machine_identifier"]
    ]
    if len(matching) != 1:
        raise RuntimeError(
            f"Expected one Home Assistant Plex entry for {expected['name']}; "
            f"found {len(matching)}"
        )

    private_config = matching[0]["server_config"]
    url = str(private_config.get("url") or "")
    token = str(private_config.get("token") or "")
    if not url or not token:
        raise RuntimeError("The selected Home Assistant Plex entry has no URL or token")

    session = requests.Session()
    session.verify = bool(private_config.get("verify_ssl", True))
    server = PlexServer(url, token, session=session, timeout=10)
    if str(server.machineIdentifier) != expected["machine_identifier"]:
        raise RuntimeError(f"Connected Plex server is not {expected['name']}")
    return server, token


def connect_player(server, token: str, settings: dict[str, Any]):
    from plexapi.client import PlexClient

    player = player_details(settings)
    return PlexClient(
        server=server,
        baseurl=player["base_url"],
        identifier=player["client_identifier"],
        token=token,
        connect=True,
        timeout=10,
    )


def get_movie(server, expected: dict[str, Any]):
    movie = server.fetchItem(f"/library/metadata/{expected['rating_key']}")
    actual_year = integer_value(getattr(movie, "year", None), "Plex item year", minimum=1874)
    if (
        str(getattr(movie, "ratingKey", "")) != expected["rating_key"]
        or str(getattr(movie, "title", "")) != expected["title"]
        or actual_year != expected["year"]
        or str(getattr(movie, "type", "")) != "movie"
        or str(getattr(movie, "librarySectionTitle", "")) != expected["library"]
    ):
        raise RuntimeError(
            "The configured rating key no longer matches the expected library, "
            "movie title, and year"
        )
    return movie


def version_summary(media: Any, media_index: int) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    for part in list(getattr(media, "parts", []) or []):
        file_path = str(getattr(part, "file", "") or "")
        parts.append(
            {
                "container": getattr(part, "container", None),
                "durationMs": getattr(part, "duration", None),
                "file": safe_basename(file_path),
                "partId": str(getattr(part, "id", "") or ""),
                "sizeBytes": getattr(part, "size", None),
            }
        )
    return {
        "audioChannels": getattr(media, "audioChannels", None),
        "audioCodec": getattr(media, "audioCodec", None),
        "bitrateKbps": getattr(media, "bitrate", None),
        "container": getattr(media, "container", None),
        "durationMs": getattr(media, "duration", None),
        "mediaId": str(getattr(media, "id", "") or ""),
        "mediaIndex": media_index,
        "parts": parts,
        "resolution": f"{getattr(media, 'width', '?')}x{getattr(media, 'height', '?')}",
        "videoCodec": getattr(media, "videoCodec", None),
        "videoResolution": getattr(media, "videoResolution", None),
    }


def versions_for(movie) -> list[dict[str, Any]]:
    return [
        version_summary(media, index)
        for index, media in enumerate(list(getattr(movie, "media", []) or []))
    ]


def selected_version(movie, expected: dict[str, Any]) -> dict[str, Any]:
    media_index = expected["media_index"]
    versions = list(getattr(movie, "media", []) or [])
    if media_index >= len(versions):
        raise RuntimeError(
            f"mediaIndex {media_index} is invalid; this movie has {len(versions)} versions"
        )
    summary = version_summary(versions[media_index], media_index)
    first_part = summary["parts"][0] if summary["parts"] else {}
    mismatches = []
    checks = {
        "duration_ms": summary["durationMs"],
        "file_basename": first_part.get("file"),
        "media_id": summary["mediaId"],
        "part_id": first_part.get("partId"),
    }
    for key, actual in checks.items():
        if str(actual) != str(expected[key]):
            mismatches.append(key)
    if mismatches:
        raise RuntimeError(
            "The configured media version fingerprint no longer matches "
            f"mediaIndex {media_index} ({', '.join(mismatches)} changed); "
            "run the read-only inspect command again"
        )
    return summary


def movie_summary(movie) -> dict[str, Any]:
    return {
        "library": getattr(movie, "librarySectionTitle", None),
        "ratingKey": str(getattr(movie, "ratingKey", "") or ""),
        "title": getattr(movie, "title", None),
        "versions": versions_for(movie),
        "year": getattr(movie, "year", None),
    }


def find_session(server, rating_key: str, client_identifier: str, timeout: int = 18):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for item in server.sessions():
            if str(getattr(item, "ratingKey", "")) != rating_key:
                continue
            player = getattr(item, "player", None)
            player_id = str(getattr(player, "machineIdentifier", "") or "")
            if not player_id or player_id == client_identifier:
                return {
                    "player": getattr(player, "title", None),
                    "playerId": player_id or None,
                    "state": getattr(player, "state", None),
                    "viewOffsetMs": getattr(item, "viewOffset", None),
                }
        time.sleep(1)
    return None


def command_list_servers(args: argparse.Namespace) -> int:
    servers = [
        {
            "machineIdentifier": record["machine_identifier"],
            "name": record["name"],
        }
        for record in plex_entries(args.ha_config_entries)
    ]
    emit({"servers": servers, "status": "ok"})
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    normalized_uid, raw_mapping = cartridge_for_uid(settings, args.uid)
    search = searchable_cartridge(raw_mapping)
    server, _token = connect_server(settings, args.ha_config_entries)
    section = server.library.section(search["library"])
    candidates = list(section.search(title=search["title"]))
    exact = [
        item
        for item in candidates
        if str(getattr(item, "type", "")) == "movie"
        and str(getattr(item, "title", "")).casefold() == search["title"].casefold()
        and getattr(item, "year", None) == search["year"]
    ]
    if not exact:
        raise RuntimeError("No exact movie title/year match was found in that Plex library")

    matches = [movie_summary(movie) for movie in exact]
    status = "ok" if len(matches) == 1 else "multiple_matches"
    emit({"cartridgeUid": normalized_uid, "matches": matches, "status": status})
    return 0 if len(matches) == 1 else 2


def command_inspect_player(args: argparse.Namespace) -> int:
    import requests

    base_url = args.base_url.rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError("--base-url must be an HTTP(S) URL")
    response = requests.get(f"{base_url}/resources", timeout=10)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    players = []
    for node in root.findall(".//Player"):
        players.append(
            {
                "clientIdentifier": node.get("machineIdentifier"),
                "platform": node.get("platform"),
                "product": node.get("product"),
                "protocolCapabilities": node.get("protocolCapabilities"),
                "title": node.get("title"),
            }
        )
    if not players:
        raise RuntimeError("The Plex Companion endpoint returned no advertised player")
    emit({"players": players, "status": "ok"})
    return 0


def command_play(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    normalized_uid, raw_mapping = cartridge_for_uid(settings, args.uid)
    expected = validated_cartridge(raw_mapping)
    request_id = request_id_value(args.request_id)
    state_path: Path | None = None
    lock_path: Path | None = None
    if not args.dry_run:
        state_path, lock_path = register_play_request(args.config, request_id)
    server, token = connect_server(settings, args.ha_config_entries)
    movie = get_movie(server, expected)
    selected = selected_version(movie, expected)

    if args.dry_run:
        emit(
            {
                "cartridgeUid": normalized_uid,
                "movie": {
                    "ratingKey": expected["rating_key"],
                    "title": expected["title"],
                    "year": expected["year"],
                },
                "status": "validated_without_playback",
                "version": selected,
            }
        )
        return 0

    client = connect_player(server, token, settings)
    assert state_path is not None and lock_path is not None
    # Home Assistant can cancel its wait without terminating this child process.
    # Recheck the ordered request while holding the same lock used by stop so an
    # orphaned preflight cannot dispatch after a cartridge-removal stop.
    with exclusive_runtime_lock(lock_path):
        require_current_play_request(state_path, request_id)
        if args.method == "modern":
            client.createPlayQueue(
                server,
                movie,
                offset=0,
                mediaIndex=expected["media_index"],
                partIndex=0,
            )
        else:
            client.playMedia(
                movie,
                offset=0,
                mediaIndex=expected["media_index"],
                partIndex=0,
            )

    player = player_details(settings)
    active = find_session(
        server,
        expected["rating_key"],
        player["client_identifier"],
    )
    emit(
        {
            "cartridgeUid": normalized_uid,
            "command": "play",
            "method": args.method,
            "movie": {
                "ratingKey": expected["rating_key"],
                "title": expected["title"],
                "year": expected["year"],
            },
            "session": active,
            "status": "playing" if active else "accepted_without_session",
            "version": selected,
        }
    )
    # Home Assistant performs the final, longer playback confirmation. A command
    # accepted before Plex reports a session is not treated as an immediate error.
    return 0


def command_stop(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    request_id = request_id_value(args.request_id)
    state_path, lock_path = runtime_paths(args.config)
    with exclusive_runtime_lock(lock_path):
        try:
            state = read_runtime_state(state_path)
        except RuntimeError:
            # A stop must remain fail-safe even if a previous runtime file was
            # interrupted or manually damaged.
            state = {"cancel_before": 0, "latest_play": 0}
        state["cancel_before"] = max(state["cancel_before"], request_id)
        write_runtime_state(state_path, state)
        if state["latest_play"] > request_id:
            emit({"command": "stop", "status": "superseded_by_newer_play"})
            return 0
        server, token = connect_server(settings, args.ha_config_entries)
        client = connect_player(server, token, settings)
        client.stop("video")
        emit({"command": "stop", "status": "accepted"})
    return 0


def command_reset_arbitration(args: argparse.Namespace) -> int:
    """Reset persisted ordering at a full Home Assistant process startup."""
    state_path, lock_path = runtime_paths(args.config)
    with exclusive_runtime_lock(lock_path):
        write_runtime_state(state_path, {"cancel_before": 0, "latest_play": 0})
    emit({"command": "reset-arbitration", "status": "reset"})
    return 0


def redact_exception(exc: Exception, entries_path: Path) -> str:
    message = str(exc)
    try:
        for record in plex_entries(entries_path):
            token = str(record["server_config"].get("token") or "")
            if token:
                message = message.replace(token, "[redacted]")
    except Exception:
        pass
    message = re.sub(
        r"(?i)(X-Plex-Token(?:=|%3D))[^&\s\"']+",
        r"\1[redacted]",
        message,
    )
    return message


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Map NFC UIDs to exact Plex movie versions and control a native "
            "Plex Companion client without Google Cast."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Private UID/media mapping (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--ha-config-entries",
        type=Path,
        default=DEFAULT_CONFIG_ENTRIES,
        help=argparse.SUPPRESS,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    list_servers = commands.add_parser(
        "list-servers",
        help="List Plex server names and machine identifiers without tokens",
    )
    list_servers.set_defaults(handler=command_list_servers)

    inspect = commands.add_parser(
        "inspect",
        help="Read-only search that lists a movie's rating key and media versions",
    )
    inspect.add_argument(
        "--uid",
        required=True,
        help="UID whose configured library/title/year should be inspected",
    )
    inspect.set_defaults(handler=command_inspect)

    inspect_player = commands.add_parser(
        "inspect-player",
        help="Read the native client's /resources endpoint without playing media",
    )
    inspect_player.add_argument(
        "--base-url",
        required=True,
        help="Native player URL, normally http://PLAYER_IP:32500",
    )
    inspect_player.set_defaults(handler=command_inspect_player)

    play = commands.add_parser("play", help="Validate or play the movie mapped to a UID")
    play.add_argument("--uid", required=True, help="UID reported by the ESPHome sensor")
    play.add_argument(
        "--method",
        choices=("legacy", "modern"),
        default="legacy",
        help="Plex Companion command style (default: legacy)",
    )
    play.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the mapping and version without contacting the player",
    )
    play.add_argument(
        "--request-id",
        type=int,
        default=0,
        help="Ordered automation-run ID used to cancel stale play processes",
    )
    play.set_defaults(handler=command_play)

    stop = commands.add_parser("stop", help="Stop video on the configured native player")
    stop.add_argument(
        "--request-id",
        type=int,
        default=0,
        help="Ordered automation-run ID that cancels older play processes",
    )
    stop.set_defaults(handler=command_stop)

    reset_arbitration = commands.add_parser(
        "reset-arbitration",
        help="Reset persisted play/stop ordering after Home Assistant starts",
    )
    reset_arbitration.set_defaults(handler=command_reset_arbitration)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except Exception as exc:
        emit(
            {
                "command": getattr(args, "command", None),
                "error": redact_exception(exc, args.ha_config_entries),
                "status": "error",
            }
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
