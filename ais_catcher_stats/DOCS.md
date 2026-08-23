# AIS-catcher Statistics

Turns the statistics of a running [AIS-catcher](https://github.com/jvde-github/AIS-catcher)
instance into Home Assistant entities.

This is a **bridge only** — it does not run AIS-catcher itself. Point it at any
AIS-catcher web server on your network (or at the AIS-catcher add-on running on
the same machine) and it publishes ~35 entities, all grouped under a single
Home Assistant device. It can also track individual ships as their own devices,
see [Vessel trackers](#vessel-trackers).

It replaces the `rest:` + `template:` YAML from
[issue #376](https://github.com/jvde-github/AIS-catcher/issues/376) — same data,
no YAML, and the entities actually end up on one device.

## Requirements

- AIS-catcher running with the web server enabled (`-N 8100 ...`), reachable
  from Home Assistant.
- An MQTT broker. The [Mosquitto broker](https://github.com/home-assistant/addons/tree/master/mosquitto)
  add-on plus the MQTT integration is enough — the credentials are picked up
  from the Supervisor automatically, you do not have to type them anywhere.
  An external broker works too: set `mqtt_host` (and `mqtt_port`, `mqtt_user`,
  `mqtt_password`) and the Mosquitto add-on is not needed at all.

## Installation

1. Add this repository under **Settings → Add-ons → Add-on store → ⋮ →
   Repositories**.
2. Install **AIS-catcher Statistics**.
3. Set `url` to your AIS-catcher web server and start the add-on.
4. The device appears under **Settings → Devices & services → MQTT**.

## The sidebar

The add-on proxies AIS-catcher through Home Assistant ingress. By default the
sidebar shows the web viewer from `url`. Set `sidebar_view: dashboard` and
`dashboard_url` (for example `http://192.168.1.10:8118`) to show AIS-catcher's
managed dashboard instead. Statistics continue to come from `url` either way.

The managed dashboard requires a recent AIS-catcher build and asks for its own
password. Its API, event stream and embedded viewer remain inside Home
Assistant ingress; the receiver does not need to be exposed to the internet.

Because the page is served through Home Assistant rather than fetched by the
browser:

- it is behind your Home Assistant login,
- it works from outside the house, over HTTPS, without exposing AIS-catcher
  to the internet or hitting mixed-content errors,
- the browser never has to reach the receiver itself, so the map also works on
  a phone that is not on the same network.

`http_username` / `http_password` are passed through, and an `https://`
receiver keeps its certificate verified unless `verify_ssl` is `false`.

If the proxy cannot start, the add-on logs a warning and carries on publishing
statistics; only the panel is affected.

## Options

| Option | Default | Description |
|---|---|---|
| `url` | `http://192.168.1.10:8100` | Base URL of the AIS-catcher web server. The add-on tries `/api/stat.json` first and falls back to `/stat.json` for older builds. |
| `sidebar_view` | `web_viewer` | Show the web viewer from `url`, or the managed `dashboard` from `dashboard_url`. |
| `scan_interval` | `30` | Seconds between polls (5–3600). |
| `device_name` | `AIS-catcher` | Name of the device in Home Assistant. |
| `device_id` | `aiscatcher` | Identifier used in entity ids and MQTT topics. Give each receiver its own value if you run several instances of this add-on. |
| `message_type_sensors` | `true` | Adds the nine per message-group sensors. |
| `vessels` | empty | Vessels to track as their own device, see below. |
| `vessel_timeout` | `30` | Minutes without a message after which a tracked vessel goes unavailable. |
| `fleet_sensors` | `true` | Sensors for the nearest vessel and how many are close by, for every ship in range rather than the listed ones. |
| `nearby_radius` | `5` | Nautical miles counted as "nearby" (1–500). |
| `remove_entities_on_stop` | `false` | Clears the discovery topics when the add-on stops, so the device disappears from Home Assistant instead of going unavailable. |
| `log_level` | `info` | `debug` logs every poll. |

Optional (hidden unless you add them):

| Option | Description |
|---|---|
| `dashboard_url` | Managed dashboard URL, for example `http://192.168.1.10:8118`. Required when `sidebar_view` is `dashboard`; it does not change the statistics source. |
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

**Nearby** (when `fleet_sensors` is on) — nearest vessel (its MMSI, distance,
bearing, speed, country and type are attributes), nearest vessel distance, and
the number of vessels within `nearby_radius`. These cover every ship in range,
so an automation can react to a ship approaching without knowing its MMSI.

**Diagnostics** — web connections, memory use, received total, uptime, station,
version, build, build date, receiver device, coverage sectors, engine running,
community sharing.

The receiver also gets an **Antenna location** `device_tracker`, so it appears
on the map next to the ships it hears — that position is what every distance
and bearing is measured from. It is published once AIS-catcher reports a real
position.

Two entities carry extra attributes: `Coverage sectors` holds the per-sector
reception reach (`reach`, `channel_a`, `channel_b` — AIS-catcher's radar
arrays, one entry per compass sector) for drawing a polar plot, and
`Community sharing` holds the `link` to your aiscatcher.org page and the
`station_link` to MarineTraffic.

Long-term statistics work out of the box: counters carry `state_class`, the
byte counters use `device_class: data_size`, distances `device_class: distance`,
and uptime is a `timestamp` (so it does not produce a sawtooth graph).

## Vessel trackers

Add the ships you care about under `vessels` and each one becomes its own
Home Assistant device, linked to the receiver:

```yaml
vessels:
  - mmsi: 219025528
    name: DBB Asterix     # optional, overrides the name the ship broadcasts
  - mmsi: 431000123       # name is picked up from the AIS broadcast
```

Per vessel you get a `device_tracker` (source type GPS, so it shows on the map
and triggers zone automations), an `In range` binary sensor, and sensors for
speed, course over ground, heading, distance, bearing, navigation status,
destination, estimated arrival and country — plus, as diagnostics, last signal,
signal level, message count, call sign, length, beam and draught. Values the
ship has not broadcast yet stay `unknown` rather than showing a wrong 0.

Everything from `Estimated arrival` down comes from the AIS static report
(message 5/24), which a ship sends every few minutes — expect those to fill in
a little after the first position. The ETA carries no year, so the add-on picks
the year that puts it closest to now.

Use **`In range`** for automations rather than the availability of the other
entities: it reads `on`/`off` and stays that way, while the rest go
`unavailable`, which also happens on a Home Assistant restart.

```yaml
automation:
  - triggers:
      - trigger: state
        entity_id: binary_sensor.dbb_asterix_in_range
        from: "off"
        to: "on"
    actions:
      - action: notify.mobile_app
        data:
          message: >-
            {{ state_attr('sensor.dbb_asterix_distance', 'friendly_name') }} is
            back, {{ states('sensor.dbb_asterix_distance') }} away.
```

This replaces the hand-written per-ship MQTT YAML from
[issue #376](https://github.com/jvde-github/AIS-catcher/issues/376): no
templates, no `unique_id` to invent, and the entities are grouped per ship.

A vessel that has not been heard for `vessel_timeout` minutes (or that has left
the receiver's range) goes `unavailable`, so automations can tell "not here"
from "here, but stationary". The device and its last position remain, and the
entities come back as soon as the ship is heard again.

Notes:

- Tracking is polled on the same `scan_interval` as the statistics, from
  `/api/ships.json`. Ten vessels cost one extra HTTP request per cycle, not ten.
- The name shown is the configured name, otherwise the last name broadcast by
  the ship, otherwise `MMSI <number>`. Once a name has been heard it is kept
  even while the ship is out of range.
- A vessel that is configured but never heard still appears, as an unavailable
  device — which is also how a mistyped MMSI shows up.

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
  `aiscatcher/<device_id>/status`, the nearby summary on
  `aiscatcher/<device_id>/fleet`, the antenna position on
  `aiscatcher/<device_id>/position`, and one vessel each on
  `aiscatcher/<device_id>/vessel/<mmsi>`. The state topic carries the whole
  normalised `stat.json`, so you can build extra template sensors from fields
  that have no entity of their own, e.g. `value_json.msg_types['21']`.
- `ships.json` is only requested when something needs it — a tracked vessel or
  `fleet_sensors`. With both off, the add-on polls `stat.json` alone.
- Removing a vessel from `vessels` also removes its device from Home Assistant
  on the next start. The add-on keeps the list it has published for in
  `/data/known_vessels.json`, because a vessel's discovery stays retained in
  the broker after its option is gone.

## Troubleshooting

**"No MQTT service found"** — install the Mosquitto broker add-on and configure
the MQTT integration, or set `mqtt_host` manually.

**"Cannot read statistics from ..."** — check that the URL is reachable from the
Home Assistant host and that AIS-catcher was started with the web server
enabled. From an SSH add-on: `curl http://<host>:8100/api/stat.json`.

**A tracked vessel stays unavailable** — it has not been heard yet. Check that
the MMSI is right and that the ship appears in the AIS-catcher map, and remember
that `vessel_timeout` (30 minutes by default) marks a silent ship unavailable.

**No AIS-catcher entry in the sidebar** — an add-on that gained ingress through
an *update* keeps the Supervisor's stored "Show in sidebar" setting, which was
off before it had a panel. Turn it on under **Settings → Add-ons → AIS-catcher
Statistics → Show in sidebar**. A fresh install has it on already.

**The sidebar panel is empty** — check the add-on log. `Could not start the web
UI proxy` is followed by what nginx objected to; anything else means the
receiver's web server did not answer, and `curl <url>` from an SSH add-on will
say why. The statistics are unaffected either way.

**A vessel appears twice, or its entities end in `_2`** — from the 0.4.1
rename. 0.4.2 clears the old discovery on start, so the duplicate device goes
away by itself; restart the add-on once if it is still there. Home Assistant
keeps the freed entity ids reserved, so rename the `_2` entities by hand under
**Settings → Devices & services → Entities** to get them back.

**Entities did not appear** — the discovery messages are sent once at startup;
restart the add-on after changing `device_name` or `device_id`. Renaming
`device_id` creates a *new* device, the old one has to be deleted manually.
