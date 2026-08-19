# Changelog

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
