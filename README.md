# 🎞️ ESP Home Cartridge Player

![Cartridge Player](Pictures/Cartridge_Player_3.jpg)

Bring back the magic of movie night — without the rewinding.

This ESPHome-powered cartridge player uses NFC tags and Home Assistant to recreate the nostalgia of physical media. Insert a cartridge, and your smart home takes care of the rest: turning on the TV, playing a movie, dimming the lights — whatever you like.

Whether you're a fan of VHS-era rituals or just want a fun new way to launch automations, this project combines retro vibes with modern convenience.

---

## 🔗 Quick Links

- 🔽 **[Upstream Latest Release](https://github.com/TheStockPot/NFC-Cartridge-Player/releases/latest)**
- 📖 **[Blog Post](https://www.thestockpot.net/videos/cartrdgeplayer)**  
- 📦 **[Bill of Materials](BOM.md)**
- 🖨️ **[3D Print Files](https://www.printables.com/model/1337649-esphome-cartridge-player)**  
- 🧠 **ESPHome Config:** [ESP32-C3](YAML/ESPHome%20YAML%20-%20ESP32-C3) · [ESP32-S3](YAML/ESPHome%20YAML%20-%20ESP32-S3)
- ⚡ **[Firmware flashing instructions](Firmware%20Files/Flashing%20Instructions.md)**
- 📺 **[Project Video](https://www.youtube.com/watch?v=Jhhwn7OA_xY)**
- 🛠️ **[Assembly & Automation Tutorial Channel](https://www.youtube.com/@TheSaucepan-AU)**
- 🏠 **[Home Assistant Native Plex Guide](Home%20Assistant%20Native%20Plex/README.md)**

---

> [!CAUTION]
> The inherited ESPHome examples retain upstream demo Wi-Fi and fallback-hotspot
> values. Before flashing, replace network, fallback AP, API, and OTA values with
> installation-specific `!secret` references, and never commit the completed
> `secrets.yaml`.

---

## 🧰 What It Does

- Reads NFC tags inside custom 3D-printed cartridges  
- Sends tag ID to Home Assistant via ESPHome  
- Triggers automations like:
  - Playing a specific movie or playlist (e.g. via Plex or YouTube)
  - Turning on devices or scenes
  - Running scripts (e.g. dimming lights, launching consoles)

---

## 🛠️ Build Your Own

All components are simple and affordable, with a [Bill of Materials available here](BOM.md), and a full kit available at [thestockpot.net](https://www.thestockpot.net).

🛠️ **Assembly & programming tutorial:**  
[▶️ Watch the project video](https://www.youtube.com/watch?v=Jhhwn7OA_xY)

---

## 🧑‍💻 How It Works

1. Insert a cartridge  
2. ESP32 detects the NFC tag via the RC522  
3. ESPHome reports the tag ID to Home Assistant  
4. Home Assistant runs an automation based on the cartridge ID  
5. Cartridge removed? Media stops. Magic.

---

## 🏠 Native Plex + Home Assistant Extension

This fork adds a public-safe, local-playback reference for launching an exact Plex
movie version in the native Android TV app—without Google Cast. It includes a
private UID-to-media mapping format, read-only discovery commands, a no-playback
dry run, reboot-safe Home Assistant automation, and step-by-step instructions for
finding the NFC UID, Plex rating key, media version, player identifier, and entity
IDs.

➡️ **[Open the Home Assistant Native Plex setup guide](Home%20Assistant%20Native%20Plex/README.md)**

The original project remains credited to
[The Stock Pot](https://github.com/TheStockPot/NFC-Cartridge-Player) and licensed
under GPL-3.0. Fork-specific changes are recorded in [CHANGELOG.md](CHANGELOG.md).
