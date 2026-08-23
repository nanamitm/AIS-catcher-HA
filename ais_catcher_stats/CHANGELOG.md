# Changelog

## 0.5.0

- Add `sidebar_view`, switching the panel between the existing web viewer and
  AIS-catcher's managed dashboard at `dashboard_url`.
- Keep statistics polling on `url` regardless of the sidebar choice.
- Proxy the managed dashboard through the same two-stage gzip decompression,
  ingress URL rewriting and cache protection used by the Receiver add-on.
- Fall back to the web viewer with a warning when dashboard mode is selected
  without `dashboard_url`, so MQTT statistics continue running.

## 0.4.3

- Fix: every start logged `Reconnected to MQTT` and announced all 36 entities a
  second time. The first connection's CONNACK arrives on the MQTT thread, often
  after the first poll has already published, and was read as a reconnect.
- Fix: that reconnect handling ran on the MQTT thread and cleared state the
  main thread was walking, which could abort the shutdown cleanup halfway; and
  because it also cleared the record of what had been announced, a stop within
  30 seconds of a reconnect cleaned up no vessel at all.
- Fix: a brief broker outage reported every discovery message as lost. Those
  are sent with QoS 1, which paho keeps and delivers on the next connection —
  only a QoS 0 message is really dropped.
- Fix: removing a vessel from `vessels` left its device in Home Assistant
  forever, stuck offline, because its discovery stays retained in the broker.
  The vessels published for are remembered in `/data` and cleared when they
  are dropped, which also lets the 0.4.2 sweep reach vessels that were removed
  before it existed.
- Fix: the sidebar panel kept the receiver's IP address from the moment it
  started, so a receiver on DHCP or mDNS that moved left the panel on 502 for
  good. The address is now looked up again every 30 seconds.
- `nginx -t` output is logged when the panel fails to start, instead of being
  discarded — DOCS sends you to that log.

## 0.4.2

- Fix: after the 0.4.1 rename, every tracked vessel appeared **twice**. The
  discovery 0.4.0 published is retained, so the broker kept replaying it and
  Home Assistant kept re-creating the old device — deleting it in the UI only
  brought it back on the next restart. The old topics are now cleared on
  start, which is what actually removes it.
- The duplicate entities took the clean entity ids with them
  (`sensor.<ship>_speed` vs `sensor.<ship>_speed_2`). Once the old device is
  gone, rename the remaining `_2` entities under **Settings → Devices &
  services → Entities**; Home Assistant keeps the id reserved until then.

## 0.4.1

- Fix: vessel devices, entities and discovery topics now carry the `device_id`
  (`aiscatcher_<device_id>_vessel_<mmsi>`). Two instances of the add-on with a
  different `device_id` tracking the same MMSI used to overwrite each other's
  discovery and collide on `unique_id`. Existing vessel devices are re-created
  under the new identifier on the first start; delete the old ones from the
  MQTT integration if they linger.
- Fix: the device disappeared for good when the MQTT broker restarted without
  persistence. Discovery is now re-published on every reconnect, and a lost
  connection is logged instead of silently swallowed.
- Fix: once the bridge had settled on `/stat.json`, an AIS-catcher upgrade that
  moves the endpoint left it polling a 404 forever. The remembered path is now
  only tried first, and is forgotten as soon as it stops answering.
- Fix: the add-on declared `mqtt:need`, so it refused to start without a
  Supervisor-provided broker even though `mqtt_host` points it at an external
  one. It now declares `mqtt:want`.
- Fix: leading or trailing spaces were stripped from the MQTT and HTTP
  passwords, which turned a valid password into an authentication failure.
- Fix: a vessel whose name was known before its type stayed a generic "Vessel"
  forever. The device is re-announced whenever the type or the IMO arrives, and
  neither is unlearned when the ship goes out of range.
- Messages the broker never received are logged instead of dropped silently,
  so a half-working MQTT connection is visible in the add-on log.

## 0.4.0

- The AIS-catcher map is now in the Home Assistant sidebar, through ingress.
  The add-on proxies the receiver's web UI, so it is reached with your Home
  Assistant login, over HTTPS when Home Assistant is, and without the browser
  needing to reach the receiver at all — which also makes it work from
  outside the house without exposing AIS-catcher.
- `http_username` / `http_password` are passed on to the proxied UI, and an
  `https://` receiver keeps its certificate checked unless `verify_ssl` is off.
- A proxy that fails to start is logged and skipped; the statistics keep
  running.

## 0.3.0

- Each tracked vessel gets an `In range` binary sensor. It reads `on`/`off`
  instead of going `unavailable` with the rest of the ship's entities, so an
  automation for "the ferry is back" no longer fires on a restart as well.
- Six sensors more per vessel, from the static report `ships.json` already
  carried: estimated arrival, country, call sign, length, beam and draught.
  The hull size is the sum of the antenna offsets the ship reports, and the
  ETA — which AIS sends without a year — resolves to the year closest to now.
- New `Nearest vessel`, `Nearest vessel distance` and `Vessels nearby` sensors
  covering everything in range, so "a ship is approaching" does not need an
  MMSI up front. Radius set by `nearby_radius` (5 nmi), switched off with
  `fleet_sensors`.
- The receiver appears on the map as an `Antenna location` tracker, at the
  position its distances and bearings are measured from.
- New `Coverage sectors` diagnostic sensor: how many compass sectors heard
  anything last minute, with AIS-catcher's radar arrays as attributes for a
  polar plot. The aiscatcher.org and MarineTraffic links are attributes on
  `Community sharing`.
- `ships.json` is only fetched when a tracked vessel or `fleet_sensors` needs
  it.

## 0.2.2

- Fix: a vessel sensor with no value logged an error on every poll, e.g.
  `sensor.<ship>_heading ... has the non-numeric value: 'unknown'`. A ship that
  never sends heading, destination or IMO hit this 120 times an hour. The
  templates now fall back to `None`, which is the payload the MQTT integration
  turns into the unknown state; `unknown` is only valid on a text sensor.

## 0.2.1

- Fix: no vessel ever appeared. `bashio::config 'vessels'` prints the *elements*
  of a list option, not the list, so the add-on received a bare object and
  logged `The vessels option is not a list, continuing without it`. The option
  is now read straight from `/data/options.json`, and the bridge also accepts
  the flattened form.
- Navigation status 15 ("Undefined") and the reserved codes 9, 10 and 13 are
  named instead of leaving the status sensor unknown. 15 is what a transponder
  sends when the crew set nothing, which is most small craft.

## 0.2.0

- Vessel trackers. List MMSIs under the `vessels` option and each ship becomes
  its own Home Assistant device, linked to the receiver, with a map
  `device_tracker` plus speed, course, heading, distance, bearing, navigation
  status, destination, last signal, signal level and message count.
- Vessel names are taken from the AIS broadcast unless overridden in the
  options, and never fall back to the MMSI once a name has been heard.
- Vessels go unavailable when no message arrives for `vessel_timeout` minutes
  (default 30) instead of showing a stale position.

## 0.1.1

- Fix: Home Assistant rejected every discovery message with
  `value should be a string for dictionary value @ data['device']['model']`.
  AIS-catcher reports `product`, `vendor`, `serial`, `model`, `device_label`,
  `sample_rate`, `station` and `station_link` per receiver, so they arrive as
  arrays (`"model": ["AIS engine v1 base"]`). They are now flattened to a
  display string during normalisation, which also fixes the `Receiver device`
  sensor showing `['AIS 00000060']`.
- The receiver model is exposed as `hw_version` on the device.
- Added `icon.png` and `logo.png`.
- Dropped the `armv7`, `armhf` and `i386` architectures, deprecated since
  Home Assistant 2025.12.

## 0.1.0

- First release.
- Polls `/api/stat.json` (falls back to `/stat.json`) of an existing AIS-catcher
  instance and publishes the statistics via MQTT discovery.
- All entities share one device block.
- Handles both the numeric and the human readable (`"117.7 MB"`) form of the
  `received` counter.
- Availability topic + `expire_after`, so entities go unavailable when the
  receiver is unreachable.
