# Changelog

This file records changes made in this fork. Upstream release history remains
available in the original repository and Git history.

Forked from `TheStockPot/NFC-Cartridge-Player` v1.0.3 at upstream commit
[`6b95482`](https://github.com/TheStockPot/NFC-Cartridge-Player/commit/6b954823f58bc47cc33692be26f6abbd60578425).

## [Unreleased]

### Added

- Public-safe Home Assistant native-Plex setup guide.
- Private JSON mapping format for associating an NFC UID with a PlexServer movie,
  exact rating key, zero-based media version, and fail-closed media-ID, part-ID,
  basename, and duration fingerprint.
- Local helper commands for sanitized Plex server, movie/version, and native-player
  discovery.
- A `play --dry-run` validation path that never contacts the player.
- Reboot-safe insertion/removal automation with conditional TV-input behavior and
  redundant local stop paths, plus an active-UID guard so an unknown cartridge
  removal cannot stop unrelated playback and startup reconciliation cannot leave a
  stale ownership marker.
- Process-level play/stop arbitration that rejects superseded requests and prevents
  a canceled Home Assistant shell-command child from dispatching playback after a
  newer cartridge-removal stop, with a safe full-start reset for corrected clocks.
- Ignore rules for private Home Assistant data, mappings, caches, logs, and backups.

### Changed

- Replaced stale branch-specific README links with durable repository-relative
  links, repaired the obsolete Waveshare URL, and removed tracking parameters from
  BOM links.
- Linked the project video directly and added the native-Plex guide to Quick Links.
- Documented separate Home Assistant UI/file import paths and explicit ignore rules
  for installations that version-control `/config` independently.
- Clarified upstream release labeling and added a pre-flash warning for inherited
  ESPHome demo network values.
- Preserved the original project's attribution, upstream history, and GPL-3.0
  license.
