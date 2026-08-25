# Home Assistant Native Plex Cartridge Player

This optional extension maps an NFC cartridge UID to an exact movie and media
version on a server named generically as **PlexServer**, then starts it in the
native Plex app on an Android TV device. It uses local Plex Companion control;
Google Cast is not involved.

It builds on [The Stock Pot NFC Cartridge Player](https://github.com/TheStockPot/NFC-Cartridge-Player).
The original hardware, firmware, wiring diagrams, templates, attribution, and
GPL-3.0 license remain unchanged. This directory is a community reference
configuration for the Home Assistant playback layer; see the fork's
[main README](../README.md) for its overview.

## What happens

When a mapped cartridge is inserted:

1. ESPHome publishes persistent cartridge-presence and UID states.
2. Home Assistant verifies the UID before changing any AV device.
3. If the TV is off, the example powers it on and selects the receiver input. If
   the TV is already on, its current input is left unchanged.
4. The receiver powers on and selects the Android TV player.
5. Home Assistant wakes Android TV, launches native Plex, and waits for the Plex
   package to be in the foreground.
6. The helper validates the Plex server, rating key, title, year, and zero-based
   media version before starting at `0:00`.
7. Home Assistant confirms that the expected title is actually playing, then
   optionally beeps.

When the cartridge is removed, `mode: restart` interrupts any in-progress startup
and attempts to stop playback through native Plex Companion, the Home Assistant
Plex entity, and an Android TV `MEDIA_STOP` fallback. The example intentionally
leaves the TV, receiver, and Android TV device powered on. An ordered request ID
and a process lock also prevent a canceled, still-running shell-command child from
starting the movie after the newer removal request.

## Files

| File | Purpose |
| --- | --- |
| [automation.example.yaml](automation.example.yaml) | Reboot-safe insertion, launch, confirmation, and removal logic |
| [configuration.example.yaml](configuration.example.yaml) | Active-UID helper plus shell commands for discovery, play, and stop |
| [cartridge_config.example.json](cartridge_config.example.json) | Public-safe example of the private UID-to-media mapping |
| [plex_native_player.py](plex_native_player.py) | Read-only discovery and native Plex Companion helper |

The completed file must be named `cartridge_config.json`. It is intentionally
ignored by this fork's `.gitignore` because it contains installation-specific
identifiers and media history. Copying it into a different Git repository does
not carry that protection with it.

## Prerequisites

- A working cartridge reader based on this repository's ESPHome configuration.
- Home Assistant's official [Plex Media Server integration](https://www.home-assistant.io/integrations/plex/)
  configured for your server (called **PlexServer** in these examples).
- Home Assistant's [Android TV Remote integration](https://www.home-assistant.io/integrations/androidtv_remote/)
  configured for the playback device.
- Plex for Android TV installed and signed in.
- **Plex → Settings → Advanced → Advertise as player** enabled on the Android TV
  app. The label can vary slightly between Plex app versions.
- A DHCP reservation for the Android TV device.
- Network reachability among Home Assistant, PlexServer, and the Android TV device.

The helper runs inside Home Assistant's own shell-command environment, where the
official Plex integration's Python library and `/config` directory are available.
It reads the existing Plex URL and token from
`/config/.storage/core.config_entries`, never edits that file, and redacts known
tokens from errors. Do not edit `.storage` manually.

## How the UID/media association works

The NFC tag is not written with a Plex path. The tag supplies only its UID. Your
private `cartridge_config.json` maps that UID to:

```text
NFC UID
  -> PlexServer machine identifier
  -> movie rating key + library/title/year safety check
  -> zero-based mediaIndex
  -> media ID + part ID + basename + duration fingerprint
  -> native Plex player address + client identifier
```

Keep the completed values private. A UID is not a password, but it is unique and
cloneable; media filenames and identifiers also reveal library details.

## Install the reference files

1. Create `/config/cartridge_player/` in Home Assistant.
2. Copy `plex_native_player.py` there.
3. Copy `cartridge_config.example.json` to
   `/config/cartridge_player/cartridge_config.json`.
4. Create the **Plex cartridge active UID** text helper through **Settings → Devices
   & services → Helpers**, using entity ID
   `input_text.plex_cartridge_active_uid`. Alternatively, merge the example
   `input_text:` entry into `/config/configuration.yaml`.
5. Merge the shell-command entries in `configuration.example.yaml` into the
   existing top-level `shell_command:` section. Do not create a second
   `shell_command:` key.
6. Run Home Assistant's configuration check.
7. Reload Shell Command from **Settings → Tools → YAML**, or call
   `shell_command.reload`.

The first production play or stop creates `.plex_native_player.lock` and
`.plex_native_player_state.json` beside the private mapping. These small runtime
files contain only request-ordering numbers. They are generated automatically; do
not edit or delete them while a command is running. If `/config` is managed in a
separate Git repository, add these entries to that repository's `.gitignore`:

```gitignore
cartridge_player/cartridge_config.json
cartridge_player/.plex_native_player.lock
cartridge_player/.plex_native_player_state.json
cartridge_player/.plex_native_player_state.json.*.tmp
```

The official [Shell Command documentation](https://www.home-assistant.io/integrations/shell_command/)
explains the execution environment, 60-second limit, reload action, and action
responses. Each command returns `stdout`, `stderr`, and `returncode`; the helper's
sanitized JSON is in `stdout`.

## Associate a cartridge with a media file

Collect and verify the values in this order. The discovery actions are read-only
unless the command name contains `play` without `--dry-run` or `stop`.

### 1. Find the NFC UID

1. In Home Assistant, go to **Settings → Tools → States**. Older releases label
   this area **Developer Tools → States**.
2. Search for the cartridge UID entity, such as
   `sensor.cartridge_player_cartridge_id`.
3. Insert the cartridge and confirm the presence entity changes to `on`.
4. Copy the UID exactly as Home Assistant reports it, including separators.
5. Remove the cartridge and confirm presence changes to `off`.

Then test reconnect recovery: unplug the reader, insert the cartridge while it is
unplugged, restore power, and confirm the same UID and `on` presence state return.
Production playback should trigger from the persistent presence state, not only
from `esphome.nfc_card_inserted`; a transient boot-time event can occur before Home
Assistant reconnects.

Replace the fictional UID key in `cartridge_config.json` now. Also enter the exact
Plex library, title, and year you intend to find. Leave the rating key and media
fingerprint placeholders in place until the inspection step.

### 2. Find the PlexServer machine identifier

After adding the shell commands, run this action from **Settings → Tools → Actions**:

```yaml
action: shell_command.plex_cartridge_list_servers
data: {}
```

Read `stdout` in the action response. It lists only each Plex integration's display
name and machine identifier; it does not print URLs or tokens:

```json
{
  "servers": [
    {
      "machineIdentifier": "0123456789abcdef0123456789abcdef01234567",
      "name": "PlexServer"
    }
  ],
  "status": "ok"
}
```

Copy the intended `machineIdentifier` into
`plex_server.machine_identifier` in `cartridge_config.json`. Keep the friendly
`name` as `PlexServer` or choose another generic label.

Manual LAN-only fallback: open
`http://PLEX_SERVER_IP:32400/identity` and copy the XML
`machineIdentifier` attribute. Do not expose port 32400 to the internet for this
check. The server display name is not its machine identifier.

### 3. Find the movie rating key and every available version

Run the read-only inspection action with that UID. The helper reads the exact
library, title, and year from the private JSON, avoiding fragile shell quoting for
movie names:

```yaml
action: shell_command.plex_cartridge_inspect_media
data:
  uid: 04-AA-BB-CC-DD-EE-FF
```

The helper searches PlexServer but never contacts the player. A single result looks
like this shortened fictional example:

```json
{
  "matches": [
    {
      "ratingKey": "12345",
      "title": "Example Movie",
      "year": 2000,
      "versions": [
        {
          "mediaIndex": 0,
          "mediaId": "67890",
          "resolution": "3840x2160",
          "videoCodec": "hevc",
          "audioCodec": "eac3",
          "audioChannels": 6,
          "durationMs": 6000000,
          "parts": [
            {
              "partId": "67891",
              "file": "Example Movie (2000) - 4K.mkv"
            }
          ]
        },
        {
          "mediaIndex": 1,
          "mediaId": "67892",
          "resolution": "1920x1080",
          "parts": [
            {
              "partId": "67893",
              "file": "Example Movie (2000) - 1080p.mkv"
            }
          ]
        }
      ]
    }
  ],
  "status": "ok"
}
```

Choose the intended library item and version, then copy these values into the UID's
entry in `cartridge_config.json`:

- `library`
- exact `title` and `year`
- `ratingKey` as `rating_key`
- selected zero-based `mediaIndex` as `media_index`
- selected `mediaId` as `media_id`
- the selected first part's `partId` as `part_id`
- the first part's `file` as `file_basename`
- the selected version's `durationMs` as `duration_ms`

`mediaIndex` is the version's position starting at zero. It is not the `mediaId` or
`partId`. The helper requires the media ID, part ID, basename, and duration as a
fingerprint and refuses playback if the index later points to a different file.
Retain resolution and codecs in a private maintenance note as additional evidence.

If the helper returns `multiple_matches`, it exits without selecting one. Compare
the rating keys and version metadata, or inspect the edition in Plex Web, before
choosing. Plex editions can be separate library items with different rating keys;
versions are alternate files attached to one item.

Manual fallback: in Plex Web, open the movie, choose **More → Get Info → View XML**,
record the `<Video ratingKey>`, and count the direct `<Media>` elements from zero.
The XML URL may include `X-Plex-Token`, and the XML can include full filesystem
paths. Never publish or share the URL, raw XML, or an unredacted screenshot. See
Plex's guides to [media information](https://support.plex.tv/articles/201998867-investigate-media-information-and-formats/)
and [multi-version movies](https://support.plex.tv/articles/200381043-multi-version-movies/).

If a file is added, removed, replaced, optimized, split, merged, or rescanned, Plex
may reorder the versions. Re-run inspection instead of assuming the old
`media_index` still selects the same file. The fingerprint check deliberately fails
closed when Plex IDs, filename, or duration drift.

### 4. Find the native Plex player identifier

1. Give the Android TV device a DHCP reservation.
2. Enable **Advertise as player** in Plex for Android TV.
3. Launch Plex and leave it in the foreground.
4. Run this read-only action, replacing the documentation-only IP:

```yaml
action: shell_command.plex_cartridge_inspect_player
data:
  base_url: http://192.0.2.10:32500
```

The address `192.0.2.10` is reserved for documentation; it will not reach a real
device. Use the reserved local IP of your Android TV player. A working response
contains a player similar to:

```json
{
  "players": [
    {
      "clientIdentifier": "example-com-plexapp-android",
      "product": "Plex for Android (TV)",
      "protocolCapabilities": "timeline,playback",
      "title": "Android TV"
    }
  ],
  "status": "ok"
}
```

Put the actual URL and `clientIdentifier` in the `player` section of
`cartridge_config.json`. The player client identifier is different from the Plex
server machine identifier. Reinstalling Plex or clearing its app data can change
it.

Manual fallback: open `http://PLAYER_IP:32500/resources` on the trusted LAN and
copy the `<Player machineIdentifier>` value. Do not append a Plex token or expose
port 32500 publicly.

### 5. Complete the private mapping

Your private file should now have the same shape as this fictional example:

```json
{
  "plex_server": {
    "name": "PlexServer",
    "machine_identifier": "0123456789abcdef0123456789abcdef01234567"
  },
  "player": {
    "base_url": "http://192.0.2.10:32500",
    "client_identifier": "example-com-plexapp-android"
  },
  "cartridges": {
    "04-AA-BB-CC-DD-EE-FF": {
      "library": "Movies",
      "title": "Example Movie",
      "year": 2000,
      "rating_key": "12345",
      "media_index": 1,
      "media_id": "67892",
      "part_id": "67893",
      "file_basename": "Example Movie (2000) - 1080p.mkv",
      "duration_ms": 6000000
    }
  }
}
```

Replace every fictional value in the real private file. Do not commit it.

### 6. Find the Home Assistant entity IDs and source labels

Under **Settings → Tools → States**, record the exact installation-specific IDs:

| Purpose | Fictional example |
| --- | --- |
| Cartridge presence | `binary_sensor.cartridge_player_cartridge_present` |
| Cartridge UID | `sensor.cartridge_player_cartridge_id` |
| Optional beep | `button.cartridge_player_beep` |
| TV | `media_player.tv` |
| AV receiver | `media_player.av_receiver` |
| Android TV remote | `remote.android_tv` |
| Plex scan-clients button | `button.plexserver_scan_clients` |
| Native Plex player | `media_player.plex_android_tv` |
| Active cartridge UID | `input_text.plex_cartridge_active_uid` |

For the TV and receiver, inspect the `source_list` attribute and copy source names
exactly, including capitalization. With Plex open, confirm the Android TV remote's
`current_activity` is normally `com.plexapp.android`.

To discover the native Plex player entity, start a short movie manually in Plex,
press the Plex integration's scan-clients button, then search States for the Plex
entity reporting that title. Stop the manual playback afterward. A native Plex
entity can legitimately be unavailable while the client is idle. Home Assistant
recommends the per-server scan-clients button over the older
`plex.scan_for_clients` action.

### 7. Customize the automation

`automation.example.yaml` is one automation mapping. Choose exactly one import
route:

- **Automation UI:** create a new automation, open **Edit in YAML**, remove the
  example's first `id:` line, and paste the remaining mapping. The UI owns the
  automation ID.
- **Direct `automations.yaml` edit:** prefix the top-level `id:` with `- ` and
  indent every following line by two spaces so the mapping becomes one list item.

Customize the alias in either route. Direct-file users must also replace the
example `id` with a unique value; the UI generates its own ID. Then replace:

- the fictional `expected_uid` and `expected_title_lower`
- the removal trigger's fictional `from` UID (it must match `expected_uid`)
- cartridge presence, UID, and beep entities
- TV and receiver entities and source labels
- Android TV remote entity
- Plex scan-clients button and native Plex player entity

Delete the marked TV, receiver, or buzzer blocks if the installation does not use
them. Do not include the same automation through two YAML paths.

Important behavior to preserve:

- The insertion trigger intentionally has no `from`, so both `off → on` and
  `unavailable → on` work.
- A Home Assistant startup trigger reconciles the persistent active-UID helper. If
  the cartridge was removed while HA was offline, the stale marker is cleared; if
  the mapped cartridge is still present, the normal launch path resumes. The same
  full-start boundary resets persisted request ordering after all earlier helper
  processes have exited, so a corrected host clock cannot strand a future play.
- UID validation happens before AV power or input actions.
- `mode: restart` lets removal or a reader reconnect supersede a stale run.
- Every run receives a time-ordered `request_id`. The native helper serializes the
  final Plex dispatch and stop, rejects older play requests, and skips an older
  stop if a newer insertion has already superseded it. Preserve the `request_id`
  data on every native play/stop action.
- The active-UID helper is set only immediately before mapped playback. Removal
  stops Plex only when both the UID sensor departed this automation's exact UID and
  the helper matches it. Inserting and removing an unknown tag therefore cannot
  interrupt unrelated playback, even if the helper were stale.
- The success beep occurs only after the expected title reports `playing`.
- The TV input changes only when the TV was off at insertion time.

Run Home Assistant's configuration check, reload automations, and confirm the new
automation is enabled.

## Validate without triggering playback

Run the dry-run action with the mapped UID:

```yaml
action: shell_command.plex_cartridge_dry_run
data:
  uid: 04-AA-BB-CC-DD-EE-FF
```

This contacts PlexServer to validate the server, rating key, title, year, and
selected version. It does **not** contact the player or start playback. Confirm the
response says `validated_without_playback` and that its file/version fingerprint is
the intended one.

Do not use **Tools → States → Set state** as a physical-device test; it changes only
Home Assistant's representation. Use actions for real commands.

## Real-world test matrix

Start at low volume and make sure no one is using the AV system.

- [ ] A different NFC tag causes no AV or playback action.
- [ ] Removing a different NFC tag does not stop unrelated Plex playback.
- [ ] Correct cartridge with everything off powers on the intended devices and
      starts the selected version near `0:00`.
- [ ] Correct cartridge with the TV already on does not change the TV input.
- [ ] Removing the cartridge during Android TV startup aborts and stops safely.
- [ ] Removing it during playback stops the native Plex app.
- [ ] Power-cycling the reader with the cartridge already inserted triggers through
      `unavailable → on`.
- [ ] A success beep occurs only after the expected title reports `playing`.
- [ ] The automation remains enabled after a Home Assistant restart.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Nothing happens | Automation enabled; presence becomes `on`; UID exactly matches both JSON and YAML |
| Wrong tag removal stops Plex | Active-UID helper and gated removal branch must be present; clear a stale helper value before retesting |
| Reader restart misses the cartridge | Trigger must omit `from`; use persistent presence/UID states; keep `mode: restart` |
| TV or receiver works but Plex does not | Android TV remote becomes `on`; `current_activity` becomes `com.plexapp.android`; port 32500 is reachable |
| `/resources` has no player | Plex is open; Advertise as player is enabled; player is on a reachable LAN; client app was not reinstalled |
| Helper cannot find PlexServer | Official Plex integration is configured; machine identifier matches `list-servers`; `.storage` format has not changed |
| Wrong movie | Rating key belongs to this server; title/year safeguards match; inspect Plex editions |
| Wrong file/version | Re-run `inspect`; compare media ID, part ID, basename, duration, resolution, and codecs |
| Native Plex entity is unavailable | Launch Plex, start short manual playback, then press the per-server scan-clients button |
| Shell command missing or unchanged | Reload Shell Command after editing `configuration.yaml` |
| Helper reports a canceled or superseded request | A newer insertion/removal run won arbitration; inspect the automation trace rather than retrying the stale process |
| Every new request is rejected after a clock correction or restore | Restart Home Assistant so the startup automation safely resets persisted ordering; do not run the reset command while a helper process is active |
| No beep | Playback/title confirmation timed out or the optional beep entity is unavailable; inspect the automation trace |
| Removal does not stop | Verify the UID departs the exact mapped value and presence becomes `off`; test native stop, HA media stop, and Android TV `MEDIA_STOP` separately |

The helper's `legacy` method name refers to the Plex Companion command API used by
Home Assistant's bundled `plexapi`; it does not mean lower-quality media. The
`modern` method remains available for installations whose bundled library supports
it.

## Add more cartridges

Add another UID object under `cartridges` in the private JSON. For each cartridge,
record a unique UID, exact library/title/year, rating key, media index, media/part
IDs, basename, and duration. The helper can play any configured UID. Extend the Home
Assistant automation with a `choose` block or create a dispatcher that validates
each allowed UID before AV actions; keep one shared active-UID/removal path for the
physical reader.

## Credential and publication safety

- Never commit Plex tokens, Home Assistant tokens, Wi-Fi passwords, ESPHome API
  keys, fallback access-point passwords, `.storage`, `secrets.yaml`, backups, logs,
  databases, traces, or raw Plex XML.
- Never put a Plex token in a URL or command-line argument. URLs enter browser
  history and logs; arguments can enter shell history and process listings.
- Do not publish real UIDs, LAN addresses, server/client identifiers, entity IDs,
  filenames, rating keys, automation traces, helper output, or ESPHome debug logs.
- Do not expose PlexServer port 32400 or native player port 32500 to the internet.
- Store backups in a private location outside this repository.
- Re-run the read-only discovery and dry-run checks after Plex/HA upgrades, player
  replacement or app reinstall, DHCP changes, or Plex library maintenance.

## References

- [Original NFC Cartridge Player repository](https://github.com/TheStockPot/NFC-Cartridge-Player)
- [The Stock Pot build guide](https://www.thestockpot.net/videos/cartrdgeplayer)
- [Home Assistant Plex integration](https://www.home-assistant.io/integrations/plex/)
- [Home Assistant Android TV Remote integration](https://www.home-assistant.io/integrations/androidtv_remote/)
- [Home Assistant Shell Command integration](https://www.home-assistant.io/integrations/shell_command/)
- [Home Assistant Tools](https://www.home-assistant.io/docs/tools/dev-tools/)
- [Plex media information and XML](https://support.plex.tv/articles/201998867-investigate-media-information-and-formats/)
- [Plex multi-version movies](https://support.plex.tv/articles/200381043-multi-version-movies/)
- [Supported Plex Companion apps](https://support.plex.tv/articles/203082707-supported-plex-companion-apps/)
