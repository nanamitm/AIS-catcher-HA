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

import requests

try:  # paho-mqtt 2.x
    from paho.mqtt.client import CallbackAPIVersion, Client as MqttClient

    def make_client(client_id):
        return MqttClient(CallbackAPIVersion.VERSION1, client_id=client_id)
except ImportError:  # paho-mqtt 1.x
    from paho.mqtt.client import Client as MqttClient

    def make_client(client_id):
        return MqttClient(client_id=client_id)

from sensors import BINARY_SENSORS, MESSAGE_GROUPS, SENSORS

LOG = logging.getLogger("ais-bridge")

STAT_PATHS = ("/api/stat.json", "/stat.json")
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


def env(name, default=""):
    value = os.environ.get(name, default)
    return value.strip() if isinstance(value, str) else value


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
            self.http_auth = (env("HTTP_USERNAME"), env("HTTP_PASSWORD"))
        self.verify_ssl = env_bool("VERIFY_SSL", True)
        self.mqtt_host = env("MQTT_HOST", "core-mosquitto")
        self.mqtt_port = int(env("MQTT_PORT", "1883"))
        self.mqtt_user = env("MQTT_USER")
        self.mqtt_pass = env("MQTT_PASS")
        self.log_level = env("LOG_LEVEL", "info").upper()

        self.base_topic = "aiscatcher/%s" % self.device_id
        self.state_topic = "%s/state" % self.base_topic
        self.availability_topic = "%s/status" % self.base_topic


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
        self.start_time = None
        self.discovered = False
        self.session = requests.Session()
        self.client = make_client("ais_catcher_stats_%s" % config.device_id)
        if config.mqtt_user:
            self.client.username_pw_set(config.mqtt_user, config.mqtt_pass)
        self.client.will_set(config.availability_topic, "offline", retain=True)

    # --- HTTP -----------------------------------------------------------

    def fetch(self):
        paths = (self.stat_path,) if self.stat_path else STAT_PATHS
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
                continue
            response.raise_for_status()
            if self.stat_path != path:
                LOG.info("Using statistics endpoint %s", path)
                self.stat_path = path
            return response.json()
        raise last_error or RuntimeError("no statistics endpoint responded")

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

    def resolve_start_time(self, run_time):
        """Keep the timestamp stable; only re-anchor on a restart or real drift."""
        now = datetime.now(timezone.utc).replace(microsecond=0)
        candidate = now - timedelta(seconds=run_time)
        if self.start_time is None or abs((candidate - self.start_time).total_seconds()) > 10:
            self.start_time = candidate
        return self.start_time.isoformat()

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
            "identifiers": ["aiscatcher_%s" % self.cfg.device_id],
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
        return "%s/%s/aiscatcher_%s/%s/config" % (
            self.cfg.discovery_prefix, component, self.cfg.device_id, key)

    def publish_discovery(self, stat):
        device = self.device_block(stat)
        count = 0
        for component, key, name, tmpl, unit, dclass, sclass, ecat, icon in self.entities():
            payload = {
                "name": name,
                "unique_id": "aiscatcher_%s_%s" % (self.cfg.device_id, key),
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

    def remove_discovery(self):
        for component, key in [(c, k) for c, k, *_ in self.entities()]:
            self.client.publish(self.discovery_topic(component, key), "", qos=1, retain=True)
        self.client.publish(self.cfg.state_topic, "", qos=1, retain=True)
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
                    self.discovered = True
                self.client.publish(self.cfg.availability_topic, "online", qos=1, retain=True)
                self.client.publish(self.cfg.state_topic, json.dumps(stat), qos=0, retain=True)
                if failures:
                    LOG.info("Recovered contact with %s", self.cfg.url)
                failures = 0
                LOG.debug("Published %s vessels, %.2f msg/s",
                          stat.get("vessel_count", 0), stat.get("msg_rate", 0.0))
            except Exception as err:  # keep the bridge alive on any hiccup
                failures += 1
                self.client.publish(self.cfg.availability_topic, "offline", qos=1, retain=True)
                if failures == 1 or failures % 10 == 0:
                    LOG.warning("Cannot read statistics from %s: %s (attempt %d)",
                                self.cfg.url, err, failures)
            self.stop_event.wait(self.cfg.interval)

        if self.cfg.remove_on_stop:
            self.remove_discovery()
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
