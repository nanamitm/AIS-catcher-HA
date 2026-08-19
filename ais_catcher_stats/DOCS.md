# AIS-catcher Statistics

Turns the statistics of a running [AIS-catcher](https://github.com/jvde-github/AIS-catcher)
instance into Home Assistant entities.

This is a **bridge only** — it does not run AIS-catcher itself. Point it at any
AIS-catcher web server on your network (or at the AIS-catcher add-on running on
the same machine) and it publishes ~35 entities, all grouped under a single
Home Assistant device.

It replaces the `rest:` + `template:` YAML from
[issue #376](https://github.com/jvde-github/AIS-catcher/issues/376) — same data,
no YAML, and the entities actually end up on one device.

## Requirements

- AIS-catcher running with the web server enabled (`-N 8100 ...`), reachable
  from Home Assistant.
- An MQTT broker. The [Mosquitto broker](https://github.com/home-assistant/addons/tree/master/mosquitto)
  add-on plus the MQTT integration is enough — the credentials are picked up
  from the Supervisor automatically, you do not have to type them anywhere.

## Installation

1. Add this repository under **Settings → Add-ons → Add-on store → ⋮ →
   Repositories**.
2. Install **AIS-catcher Statistics**.
3. Set `url` to your AIS-catcher web server and start the add-on.
4. The device appears under **Settings → Devices & services → MQTT**.

## Options

| Option | Default | Description |
|---|---|---|
| `url` | `http://192.168.1.10:8100` | Base URL of the AIS-catcher web server. The add-on tries `/api/stat.json` first and falls back to `/stat.json` for older builds. |
| `scan_interval` | `30` | Seconds between polls (5–3600). |
| `device_name` | `AIS-catcher` | Name of the device in Home Assistant. |
| `device_id` | `aiscatcher` | Identifier used in entity ids and MQTT topics. Give each receiver its own value if you run several instances of this add-on. |
| `message_type_sensors` | `true` | Adds the nine per message-group sensors. |
| `remove_entities_on_stop` | `false` | Clears the discovery topics when the add-on stops, so the device disappears from Home Assistant instead of going unavailable. |
| `log_level` | `info` | `debug` logs every poll. |

Optional (hidden unless you add them):

| Option | Description |
|---|---|
| `http_username` / `http_password` | Basic auth for the AIS-catcher web server. |
| `verify_ssl` | Set to `false` for a self-signed HTTPS certificate. |
| `discovery_prefix` | MQTT discovery prefix, if you changed it from `homeassistant`. |
| `mqtt_host` / `mqtt_port` / `mqtt_user` / `mqtt_password` | Use an external broker instead of the Supervisor-provided one. Setting `mqtt_host` switches off auto-detection. |

## Entities

Grouped under one device, named `<device_name> <entity>`:

**Reception** — message rate (msg/s), messages per minute, vessel count, vessel
count maximum, vessels last hour, vessels last day, max distance last hour, max
distance last day, PPM last minute, signal level minimum/maximum, channel A–D
msg/min.

**Message groups** (when `message_type_sensors` is on) — position reports,
base station, static data, binary, SAR aircraft, safety related,
Aid-to-Navigation, long range, other, all in msg/min over the last minute.

**Diagnostics** — web connections, memory use, received total, uptime, station,
version, build, build date, receiver device, engine running, community sharing.

Long-term statistics work out of the box: counters carry `state_class`, the
byte counters use `device_class: data_size`, distances `device_class: distance`,
and uptime is a `timestamp` (so it does not produce a sawtooth graph).

## Notes

- `Received total` is exposed in bytes with `state_class: total_increasing`.
  A [derivative helper](https://www.home-assistant.io/integrations/derivative/)
  on it gives you a throughput sensor; no template parsing needed. Older
  AIS-catcher builds report this as `"117.7 MB"` — the add-on converts either
  form to bytes.
- If AIS-catcher becomes unreachable, all entities go `unavailable` (the add-on
  publishes `offline` on the availability topic and every entity carries
  `expire_after`), rather than keeping stale values.
- MQTT topics: state on `aiscatcher/<device_id>/state`, availability on
  `aiscatcher/<device_id>/status`. The state topic carries the whole normalised
  `stat.json`, so you can build extra template sensors from fields that have no
  entity of their own, e.g. `value_json.msg_types['21']`.

## Troubleshooting

**"No MQTT service found"** — install the Mosquitto broker add-on and configure
the MQTT integration, or set `mqtt_host` manually.

**"Cannot read statistics from ..."** — check that the URL is reachable from the
Home Assistant host and that AIS-catcher was started with the web server
enabled. From an SSH add-on: `curl http://<host>:8100/api/stat.json`.

**Entities did not appear** — the discovery messages are sent once at startup;
restart the add-on after changing `device_name` or `device_id`. Renaming
`device_id` creates a *new* device, the old one has to be deleted manually.
