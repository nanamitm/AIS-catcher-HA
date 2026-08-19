# Changelog

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
