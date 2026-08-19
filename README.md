# AIS-catcher Home Assistant Add-ons

Home Assistant add-on repository for [AIS-catcher](https://github.com/jvde-github/AIS-catcher).

## Installation

Click the button below to open the "Add add-on repository" dialog on your own
Home Assistant instance:

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnanamitm%2FAIS-catcher-HA)

If the button does not work, add the repository by hand:

1. Open **Settings → Add-ons → Add-on store** in Home Assistant.
2. Select the three dots in the top right and choose **Repositories**.
3. Enter `https://github.com/nanamitm/AIS-catcher-HA` and select **Add**, then
   close the dialog.
4. Reload the page and scroll down to the **AIS-catcher Home Assistant Add-ons**
   section, or search for "AIS-catcher".
5. Select **AIS-catcher Statistics** and select **Install**. The image is built
   on your device, which takes a few minutes on a Raspberry Pi or Home
   Assistant Yellow.
6. Open the **Configuration** tab, set `url` to your AIS-catcher web server
   (for example `http://192.168.1.10:8100`), save, and start the add-on.

### Prerequisites

- Home Assistant **OS** or **Supervised**. Add-ons are not available on Home
  Assistant Container.
- The [Mosquitto broker](https://github.com/home-assistant/addons/tree/master/mosquitto)
  add-on and the MQTT integration. The credentials are picked up from the
  Supervisor automatically, so nothing has to be typed in.
- A running AIS-catcher with its web server enabled, reachable from Home
  Assistant: `http://<host>:8100/api/stat.json` must return JSON.

## Add-ons

### [AIS-catcher Statistics](./ais_catcher_stats)

<img src="ais_catcher_stats/logo.png" width="320" alt="AIS-catcher Statistics">

Polls the `stat.json` endpoint of an existing AIS-catcher web server and
publishes the statistics to Home Assistant over MQTT discovery — around 35
entities, all grouped under **one device**: message rate, vessel counts, range,
signal levels, PPM, per-channel and per-message-type breakdowns, plus
diagnostics such as memory use, received bytes, uptime and version.

Optionally it also tracks individual ships: list the MMSIs you care about and
each becomes its own device with a map tracker, speed, course, distance,
navigation status and destination.

It is a bridge only — it does not run AIS-catcher itself, so it works both with
a receiver on the same machine and with one running elsewhere on the network.

This is the add-on version of the `rest:` + `template:` YAML posted in
[AIS-catcher issue #376](https://github.com/jvde-github/AIS-catcher/issues/376),
without the YAML and without the "all sensors ended up outside a device"
problem.

See [the documentation](./ais_catcher_stats/DOCS.md) for the options.

## Repository layout

```
repository.yaml              add-on repository manifest
ais_catcher_stats/           the add-on (this folder is what Supervisor builds)
├── config.yaml              manifest: options, schema, services: mqtt:need
├── build.yaml               base images per architecture
├── Dockerfile
├── run.sh                   bashio: options + Supervisor MQTT credentials
├── bridge.py                polling, normalisation, MQTT discovery, publishing
├── sensors.py               entity table - add a row to add a sensor
├── translations/en.yaml     option labels shown in the add-on UI
├── icon.png / logo.png      store artwork
├── DOCS.md                  the add-on documentation tab
└── CHANGELOG.md
tests/test_bridge.py         offline test of normalisation and discovery
tools/make_icons.py          regenerates the artwork
.github/workflows/           add-on linter, shellcheck, bridge test
```

## Development

The bridge runs without Home Assistant: the test stubs out MQTT and feeds a
recorded `stat.json` through the normalisation and discovery code, then renders
every value template with Jinja.

```bash
pip install -r tests/requirements.txt && python tests/test_bridge.py
```

Regenerate the artwork after changing `tools/make_icons.py`:

```bash
pip install -r tools/requirements.txt && python tools/make_icons.py
```

To test a change on a real system, copy `ais_catcher_stats/` to `/addons/` on
the Home Assistant host (Samba or SSH add-on), then **Add-on store → ⋮ → Check
for updates**, and use **⋮ → Rebuild** on the add-on after each change. Keep
`run.sh` LF-terminated — `.gitattributes` enforces this.

## License

MIT — see [LICENSE](./LICENSE).
