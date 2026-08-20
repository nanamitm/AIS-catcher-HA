#!/usr/bin/env python3
"""AIS-catcher -> Home Assistant bridge.

Polls the AIS-catcher web server for stat.json, normalises the payload and
publishes it to a single retained MQTT topic.  All entities are announced once
through MQTT discovery and share one `device` block, so they show up as a
single device in Home Assistant.
"""

import json
import logging
import os
import re
import signal
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from itertools import zip_longest

import requests

try:  # paho-mqtt 2.x
    from paho.mqtt.client import CallbackAPIVersion, Client as MqttClient

    def make_client(client_id):
        return MqttClient(CallbackAPIVersion.VERSION1, client_id=client_id)
except ImportError:  # paho-mqtt 1.x
    from paho.mqtt.client import Client as MqttClient

    def make_client(client_id):
        return MqttClient(client_id=client_id)

from sensors import (BINARY_SENSORS, FLEET_SENSORS, MESSAGE_GROUPS, NAV_STATUS,
                     SENSOR_ATTRIBUTES, SENSORS, SHIP_TYPES,
                     VESSEL_BINARY_SENSORS, VESSEL_SENSORS)

LOG = logging.getLogger("ais-bridge")

STAT_PATHS = ("/api/stat.json", "/stat.json")
SHIP_PATHS = ("/api/ships.json", "/ships.json")
CHANNELS = "ABCD"
MSG_TYPES = 27  # AIS message types 1..27, msg[i] holds type i + 1

# Message type -> group name.  Types not listed fall into "other".
MSG_GROUPS = {
    "position": (1, 2, 3, 18, 19),
    "base": (4,),
    "static": (5, 24),
    "binary": (6, 8, 25, 26),
    "sar": (9,),
    "safety": (12, 14),
    "aton": (21,),
    "long_range": (27,),
}

# AIS-catcher reports these per receiver, so they arrive as arrays even for a
# single device: "model": ["AIS engine v1 base"].  MQTT discovery only accepts
# strings in the device block, and an array renders as ['...'] in a template,
# so they are flattened to a display string before anything else sees them.
LIST_FIELDS = ("product", "vendor", "serial", "model", "device_label",
               "sample_rate", "station", "station_link")

SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
SIZE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?B)?", re.IGNORECASE)


def env(name, default="", strip=True):
    """Read an option.

    Values are stripped because the add-on options arrive through bashio and
    a stray space is never meant to be part of a host name or a URL.  Secrets
    are read with strip=False: a password may legitimately begin or end with
    whitespace, and silently trimming it turns into an authentication failure
    with nothing in the log to explain it.
    """
    value = os.environ.get(name, default)
    if strip and isinstance(value, str):
        return value.strip()
    return value


def env_bool(name, default=False):
    return env(name, str(default)).lower() in ("true", "1", "yes", "on")


class Config:
    def __init__(self):
        self.url = env("AIS_URL").rstrip("/")
        self.interval = int(env("SCAN_INTERVAL", "30"))
        self.device_name = env("DEVICE_NAME", "AIS-catcher")
        self.device_id = env("DEVICE_ID", "aiscatcher")
        self.message_groups = env_bool("MESSAGE_TYPE_SENSORS", True)
        self.remove_on_stop = env_bool("REMOVE_ON_STOP", False)
        self.discovery_prefix = env("DISCOVERY_PREFIX", "homeassistant") or "homeassistant"
        self.http_auth = None
        if env("HTTP_USERNAME"):
            self.http_auth = (env("HTTP_USERNAME"), env("HTTP_PASSWORD", strip=False))
        self.verify_ssl = env_bool("VERIFY_SSL", True)
        self.mqtt_host = env("MQTT_HOST", "core-mosquitto")
        self.mqtt_port = int(env("MQTT_PORT", "1883"))
        self.mqtt_user = env("MQTT_USER")
        self.mqtt_pass = env("MQTT_PASS", strip=False)
        self.log_level = env("LOG_LEVEL", "info").upper()

        self.vessels = parse_vessels(env("VESSELS", "[]"))
        self.vessel_timeout = int(env("VESSEL_TIMEOUT", "30")) * 60
        self.fleet_sensors = env_bool("FLEET_SENSORS", True)
        radius = float(env("NEARBY_RADIUS", "5") or 5)
        # Keep a whole number whole, so the attribute reads 5 and not 5.0.
        self.nearby_radius = int(radius) if radius.is_integer() else radius

        self.base_topic = "aiscatcher/%s" % self.device_id
        self.state_topic = "%s/state" % self.base_topic
        self.availability_topic = "%s/status" % self.base_topic
        self.fleet_topic = "%s/fleet" % self.base_topic
        self.station_topic = "%s/position" % self.base_topic

        # Discovery node id of the receiver.  Everything this add-on publishes
        # is namespaced with it, so two instances watching the same vessel do
        # not fight over one discovery topic or one unique_id.
        self.node = "aiscatcher_%s" % self.device_id

    @property
    def needs_ships(self):
        """Whether ships.json has to be fetched at all."""
        return bool(self.vessels) or self.fleet_sensors

    def vessel_node(self, mmsi):
        return "%s_vessel_%d" % (self.node, mmsi)

    def vessel_topic(self, mmsi, suffix=""):
        return "%s/vessel/%d%s" % (self.base_topic, mmsi, suffix)

    def vessel_discovery_topic(self, component, mmsi, key):
        return "%s/%s/%s/%s/config" % (
            self.discovery_prefix, component, self.vessel_node(mmsi), key)


def load_json_entries(raw):
    """Decode the `vessels` option, whichever shape the shell handed over.

    Normally an array.  `bashio::config` prints the elements of a list option
    rather than the list itself, so older run.sh versions -- and anyone
    exporting VESSELS by hand -- can deliver one bare object or several objects
    in a row.  All three forms mean the same thing here.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except ValueError:
        pass

    decoder, entries, index = json.JSONDecoder(), [], 0
    while index < len(raw):
        value, index = decoder.raw_decode(raw, index)   # raises on real garbage
        entries.append(value)
        while index < len(raw) and raw[index] in " \t\r\n,":
            index += 1
    return entries


def parse_vessels(raw):
    """Read the `vessels` add-on option: [{"mmsi": 219025528, "name": "..."}]."""
    try:
        entries = load_json_entries(raw)
    except ValueError as err:
        LOG.error("Cannot read the vessels option (%s), continuing without it", err)
        return []
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        LOG.error("The vessels option is not a list, continuing without it")
        return []

    vessels, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            mmsi = int(entry.get("mmsi"))
        except (TypeError, ValueError):
            LOG.warning("Skipping a vessel without a usable MMSI: %r", entry)
            continue
        if not 1 <= mmsi <= 999999999:
            LOG.warning("Skipping vessel %s: not a valid MMSI", mmsi)
            continue
        if mmsi in seen:
            LOG.warning("Skipping duplicate vessel %s", mmsi)
            continue
        seen.add(mmsi)
        vessels.append({"mmsi": mmsi, "name": str(entry.get("name") or "").strip()})
    return vessels


def hull_size(payload, *keys):
    """Add up the antenna offsets AIS reports instead of a hull size.

    A ship gives the distance from its antenna to bow and stern (or to port and
    starboard); the sum is the length (or the beam).  All zeroes means the
    vessel did not report its dimensions.
    """
    values = [payload.get(key) for key in keys]
    if not all(isinstance(value, (int, float)) for value in values):
        return None
    return sum(values) or None


def eta_time(payload, now=None):
    """Resolve the AIS estimated time of arrival to a timestamp.

    ETA carries month, day, hour and minute but no year, and a transponder that
    has nothing to say sends month 0, day 0, hour 24 or minute 60.  The year
    chosen is the one that puts the ETA closest to now, so an ETA in January
    still resolves while the receiver is in December.
    """
    parts = [payload.get(key) for key in
             ("eta_month", "eta_day", "eta_hour", "eta_minute")]
    if not all(isinstance(value, int) for value in parts):
        return None
    month, day, hour, minute = parts
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59):
        return None

    now = now or datetime.now(timezone.utc)
    best = None
    for year in (now.year - 1, now.year, now.year + 1):
        try:
            candidate = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:   # 31 February and friends
            continue
        if best is None or abs(candidate - now) < abs(best - now):
            best = candidate
    return best.isoformat() if best else None


def nav_status(value):
    return NAV_STATUS.get(value) if isinstance(value, int) else None


def ship_type(value):
    if not isinstance(value, int):
        return None
    for low, high, name in SHIP_TYPES:
        if low <= value <= high:
            return name
    return None


def parse_size(value):
    """Return bytes.  Accepts a raw number or a human string like '12.3 MB'."""
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return 0
    match = SIZE_RE.search(value.strip().upper())
    if not match:
        return 0
    number = float(match.group(1))
    unit = match.group(2) or "B"
    return int(number * SIZE_UNITS.get(unit, 1))


def as_dict(value):
    return value if isinstance(value, dict) else {}


def scalarise(value):
    """Turn a per-receiver array into a display string.

    ["AIS engine v1 base"] -> "AIS engine v1 base"
    ["RTL-SDR", "SDRplay"] -> "RTL-SDR, SDRplay"   (two receivers)
    """
    if isinstance(value, (list, tuple)):
        parts = [str(v).strip() for v in value if v not in (None, "")]
        return ", ".join(parts)
    if value is None:
        return ""
    return str(value).strip() if isinstance(value, str) else value


def pad(values, length):
    values = values if isinstance(values, list) else []
    numbers = [v if isinstance(v, (int, float)) else 0 for v in values[:length]]
    return numbers + [0] * (length - len(numbers))


class Bridge:
    def __init__(self, config):
        self.cfg = config
        self.stop_event = threading.Event()
        self.stat_path = None
        self.ship_path = None
        self.anchors = {}
        self.discovered = False
        self.device = None        # the device block, reused by later discoveries
        self.station_published = False
        self.vessel_names = {}   # mmsi -> the name the discovery was published with
        self.ship_names = {}     # mmsi -> last shipname heard over the air
        self.vessel_seen = set()  # mmsi currently published as online
        self.session = requests.Session()
        self.client = make_client("ais_catcher_stats_%s" % config.device_id)
        if config.mqtt_user:
            self.client.username_pw_set(config.mqtt_user, config.mqtt_pass)
        self.client.will_set(config.availability_topic, "offline", retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

    # --- MQTT -----------------------------------------------------------

    def on_connect(self, client, userdata, flags, rc, *_):
        """Announce everything again after a reconnect.

        paho reconnects on its own, but a broker without persistence loses
        every retained message while it is down -- the discovery config
        included.  Without forgetting what was announced the device would stay
        missing from Home Assistant until the add-on is restarted by hand.
        """
        if rc != 0:
            LOG.error("MQTT broker refused the connection (code %s)", rc)
            return
        if self.discovered or self.vessel_names:
            LOG.info("Reconnected to MQTT, re-publishing discovery")
        self.discovered = False
        self.vessel_names.clear()
        self.vessel_seen.clear()

    def on_disconnect(self, client, userdata, rc, *_):
        if rc != 0:
            LOG.warning("Lost the MQTT connection (code %s), reconnecting", rc)

    # --- HTTP -----------------------------------------------------------

    def fetch(self):
        return self.get_json("stat_path", STAT_PATHS)

    def fetch_ships(self):
        return self.get_json("ship_path", SHIP_PATHS)

    def get_json(self, remembered, candidates):
        """GET the first endpoint that answers, then stick to it.

        The remembered path is tried first, not exclusively: an AIS-catcher
        upgrade can move the endpoint, and a bridge that only ever asks for the
        path it learned once would keep failing on the same 404 forever.
        """
        known = getattr(self, remembered)
        paths = ([known] + [p for p in candidates if p != known]) if known else list(candidates)
        last_error = None
        for path in paths:
            try:
                response = self.session.get(
                    self.cfg.url + path,
                    timeout=min(10, max(3, self.cfg.interval)),
                    auth=self.cfg.http_auth,
                    verify=self.cfg.verify_ssl,
                )
            except requests.RequestException as err:
                last_error = err
                continue
            if response.status_code == 404:
                last_error = RuntimeError("%s returned 404" % path)
                if known == path:
                    LOG.info("Endpoint %s is gone, looking for another one", path)
                    setattr(self, remembered, None)
                    known = None
                continue
            response.raise_for_status()
            if known != path:
                LOG.info("Using endpoint %s", path)
                setattr(self, remembered, path)
            return response.json()
        raise last_error or RuntimeError("no endpoint responded")

    # --- payload --------------------------------------------------------

    def normalise(self, stat):
        """Flatten and stabilise stat.json so the templates cannot break."""
        out = dict(stat)

        for period in ("last_minute", "last_hour", "last_day", "total", "session"):
            bucket = as_dict(stat.get(period))
            bucket["count"] = bucket.get("count", 0) or 0
            bucket["vessels"] = bucket.get("vessels", 0) or 0
            bucket["dist"] = bucket.get("dist", 0) or 0
            bucket["ppm"] = bucket.get("ppm", 0) or 0
            bucket["level_min"] = bucket.get("level_min", 0) or 0
            bucket["level_max"] = bucket.get("level_max", 0) or 0
            bucket["channel"] = pad(bucket.get("channel"), len(CHANNELS))
            bucket["msg"] = pad(bucket.get("msg"), MSG_TYPES)
            out[period] = bucket

        minute = out["last_minute"]
        out["channel"] = dict(zip(CHANNELS, minute["channel"]))
        out.update(self.coverage(minute))

        msg = minute["msg"]
        groups = {}
        grouped_total = 0
        for name, types in MSG_GROUPS.items():
            value = sum(msg[t - 1] for t in types if t <= MSG_TYPES)
            groups[name] = value
            grouped_total += value
        groups["other"] = max(0, sum(msg) - grouped_total)
        out["msg_group"] = groups
        out["msg_types"] = {str(i + 1): msg[i] for i in range(MSG_TYPES)}

        for field in LIST_FIELDS:
            if field in out:
                out[field] = scalarise(out[field])

        out["memory"] = parse_size(stat.get("memory", 0))
        out["received"] = parse_size(stat.get("received", 0))
        out["msg_rate"] = float(stat.get("msg_rate", 0) or 0)
        out["run_time"] = int(float(stat.get("run_time", 0) or 0))
        out["start_time"] = self.resolve_start_time(out["run_time"])
        out["engine_running"] = bool(stat.get("engine_running", True))
        out["sharing"] = bool(stat.get("sharing", False))

        # The OS/hardware blobs are raw JSON and of no use as entities.
        for noisy in ("os", "hardware", "outputs"):
            out.pop(noisy, None)
        return out

    @staticmethod
    def coverage(minute):
        """Reception reach per compass sector, from the radar arrays.

        AIS-catcher splits the horizon into equal sectors and reports the
        furthest message heard in each one, per channel.  Summarised here as a
        count of sectors that heard anything -- a single number that says
        whether the antenna sees all around it -- with the arrays kept as
        attributes so a polar plot can be drawn from them.
        """
        arrays = {}
        for key in ("radar_a", "radar_b"):
            values = minute.get(key)
            arrays[key] = [value if isinstance(value, (int, float)) else 0
                           for value in values] if isinstance(values, list) else []

        reach = [max(a, b) for a, b in
                 zip_longest(arrays["radar_a"], arrays["radar_b"], fillvalue=0)]
        return {
            "coverage_sectors": sum(1 for value in reach if value > 0),
            "coverage": {
                "sectors": len(reach),
                "degrees": round(360 / len(reach), 1) if reach else 0,
                "reach": reach,
                "channel_a": arrays["radar_a"],
                "channel_b": arrays["radar_b"],
            },
        }

    def stable_time(self, key, seconds_ago, tolerance=10):
        """An "N seconds ago" timestamp that does not jitter on every poll.

        The value only moves when it really moved, so Home Assistant does not
        record a new state each cycle.
        """
        candidate = (datetime.now(timezone.utc).replace(microsecond=0)
                     - timedelta(seconds=seconds_ago))
        anchor = self.anchors.get(key)
        if anchor is None or abs((candidate - anchor).total_seconds()) > tolerance:
            self.anchors[key] = candidate
            anchor = candidate
        return anchor.isoformat()

    def resolve_start_time(self, run_time):
        return self.stable_time("start_time", run_time)

    # --- discovery ------------------------------------------------------

    def device_block(self, stat):
        # Every value here must be a plain string; Home Assistant rejects the
        # whole discovery message otherwise.
        def text(*keys):
            for key in keys:
                value = scalarise(stat.get(key))
                if value not in (None, ""):
                    return str(value)
            return ""

        device = {
            "identifiers": [self.cfg.node],
            "name": self.cfg.device_name,
            "manufacturer": "jvde-github",
            "model": text("product", "model", "device_label") or "AIS-catcher",
            "configuration_url": self.cfg.url,
        }
        for field, keys in (("sw_version", ("build_version",)),
                            ("hw_version", ("model",)),
                            ("serial_number", ("serial",))):
            value = text(*keys)
            if value:
                device[field] = value
        return device

    def entities(self):
        rows = list(SENSORS)
        if self.cfg.message_groups:
            rows += MESSAGE_GROUPS
        for key, name, tmpl, unit, dclass, sclass, ecat, icon in rows:
            yield "sensor", key, name, tmpl, unit, dclass, sclass, ecat, icon
        for key, name, tmpl, dclass, ecat in BINARY_SENSORS:
            yield "binary_sensor", key, name, tmpl, None, dclass, None, ecat, None

    def discovery_topic(self, component, key):
        return "%s/%s/%s/%s/config" % (
            self.cfg.discovery_prefix, component, self.cfg.node, key)

    def publish_discovery(self, stat):
        device = self.device = self.device_block(stat)
        count = 0
        for component, key, name, tmpl, unit, dclass, sclass, ecat, icon in self.entities():
            payload = {
                "name": name,
                "unique_id": "%s_%s" % (self.cfg.node, key),
                "object_id": "%s_%s" % (self.cfg.device_id, key),
                "state_topic": self.cfg.state_topic,
                "value_template": tmpl,
                "availability_topic": self.cfg.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "expire_after": max(60, self.cfg.interval * 3),
                "device": device,
            }
            if component == "binary_sensor":
                payload["payload_on"] = "ON"
                payload["payload_off"] = "OFF"
            attributes = SENSOR_ATTRIBUTES.get(key)
            if attributes:
                payload["json_attributes_topic"] = self.cfg.state_topic
                payload["json_attributes_template"] = attributes
            for field, value in (
                ("unit_of_measurement", unit),
                ("device_class", dclass),
                ("state_class", sclass),
                ("entity_category", ecat),
                ("icon", icon),
            ):
                if value:
                    payload[field] = value
            self.client.publish(self.discovery_topic(component, key),
                                json.dumps(payload), qos=1, retain=True)
            count += 1
        LOG.info("Published discovery for %d entities as device '%s'",
                 count, self.cfg.device_name)

    # --- everything in range --------------------------------------------

    def publish_fleet_discovery(self, stat):
        device = self.device_block(stat)
        for key, name, tmpl, unit, dclass, sclass, ecat, icon in FLEET_SENSORS:
            payload = {
                "name": name,
                "unique_id": "%s_%s" % (self.cfg.node, key),
                "object_id": "%s_%s" % (self.cfg.device_id, key),
                "state_topic": self.cfg.fleet_topic,
                "value_template": tmpl,
                "availability_topic": self.cfg.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "expire_after": max(60, self.cfg.interval * 3),
                "device": device,
            }
            for field, value in (("unit_of_measurement", unit),
                                 ("device_class", dclass),
                                 ("state_class", sclass),
                                 ("entity_category", ecat),
                                 ("icon", icon)):
                if value:
                    payload[field] = value
            attributes = SENSOR_ATTRIBUTES.get(key)
            if attributes:
                payload["json_attributes_topic"] = self.cfg.fleet_topic
                payload["json_attributes_template"] = attributes
            self.client.publish(self.discovery_topic("sensor", key),
                                json.dumps(payload), qos=1, retain=True)
        LOG.info("Published discovery for %d fleet entities", len(FLEET_SENSORS))

    def fleet_payload(self, ships):
        """Summarise ships.json: what is closest, and how much is nearby."""
        rows = []
        entries = ships.get("ships", []) or []
        for ship in entries:
            distance = ship.get("distance")
            if isinstance(distance, (int, float)):
                rows.append((distance, ship))

        payload = {
            "radius": self.cfg.nearby_radius,
            "total": len(entries),
            "within": sum(1 for distance, _ in rows
                          if distance <= self.cfg.nearby_radius),
        }
        if rows:
            distance, ship = min(rows, key=lambda row: row[0])
            nearest = {"distance": distance}
            try:
                nearest["mmsi"] = int(ship["mmsi"])
                nearest["name"] = str(ship.get("shipname") or "").strip() \
                    or "MMSI %d" % nearest["mmsi"]
            except (KeyError, TypeError, ValueError):
                return payload
            for key in ("bearing", "speed", "country", "last_signal"):
                value = ship.get(key)
                if value is not None:
                    nearest[key] = value
            type_text = ship_type(ship.get("shiptype"))
            if type_text:
                nearest["shiptype"] = type_text
            payload["nearest"] = nearest
        return payload

    def publish_fleet(self, ships):
        self.client.publish(self.cfg.fleet_topic,
                            json.dumps(self.fleet_payload(ships)),
                            qos=0, retain=True)

    def publish_station(self, ships):
        """Put the receiver itself on the map.

        ships.json reports the antenna position, which is what every distance
        and bearing in the payload is measured from.  A receiver that has no
        position configured reports 0/0 -- a real coordinate in the Atlantic,
        so it has to be skipped rather than published.
        """
        station = as_dict(ships.get("station"))
        lat, lon = station.get("lat"), station.get("lon")
        if not all(isinstance(value, (int, float)) for value in (lat, lon)):
            return
        if lat == 0 and lon == 0:
            return

        if not self.station_published:
            tracker = {
                "name": "Antenna location",
                "unique_id": "%s_station_location" % self.cfg.node,
                "object_id": "%s_station_location" % self.cfg.device_id,
                "json_attributes_topic": self.cfg.station_topic,
                "availability_topic": self.cfg.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "source_type": "gps",
                "device": self.device or {"identifiers": [self.cfg.node]},
            }
            self.client.publish(
                self.discovery_topic("device_tracker", "station_location"),
                json.dumps(tracker), qos=1, retain=True)
            self.station_published = True
            LOG.info("Published the receiver position %.4f, %.4f", lat, lon)

        self.client.publish(self.cfg.station_topic,
                            json.dumps({"latitude": lat, "longitude": lon,
                                        "gps_accuracy": 0}),
                            qos=0, retain=True)

    # --- vessels --------------------------------------------------------

    def vessel_payload(self, ship):
        """Normalise one entry of ships.json.

        Keys AIS-catcher has not received are absent, and nulls are dropped, so
        the templates can fall back with `default('unknown')` while a real 0
        still comes through.
        """
        mmsi = int(ship["mmsi"])
        payload = {"mmsi": mmsi}
        for key in ("lat", "lon", "speed", "cog", "heading", "distance", "bearing",
                    "level", "ppm", "count", "status", "shiptype", "shipname",
                    "destination", "callsign", "imo", "last_signal",
                    "country", "draught",
                    "to_bow", "to_stern", "to_port", "to_starboard",
                    "eta_month", "eta_day", "eta_hour", "eta_minute"):
            value = ship.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            payload[key] = value

        status_text = nav_status(payload.get("status"))
        if status_text:
            payload["status_text"] = status_text
        type_text = ship_type(payload.get("shiptype"))
        if type_text:
            payload["shiptype_text"] = type_text

        for key, offsets in (("length", ("to_bow", "to_stern")),
                             ("beam", ("to_port", "to_starboard"))):
            size = hull_size(payload, *offsets)
            if size is not None:
                payload[key] = size

        eta = eta_time(payload)
        if eta:
            payload["eta"] = eta

        # last_signal is the age of the last message in seconds
        age = payload.get("last_signal")
        if isinstance(age, (int, float)):
            payload["last_signal_time"] = self.stable_time("vessel_%d" % mmsi, age)
        return payload

    def vessel_name(self, mmsi, configured, payload):
        """A name that never downgrades.

        A ship out of range reports nothing, so without remembering the last
        known shipname the device would flip back to "MMSI ..." and republish
        its discovery every time the vessel leaves and returns.
        """
        if payload.get("shipname"):
            self.ship_names[mmsi] = payload["shipname"]
        return configured or self.ship_names.get(mmsi) or "MMSI %d" % mmsi

    def vessel_device(self, mmsi, name, payload):
        device = {
            "identifiers": [self.cfg.vessel_node(mmsi)],
            "name": name,
            "manufacturer": "AIS",
            "model": payload.get("shiptype_text") or "Vessel",
            "via_device": self.cfg.node,
        }
        if payload.get("imo"):
            device["serial_number"] = "IMO %s" % payload["imo"]
        return device

    def publish_vessel_discovery(self, mmsi, name, payload):
        device = self.vessel_device(mmsi, name, payload)
        state_topic = self.cfg.vessel_topic(mmsi)
        availability = self.cfg.vessel_topic(mmsi, "/status")

        # The tracker takes its position from a dedicated attributes topic, so
        # Home Assistant can place it on the map without a state template.
        tracker = {
            "name": "Location",
            "unique_id": "%s_location" % self.cfg.vessel_node(mmsi),
            "object_id": "%s_%d_location" % (self.cfg.device_id, mmsi),
            "json_attributes_topic": self.cfg.vessel_topic(mmsi, "/position"),
            "availability_topic": availability,
            "payload_available": "online",
            "payload_not_available": "offline",
            "source_type": "gps",
            "device": device,
        }
        self.client.publish(
            self.cfg.vessel_discovery_topic("device_tracker", mmsi, "location"),
            json.dumps(tracker), qos=1, retain=True)

        for key, ename, dclass, icon in VESSEL_BINARY_SENSORS:
            config = {
                "name": ename,
                "unique_id": "%s_%s" % (self.cfg.vessel_node(mmsi), key),
                "object_id": "%s_%d_%s" % (self.cfg.device_id, mmsi, key),
                "state_topic": availability,
                "payload_on": "online",
                "payload_off": "offline",
                # The bridge's availability, not the vessel's: a ship out of
                # range has to read "off", not "unavailable".
                "availability_topic": self.cfg.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            }
            for field, value in (("device_class", dclass), ("icon", icon)):
                if value:
                    config[field] = value
            self.client.publish(
                self.cfg.vessel_discovery_topic("binary_sensor", mmsi, key),
                json.dumps(config), qos=1, retain=True)

        for key, ename, tmpl, unit, dclass, sclass, ecat, icon in VESSEL_SENSORS:
            config = {
                "name": ename,
                "unique_id": "%s_%s" % (self.cfg.vessel_node(mmsi), key),
                "object_id": "%s_%d_%s" % (self.cfg.device_id, mmsi, key),
                "state_topic": state_topic,
                "value_template": tmpl,
                "availability_topic": availability,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device,
            }
            for field, value in (("unit_of_measurement", unit),
                                 ("device_class", dclass),
                                 ("state_class", sclass),
                                 ("entity_category", ecat),
                                 ("icon", icon)):
                if value:
                    config[field] = value
            self.client.publish(self.cfg.vessel_discovery_topic("sensor", mmsi, key),
                                json.dumps(config), qos=1, retain=True)

        self.vessel_names[mmsi] = name
        LOG.info("Published discovery for vessel %d as '%s'", mmsi, name)

    def publish_vessels(self, ships):
        """Publish one device per configured vessel from a ships.json response."""
        index = {}
        for ship in ships.get("ships", []) or []:
            try:
                index[int(ship["mmsi"])] = ship
            except (KeyError, TypeError, ValueError):
                continue

        for vessel in self.cfg.vessels:
            mmsi, configured = vessel["mmsi"], vessel["name"]
            ship = index.get(mmsi)
            payload = self.vessel_payload(ship) if ship else {}

            age = payload.get("last_signal")
            fresh = bool(ship) and not (
                isinstance(age, (int, float)) and age > self.cfg.vessel_timeout)

            name = self.vessel_name(mmsi, configured, payload)
            if self.vessel_names.get(mmsi) != name:
                self.publish_vessel_discovery(mmsi, name, payload)

            if not fresh:
                if mmsi in self.vessel_seen:
                    LOG.info("Vessel %d (%s) is out of range", mmsi, name)
                    self.vessel_seen.discard(mmsi)
                self.client.publish(self.cfg.vessel_topic(mmsi, "/status"),
                                    "offline", qos=1, retain=True)
                continue

            if mmsi not in self.vessel_seen:
                LOG.info("Vessel %d (%s) is in range", mmsi, name)
                self.vessel_seen.add(mmsi)

            self.client.publish(self.cfg.vessel_topic(mmsi, "/status"),
                                "online", qos=1, retain=True)
            self.client.publish(self.cfg.vessel_topic(mmsi),
                                json.dumps(payload), qos=0, retain=True)

            lat, lon = payload.get("lat"), payload.get("lon")
            if lat is not None and lon is not None:
                self.client.publish(
                    self.cfg.vessel_topic(mmsi, "/position"),
                    json.dumps({"latitude": lat, "longitude": lon,
                                "gps_accuracy": 0}),
                    qos=0, retain=True)

    def remove_discovery(self):
        for component, key in [(c, k) for c, k, *_ in self.entities()]:
            self.client.publish(self.discovery_topic(component, key), "", qos=1, retain=True)
        for key, *_ in FLEET_SENSORS:
            self.client.publish(self.discovery_topic("sensor", key), "", qos=1, retain=True)
        self.client.publish(
            self.discovery_topic("device_tracker", "station_location"),
            "", qos=1, retain=True)
        self.client.publish(self.cfg.state_topic, "", qos=1, retain=True)
        self.client.publish(self.cfg.fleet_topic, "", qos=1, retain=True)
        self.client.publish(self.cfg.station_topic, "", qos=1, retain=True)

        for mmsi in self.vessel_names:
            self.client.publish(
                self.cfg.vessel_discovery_topic("device_tracker", mmsi, "location"),
                "", qos=1, retain=True)
            for key, *_ in VESSEL_SENSORS:
                self.client.publish(self.cfg.vessel_discovery_topic("sensor", mmsi, key),
                                    "", qos=1, retain=True)
            for key, *_ in VESSEL_BINARY_SENSORS:
                self.client.publish(
                    self.cfg.vessel_discovery_topic("binary_sensor", mmsi, key),
                    "", qos=1, retain=True)
            for suffix in ("", "/position", "/status"):
                self.client.publish(self.cfg.vessel_topic(mmsi, suffix), "",
                                    qos=1, retain=True)
        LOG.info("Removed discovery configuration from the broker")

    # --- main loop ------------------------------------------------------

    def connect(self):
        while not self.stop_event.is_set():
            try:
                self.client.connect(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=60)
                self.client.loop_start()
                LOG.info("Connected to MQTT broker %s:%d",
                         self.cfg.mqtt_host, self.cfg.mqtt_port)
                return True
            except OSError as err:
                LOG.error("MQTT connection failed (%s), retrying in 10s", err)
                self.stop_event.wait(10)
        return False

    def run(self):
        if not self.connect():
            return 1
        failures = 0
        while not self.stop_event.is_set():
            try:
                stat = self.normalise(self.fetch())
                if not self.discovered:
                    self.publish_discovery(stat)
                    if self.cfg.fleet_sensors:
                        self.publish_fleet_discovery(stat)
                    self.discovered = True
                self.client.publish(self.cfg.availability_topic, "online", qos=1, retain=True)
                self.client.publish(self.cfg.state_topic, json.dumps(stat), qos=0, retain=True)
                if failures:
                    LOG.info("Recovered contact with %s", self.cfg.url)
                failures = 0
                LOG.debug("Published %s vessels, %.2f msg/s",
                          stat.get("vessel_count", 0), stat.get("msg_rate", 0.0))

                if self.cfg.needs_ships:
                    # A tracker hiccup must not take the statistics down with it
                    try:
                        ships = self.fetch_ships()
                        self.publish_station(ships)
                        if self.cfg.vessels:
                            self.publish_vessels(ships)
                        if self.cfg.fleet_sensors:
                            self.publish_fleet(ships)
                    except Exception as err:
                        LOG.warning("Cannot read the vessel list: %s", err)
            except Exception as err:  # keep the bridge alive on any hiccup
                failures += 1
                self.client.publish(self.cfg.availability_topic, "offline", qos=1, retain=True)
                if failures == 1 or failures % 10 == 0:
                    LOG.warning("Cannot read statistics from %s: %s (attempt %d)",
                                self.cfg.url, err, failures)
            self.stop_event.wait(self.cfg.interval)

        if self.cfg.remove_on_stop:
            self.remove_discovery()
        else:
            for mmsi in self.vessel_names:
                self.client.publish(self.cfg.vessel_topic(mmsi, "/status"),
                                    "offline", qos=1, retain=True)
        self.client.publish(self.cfg.availability_topic, "offline", qos=1, retain=True)
        time.sleep(0.5)
        self.client.loop_stop()
        self.client.disconnect()
        LOG.info("Bridge stopped")
        return 0


def main():
    cfg = Config()
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="[%(levelname)s] %(message)s",
        stream=sys.stdout,
    )
    if not cfg.url:
        LOG.error("No AIS-catcher URL configured")
        return 1

    bridge = Bridge(cfg)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: bridge.stop_event.set())
    return bridge.run()


if __name__ == "__main__":
    sys.exit(main())
