import json, os, sys, types

# --- stub paho-mqtt -------------------------------------------------------
paho = types.ModuleType("paho")
mqtt = types.ModuleType("paho.mqtt")
client_mod = types.ModuleType("paho.mqtt.client")


class Client:
    def __init__(self, *a, **kw):
        self.published = []

    def username_pw_set(self, *a):
        pass

    def will_set(self, *a, **kw):
        pass

    def connect(self, *a, **kw):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload))


client_mod.Client = Client
mqtt.client = client_mod
paho.mqtt = mqtt
sys.modules["paho"] = paho
sys.modules["paho.mqtt"] = mqtt
sys.modules["paho.mqtt.client"] = client_mod

os.environ.update({
    "AIS_URL": "http://localhost:8100",
    "SCAN_INTERVAL": "30",
    "DEVICE_NAME": "AIS-catcher",
    "DEVICE_ID": "aiscatcher",
    "MESSAGE_TYPE_SENSORS": "true",
    "MQTT_HOST": "core-mosquitto",
    "MQTT_PORT": "1883",
    "MQTT_USER": "addons",
    "MQTT_PASS": "x",
})

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "ais_catcher_stats"))
import bridge  # noqa: E402

STAT = {
    "total": {"count": 100000, "msg": [1] * 27, "channel": [1, 2, 3, 4]},
    "session": {"count": 5000},
    "last_day": {"count": 40000, "vessels": 320, "dist": 41.2},
    "last_hour": {"count": 3000, "vessels": 120, "dist": 38.51234},
    "last_minute": {
        "count": 57, "vessels": 30, "dist": 22.4, "ppm": 1.23,
        "level_min": 22.5, "level_max": 44.1,
        "channel": [30, 27],                       # only A/B present
        # furthest message heard per compass sector, per channel
        "radar_a": [0, 8.4, 11.2, 0, 0, 12.5, 0, 0],
        "radar_b": [0, 0, 3.0, 0, 0, 0, 0],        # one sector short
        "msg": [20, 5, 8, 3, 2, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 0, 4, 0, 0, 2],
    },
    "msg_rate": 0.95, "vessel_count": 31, "vessel_max": 55, "tcp_clients": 2,
    "build_version": "v0.65", "build_describe": "v0.65-abcdef", "build_date": "Jan 1 2026",
    "run_time": "7265", "memory": 41943040, "received": 123456789,
    # AIS-catcher reports these per receiver, i.e. as arrays (see issue report
    # from a real install: model: ['AIS engine v1 base'], serial: ['00000060'])
    "station": "Motorhome", "product": ["RTL2838UHIDIR"], "serial": ["00000060"],
    "model": ["AIS engine v1 base"], "vendor": ["Realtek"],
    "sample_rate": ["1536K"], "device_label": ["AIS 00000060"],
    "engine_running": True, "sharing": False,
    "sharing_link": "https://www.aiscatcher.org/?&zoom=10&lat=35.4&lon=139.6",
    "station_link": ["https://www.marinetraffic.com/en/ais/details/stations/1"],
    "os": {"x": 1}, "hardware": {"y": 2}, "outputs": [1, 2, 3],
}

cfg = bridge.Config()
b = bridge.Bridge(cfg)
b.fetch = lambda: json.loads(json.dumps(STAT))

norm = b.normalise(b.fetch())
print("channel:", norm["channel"])
print("msg_group:", norm["msg_group"])
print("memory/received:", norm["memory"], norm["received"])
print("start_time:", norm["start_time"], "run_time:", norm["run_time"])
assert norm["channel"] == {"A": 30, "B": 27, "C": 0, "D": 0}
assert sum(norm["msg_group"].values()) == sum(norm["last_minute"]["msg"])
assert norm["msg_group"]["base"] == 3 and norm["msg_group"]["aton"] == 2
assert norm["msg_group"]["position"] == 20 + 5 + 8 + 4
assert "os" not in norm and "outputs" not in norm
assert len(norm["last_minute"]["msg"]) == 27

# coverage: sectors 1, 2 and 5 heard something, and the shorter B array must
# not truncate the result
print("coverage:", norm["coverage_sectors"], norm["coverage"])
assert norm["coverage_sectors"] == 3, norm["coverage"]
assert norm["coverage"]["sectors"] == 8 and norm["coverage"]["degrees"] == 45.0
assert norm["coverage"]["reach"][2] == 11.2   # max of A 11.2 and B 3.0
assert bridge.Bridge.coverage({})["coverage_sectors"] == 0
assert bridge.Bridge.coverage({"radar_a": "nonsense"})["coverage"]["reach"] == []

# old-style human readable received string
assert bridge.parse_size("117.7 MB") == int(117.7 * 1024 ** 2)
assert bridge.parse_size(12345) == 12345
assert bridge.parse_size("512 B") == 512
assert bridge.parse_size(None) == 0

# stable start_time across polls
t1 = b.resolve_start_time(7265)
t2 = b.resolve_start_time(7268)
assert t1 == t2, (t1, t2)
assert b.resolve_start_time(5) != t1

# per-receiver arrays must be flattened to strings before anything sees them
assert norm["model"] == "AIS engine v1 base", norm["model"]
assert norm["serial"] == "00000060", norm["serial"]
assert norm["device_label"] == "AIS 00000060", norm["device_label"]
assert bridge.scalarise(["RTL-SDR", "SDRplay"]) == "RTL-SDR, SDRplay"
assert bridge.scalarise([]) == ""
assert bridge.scalarise("plain") == "plain"

b.publish_discovery(norm)
configs = [(t, json.loads(p)) for t, p in b.client.published if t.endswith("/config")]

# attributes ride along on the entity they belong to, from the same topic
attributed = {c["unique_id"].rsplit("_", 1)[-1]: c for _, c in configs
              if "json_attributes_topic" in c}
assert set(attributed) == {"coverage", "sharing"}, sorted(attributed)
for c in attributed.values():
    assert c["json_attributes_topic"] == c["state_topic"]
print("entities:", len(configs))
ids = [c["unique_id"] for _, c in configs]
assert len(ids) == len(set(ids)), "duplicate unique_id"
devices = {json.dumps(c["device"], sort_keys=True) for _, c in configs}
assert len(devices) == 1, "entities not on one device"
print("device:", next(iter(devices)))

# HA rejects the whole discovery message unless every device value is a string
device = configs[0][1]["device"]
for field, value in device.items():
    if field == "identifiers":
        assert isinstance(value, list) and all(isinstance(v, str) for v in value), field
    else:
        assert isinstance(value, str), "device.%s is %s, not a string" % (field, type(value))

# render every template with Jinja to be sure they resolve against the payload
try:
    from jinja2 import Environment
except ImportError:
    print("jinja2 missing - template rendering skipped")
else:
    env = Environment()
    env.filters.setdefault("float", lambda v, d=0.0: float(v) if str(v).replace('.', '', 1).replace('-', '', 1).isdigit() else d)
    for topic, c in configs:
        out = env.from_string(c["value_template"]).render(value_json=norm)
        assert out.strip() != "", topic
    print("all %d templates rendered" % len(configs))

for topic, c in configs[:6]:
    print(" -", c["object_id"], "=", c["value_template"])
print("OK")

# --- vessel trackers ------------------------------------------------------

SHIPS = {
    "count": 3,
    "station": {"lat": 35.44, "lon": 139.64, "mmsi": 0, "gps": False},
    "ships": [
        {   # fully populated, moored ferry
            "mmsi": 219025528, "lat": 35.4512, "lon": 139.6431,
            "distance": 1.83, "bearing": 214.0, "level": 32.5, "count": 811,
            "ppm": 0.7, "heading": 91, "cog": 88.4, "speed": 12.3,
            "shiptype": 60, "status": 5, "shipname": "DBB ASTERIX",
            "destination": "YOKOHAMA", "callsign": "OXYZ2", "imo": 9257157,
            "last_signal": 12, "country": "DK", "draught": 5.4,
            "to_bow": 120, "to_stern": 30, "to_port": 12, "to_starboard": 13,
            "eta_month": 3, "eta_day": 14, "eta_hour": 9, "eta_minute": 30,
        },
        {   # seen, but position and most dynamic data still unknown
            "mmsi": 431000123, "lat": None, "lon": None,
            "distance": None, "bearing": None, "count": 3,
            "shiptype": 70, "status": 0, "last_signal": 40,
        },
        {   # heard once, long ago
            "mmsi": 999000111, "lat": 35.1, "lon": 139.1, "count": 1,
            "last_signal": 7200,
        },
    ],
    "error": False,
}

os.environ["VESSELS"] = json.dumps([
    {"mmsi": 219025528, "name": "DBB Asterix"},
    {"mmsi": 431000123},
    {"mmsi": 999000111, "name": "Rare visitor"},
    {"mmsi": 111222333, "name": "Never heard"},
    {"mmsi": "not a number"},          # dropped with a warning
    {"mmsi": 219025528, "name": "dup"},  # dropped as a duplicate
])
os.environ["VESSEL_TIMEOUT"] = "30"   # minutes

cfg = bridge.Config()
assert [v["mmsi"] for v in cfg.vessels] == [219025528, 431000123, 999000111, 111222333]
assert cfg.vessel_timeout == 1800

# `bashio::config` prints the elements of a list option rather than the list,
# so one configured vessel used to reach the bridge as a bare object and every
# tracker silently disappeared.  All three shapes must parse.
one = '{"mmsi": 431600190, "name": "DAI18DAIKYOU-MARU"}'
assert bridge.parse_vessels(one) == [{"mmsi": 431600190, "name": "DAI18DAIKYOU-MARU"}]
assert [v["mmsi"] for v in bridge.parse_vessels(one + '\n{"mmsi": 219025528}')] == \
    [431600190, 219025528]
assert bridge.parse_vessels('[%s]' % one)[0]["mmsi"] == 431600190
assert bridge.parse_vessels("") == [] and bridge.parse_vessels(None) == []
assert bridge.parse_vessels("not json") == []
print("VESSELS OPTION PARSING OK")

v = bridge.Bridge(cfg)
v.publish_vessels(json.loads(json.dumps(SHIPS)))

published = dict(v.client.published)
vessel_configs = [(t, json.loads(p)) for t, p in v.client.published
                  if t.endswith("/config") and "aiscatcher_vessel_" in t]
print("vessel entities:", len(vessel_configs))
assert len(vessel_configs) == 4 * (
    len(bridge.VESSEL_SENSORS) + len(bridge.VESSEL_BINARY_SENSORS) + 1)

# The in-range flag must survive a ship leaving: it reads the vessel status
# topic as its state and the *bridge* availability, so it reports off instead
# of going unavailable with the rest of the vessel's entities.
in_range = [c for t, c in vessel_configs if t.endswith("/in_range/config")]
assert len(in_range) == 4
for c in in_range:
    assert c["state_topic"].endswith("/status"), c["state_topic"]
    assert (c["payload_on"], c["payload_off"]) == ("online", "offline")
    assert c["availability_topic"] == "aiscatcher/aiscatcher/status", c["availability_topic"]

# one tracker per vessel, all linked to the receiver device
trackers = [c for t, c in vessel_configs if "/device_tracker/" in t]
assert len(trackers) == 4
for tracker in trackers:
    assert tracker["source_type"] == "gps"
    assert tracker["device"]["via_device"] == "aiscatcher_aiscatcher"
    assert tracker["json_attributes_topic"].endswith("/position")

names = {c["device"]["identifiers"][0]: c["device"]["name"] for _, c in vessel_configs}
print("names:", names)
assert names["aiscatcher_vessel_219025528"] == "DBB Asterix"   # configured name wins
assert names["aiscatcher_vessel_431000123"] == "MMSI 431000123"  # no name known yet
assert names["aiscatcher_vessel_111222333"] == "Never heard"

# device metadata comes from the ship report
ferry = [c for _, c in vessel_configs if c["device"]["identifiers"][0].endswith("219025528")][0]
assert ferry["device"]["model"] == "Passenger", ferry["device"]
assert ferry["device"]["serial_number"] == "IMO 9257157"
for field, value in ferry["device"].items():
    if field != "identifiers":
        assert isinstance(value, str), field

# availability: fresh -> online, stale or unseen -> offline
assert published["aiscatcher/aiscatcher/vessel/219025528/status"] == "online"
assert published["aiscatcher/aiscatcher/vessel/431000123/status"] == "online"
assert published["aiscatcher/aiscatcher/vessel/999000111/status"] == "offline"  # 2h old
assert published["aiscatcher/aiscatcher/vessel/111222333/status"] == "offline"  # not seen

# position is only published when there is one
assert "aiscatcher/aiscatcher/vessel/219025528/position" in published
assert "aiscatcher/aiscatcher/vessel/431000123/position" not in published
position = json.loads(published["aiscatcher/aiscatcher/vessel/219025528/position"])
assert position == {"latitude": 35.4512, "longitude": 139.6431, "gps_accuracy": 0}

state = json.loads(published["aiscatcher/aiscatcher/vessel/219025528"])
print("vessel state:", {k: state[k] for k in ("shipname", "status_text", "shiptype_text",
                                              "speed", "last_signal_time")})
assert state["status_text"] == "Moored"
assert state["shiptype_text"] == "Passenger"

# static report: hull size is the sum of the antenna offsets, ETA gets a year
assert state["length"] == 150 and state["beam"] == 25
assert state["country"] == "DK" and state["draught"] == 5.4
assert state["eta"].startswith(("2026-03-14T09:30", "2027-03-14T09:30")), state["eta"]

from datetime import datetime, timezone  # noqa: E402

# the year picked is the one closest to now, across the new year boundary
dec = datetime(2026, 12, 28, 12, 0, tzinfo=timezone.utc)
assert bridge.eta_time({"eta_month": 1, "eta_day": 4, "eta_hour": 6,
                        "eta_minute": 0}, dec).startswith("2027-01-04")
assert bridge.eta_time({"eta_month": 12, "eta_day": 30, "eta_hour": 6,
                        "eta_minute": 0}, dec).startswith("2026-12-30")
# "not available" is month 0 / day 0 / hour 24 / minute 60, and 31 February
# must not raise
for bad in ({"eta_month": 0, "eta_day": 4, "eta_hour": 6, "eta_minute": 0},
            {"eta_month": 3, "eta_day": 0, "eta_hour": 6, "eta_minute": 0},
            {"eta_month": 3, "eta_day": 4, "eta_hour": 24, "eta_minute": 0},
            {"eta_month": 3, "eta_day": 4, "eta_hour": 6, "eta_minute": 60},
            {"eta_month": 2, "eta_day": 31, "eta_hour": 6, "eta_minute": 0},
            {}):
    assert bridge.eta_time(bad, dec) is None, bad

# a ship that reports no dimensions must not become a 0 m vessel
assert bridge.hull_size({"to_bow": 0, "to_stern": 0}, "to_bow", "to_stern") is None
assert bridge.hull_size({"to_bow": 10}, "to_bow", "to_stern") is None
assert "lat" not in json.loads(published["aiscatcher/aiscatcher/vessel/431000123"])

# a vessel keeps its discovery once published, and is not republished per poll
before = len([t for t, _ in v.client.published if t.endswith("/config")])
v.publish_vessels(json.loads(json.dumps(SHIPS)))
after = len([t for t, _ in v.client.published if t.endswith("/config")])
assert before == after, "discovery was republished unnecessarily"

# timestamps must not jitter between polls
again = json.loads(dict(v.client.published)["aiscatcher/aiscatcher/vessel/219025528"])
assert again["last_signal_time"] == state["last_signal_time"]

# A missing value must render as "None", the only payload the MQTT integration
# turns into the unknown state.  The literal "unknown" is rejected on a numeric
# or timestamp sensor and logs an error on every poll.
assert not any("unknown" in tmpl for _, _, tmpl, *_ in bridge.VESSEL_SENSORS)

try:
    from jinja2 import Environment
except ImportError:
    pass
else:
    env = Environment()
    sparse = json.loads(published["aiscatcher/aiscatcher/vessel/431000123"])
    for topic, c in vessel_configs:
        if "value_template" not in c:
            continue
        env.from_string(c["value_template"]).render(value_json=state)
        out = env.from_string(c["value_template"]).render(value_json=sparse)
        key = topic.rsplit("/", 2)[1]
        if key in ("heading", "speed", "distance", "bearing", "level", "destination"):
            assert out == "None", (key, out)   # not "unknown", not ""
    # a real 0 must survive the fallback
    assert env.from_string(dict(
        (k, t) for k, _, t, *_ in bridge.VESSEL_SENSORS)["speed"]
    ).render(value_json={"speed": 0}) == "0"
    print("all vessel templates rendered, including the sparse ship")

print("VESSELS OK")

# --- everything in range --------------------------------------------------

os.environ["NEARBY_RADIUS"] = "2"
f = bridge.Bridge(bridge.Config())
fleet = f.fleet_payload(json.loads(json.dumps(SHIPS)))
print("fleet:", fleet)
assert fleet["total"] == 3
assert fleet["within"] == 1, fleet          # only the ferry at 1.83 nmi
assert fleet["radius"] == 2
assert fleet["nearest"]["name"] == "DBB ASTERIX"   # the broadcast name, not the option
assert fleet["nearest"]["distance"] == 1.83
assert fleet["nearest"]["shiptype"] == "Passenger"

# a ship without a distance cannot be the nearest one, and no ship at all
# leaves the sensor unknown rather than reporting a wrong vessel
assert "nearest" not in f.fleet_payload({"ships": [{"mmsi": 1, "lat": 1}]})
assert f.fleet_payload({"ships": []})["within"] == 0

f.publish_fleet_discovery(norm)
fleet_keys = {key for key, *_ in bridge.FLEET_SENSORS}
fleet_configs = [json.loads(p) for t, p in f.client.published
                 if t.endswith("/config") and t.rsplit("/", 2)[1] in fleet_keys]
assert len(fleet_configs) == len(bridge.FLEET_SENSORS)
for c in fleet_configs:
    assert c["state_topic"] == "aiscatcher/aiscatcher/fleet"
    assert c["device"]["identifiers"] == ["aiscatcher_aiscatcher"]   # the receiver
nearest = [c for c in fleet_configs if c["unique_id"].endswith("nearest_vessel")][0]
assert nearest["json_attributes_topic"] == "aiscatcher/aiscatcher/fleet"

# ships.json is only fetched when something actually needs it
os.environ["FLEET_SENSORS"] = "false"
os.environ["VESSELS"] = "[]"
assert bridge.Config().needs_ships is False
os.environ["FLEET_SENSORS"] = "true"
assert bridge.Config().needs_ships is True

try:
    from jinja2 import Environment
except ImportError:
    pass
else:
    env = Environment()
    empty = {"total": 0, "within": 0, "radius": 2}      # nothing in range at all
    for key, _, tmpl, *_ in bridge.FLEET_SENSORS:
        assert env.from_string(tmpl).render(value_json=fleet) != ""
        # stepping into a missing object raises rather than falling back, which
        # in Home Assistant means an error on every poll and a stuck state
        assert env.from_string(tmpl).render(value_json=empty) in ("None", "0")

    # every attributes template has to survive a payload that carries none of
    # the fields it names, and still render a JSON object
    from sensors import SENSOR_ATTRIBUTES                # noqa: E402
    for key, tmpl in SENSOR_ATTRIBUTES.items():
        for payload in (norm, fleet, empty, {}):
            out = env.from_string(tmpl).render(value_json=payload)
            assert isinstance(json.loads(out), dict), (key, out)
    print("all attribute templates rendered")
print("FLEET OK")

# --- the receiver on the map ----------------------------------------------

s = bridge.Bridge(bridge.Config())
s.device = {"identifiers": ["aiscatcher_aiscatcher"], "name": "AIS-catcher"}
s.publish_station(json.loads(json.dumps(SHIPS)))
station = dict(s.client.published)
assert json.loads(station["aiscatcher/aiscatcher/position"]) == {
    "latitude": 35.44, "longitude": 139.64, "gps_accuracy": 0}
tracker = json.loads(station[
    "homeassistant/device_tracker/aiscatcher_aiscatcher/station_location/config"])
assert tracker["source_type"] == "gps"
assert tracker["device"]["identifiers"] == ["aiscatcher_aiscatcher"]

# the discovery is written once, not on every poll
before = len(s.client.published)
s.publish_station(json.loads(json.dumps(SHIPS)))
assert len(s.client.published) == before + 1

# 0/0 is a real coordinate off Africa, so a receiver without a position must
# not end up there
blank = bridge.Bridge(bridge.Config())
blank.publish_station({"station": {"lat": 0, "lon": 0}})
blank.publish_station({"station": {}})
blank.publish_station({})
assert blank.client.published == [], blank.client.published
print("STATION OK")

# a vessel that goes out of range keeps the name it was discovered with
SPARSE = json.loads(json.dumps(SHIPS))
SPARSE["ships"][1]["shipname"] = "KAIYO MARU"
v.publish_vessels(SPARSE)
count_after_name = len([t for t, _ in v.client.published if t.endswith("/config")])
assert v.vessel_names[431000123] == "KAIYO MARU", v.vessel_names[431000123]

v.publish_vessels({"ships": []})          # every vessel out of range
assert v.vessel_names[431000123] == "KAIYO MARU", "name downgraded when out of range"
assert len([t for t, _ in v.client.published if t.endswith("/config")]) == count_after_name
assert dict(v.client.published)["aiscatcher/aiscatcher/vessel/219025528/status"] == "offline"
print("NAME PERSISTENCE OK")
