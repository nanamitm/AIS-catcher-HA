"""Entity definitions for the AIS-catcher statistics bridge.

Every entity reads from a single retained JSON state topic, so the templates
below address the normalised payload built by bridge.normalise().  Adding a
sensor means adding a row here -- nothing else changes.
"""

# key, name, value_template, unit, device_class, state_class, entity_category, icon
SENSORS = [
    ("msg_rate", "Message rate",
     "{{ value_json.msg_rate | float(0) | round(2) }}",
     "msg/s", None, "measurement", None, "mdi:speedometer"),
    ("msg_per_minute", "Messages per minute",
     "{{ value_json.last_minute.count | int(0) }}",
     "msg/min", None, "measurement", None, "mdi:message-badge-outline"),
    ("vessel_count", "Vessel count",
     "{{ value_json.vessel_count | int(0) }}",
     "vessels", None, "measurement", None, "mdi:ferry"),
    ("vessel_max", "Vessel count maximum",
     "{{ value_json.vessel_max | int(0) }}",
     "vessels", None, "measurement", "diagnostic", "mdi:ferry"),
    ("vessels_last_hour", "Vessels last hour",
     "{{ value_json.last_hour.vessels | int(0) }}",
     "vessels", None, "measurement", None, "mdi:ferry"),
    ("vessels_last_day", "Vessels last day",
     "{{ value_json.last_day.vessels | int(0) }}",
     "vessels", None, "measurement", None, "mdi:ferry"),

    ("distance_last_hour", "Max distance last hour",
     "{{ value_json.last_hour.dist | float(0) | round(2) }}",
     "nmi", "distance", "measurement", None, None),
    ("distance_last_day", "Max distance last day",
     "{{ value_json.last_day.dist | float(0) | round(2) }}",
     "nmi", "distance", "measurement", None, None),

    ("ppm", "PPM last minute",
     "{{ value_json.last_minute.ppm | float(0) | round(3) }}",
     "ppm", None, "measurement", None, "mdi:sine-wave"),
    ("level_min", "Signal level minimum",
     "{{ value_json.last_minute.level_min | float(0) | round(2) }}",
     "dB", "signal_strength", "measurement", None, None),
    ("level_max", "Signal level maximum",
     "{{ value_json.last_minute.level_max | float(0) | round(2) }}",
     "dB", "signal_strength", "measurement", None, None),

    ("tcp_clients", "Web connections",
     "{{ value_json.tcp_clients | int(0) }}",
     "connections", None, "measurement", "diagnostic", "mdi:lan-connect"),
    ("memory", "Memory use",
     "{{ value_json.memory | int(0) }}",
     "B", "data_size", "measurement", "diagnostic", None),
    ("received", "Received total",
     "{{ value_json.received | int(0) }}",
     "B", "data_size", "total_increasing", "diagnostic", None),
    ("uptime", "Uptime",
     "{{ value_json.start_time }}",
     None, "timestamp", None, "diagnostic", None),

    ("station", "Station",
     "{{ value_json.station | default('unknown', true) }}",
     None, None, None, "diagnostic", "mdi:radio-tower"),
    ("version", "Version",
     "{{ value_json.build_version | default('unknown', true) }}",
     None, None, None, "diagnostic", "mdi:tag-outline"),
    ("build", "Build",
     "{{ value_json.build_describe | default('unknown', true) }}",
     None, None, None, "diagnostic", "mdi:tag-outline"),
    ("build_date", "Build date",
     "{{ value_json.build_date | default('unknown', true) }}",
     None, None, None, "diagnostic", "mdi:calendar"),
    ("device_label", "Receiver device",
     "{{ value_json.device_label | default('unknown', true) }}",
     None, None, None, "diagnostic", "mdi:usb"),
]

# Per channel message counts (A/B/C/D) over the last minute.
for _i, _c in enumerate("ABCD"):
    SENSORS.append((
        "channel_%s" % _c.lower(),
        "Channel %s msg/min" % _c,
        "{{ value_json.channel.%s | int(0) }}" % _c,
        "msg/min", None, "measurement", None, "mdi:antenna",
    ))

# Optional message-group breakdown, mirroring the grouping used in issue #376.
MESSAGE_GROUP_SENSORS = [
    ("msg_base_station", "Base station msg/min", "base"),
    ("msg_sar_aircraft", "SAR aircraft msg/min", "sar"),
    ("msg_aid_to_navigation", "Aid-to-Navigation msg/min", "aton"),
    ("msg_long_range", "Long range msg/min", "long_range"),
    ("msg_binary", "Binary msg/min", "binary"),
    ("msg_safety", "Safety related msg/min", "safety"),
    ("msg_position", "Position report msg/min", "position"),
    ("msg_static", "Static data msg/min", "static"),
    ("msg_other", "Other msg/min", "other"),
]

MESSAGE_GROUPS = [
    (key, name,
     "{{ value_json.msg_group.%s | int(0) }}" % group,
     "msg/min", None, "measurement", None, "mdi:message-text-outline")
    for key, name, group in MESSAGE_GROUP_SENSORS
]

# key, name, value_template (must render ON/OFF), device_class, entity_category
BINARY_SENSORS = [
    ("engine_running", "Engine running",
     "{{ 'ON' if value_json.engine_running else 'OFF' }}",
     "running", "diagnostic"),
    ("sharing", "Community sharing",
     "{{ 'ON' if value_json.sharing else 'OFF' }}",
     None, "diagnostic"),
]


# --- per vessel -----------------------------------------------------------
# These read the payload published to aiscatcher/<device_id>/vessel/<mmsi>.
# AIS-catcher omits fields it has not received yet, and the bridge drops nulls,
# so every optional value falls back through `default('unknown')` - which Home
# Assistant renders as the unknown state.  `default` without `true` only fires
# on a missing key, so a legitimate 0 (speed, bearing) survives.
VESSEL_SENSORS = [
    ("speed", "Speed",
     "{{ value_json.speed | default('unknown') }}",
     "kn", "speed", "measurement", None, "mdi:speedometer"),
    ("course", "Course over ground",
     "{{ value_json.cog | default('unknown') }}",
     "°", None, "measurement", None, "mdi:compass"),
    ("heading", "Heading",
     "{{ value_json.heading | default('unknown') }}",
     "°", None, "measurement", None, "mdi:compass-outline"),
    ("distance", "Distance",
     "{{ value_json.distance | default('unknown') }}",
     "nmi", "distance", "measurement", None, None),
    ("bearing", "Bearing",
     "{{ value_json.bearing | default('unknown') }}",
     "°", None, "measurement", None, "mdi:compass-rose"),
    ("status", "Navigation status",
     "{{ value_json.status_text | default('unknown') }}",
     None, None, None, None, "mdi:ferry"),
    ("destination", "Destination",
     "{{ value_json.destination | default('unknown') }}",
     None, None, None, None, "mdi:map-marker-path"),
    ("last_signal", "Last signal",
     "{{ value_json.last_signal_time | default('unknown') }}",
     None, "timestamp", None, "diagnostic", None),
    ("level", "Signal level",
     "{{ value_json.level | default('unknown') }}",
     "dB", "signal_strength", "measurement", "diagnostic", None),
    ("messages", "Messages received",
     "{{ value_json.count | default('unknown') }}",
     "msg", None, "total_increasing", "diagnostic", "mdi:message-text-outline"),
]

# AIS navigation status (message types 1/2/3), field "status".
NAV_STATUS = {
    0: "Under way using engine",
    1: "At anchor",
    2: "Not under command",
    3: "Restricted manoeuvrability",
    4: "Constrained by draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in fishing",
    8: "Under way sailing",
    9: "Reserved (high speed craft)",
    10: "Reserved (wing in ground)",
    11: "Towing astern",
    12: "Pushing ahead",
    13: "Reserved",
    14: "AIS-SART active",
    # The default a transponder sends when nothing was set, so it is by far the
    # most common value on small craft.
    15: "Undefined",
}

# Ship type ranges, field "shiptype".
SHIP_TYPES = [
    (20, 29, "Wing in ground"),
    (30, 30, "Fishing"),
    (31, 32, "Towing"),
    (33, 33, "Dredging"),
    (34, 34, "Diving operations"),
    (35, 35, "Military operations"),
    (36, 36, "Sailing"),
    (37, 37, "Pleasure craft"),
    (40, 49, "High speed craft"),
    (50, 50, "Pilot vessel"),
    (51, 51, "Search and rescue"),
    (52, 52, "Tug"),
    (53, 53, "Port tender"),
    (54, 54, "Anti-pollution"),
    (55, 55, "Law enforcement"),
    (58, 58, "Medical transport"),
    (60, 69, "Passenger"),
    (70, 79, "Cargo"),
    (80, 89, "Tanker"),
    (90, 99, "Other"),
]
