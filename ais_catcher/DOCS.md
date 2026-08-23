# AIS-catcher Receiver

Runs [AIS-catcher](https://github.com/jvde-github/AIS-catcher) on the Home
Assistant machine itself, with the SDR plugged into it — no second computer, no
Raspberry Pi next to the antenna.

It is the counterpart of the [AIS-catcher Statistics](../ais_catcher_stats)
add-on, not a replacement: this one receives, that one turns what it receives
into Home Assistant entities. Install both to get sensors; install this one
alone if you only want a receiver with a map.

## Requirements

- Home Assistant **OS** or **Supervised** on `aarch64` or `amd64`.
- A supported SDR connected to the machine Home Assistant runs on: an RTL-SDR
  dongle, an AirSpy, a HackRF, a HydraSDR, or a serial receiver such as a
  dAISy. SDRplay is **not** supported — the release packages this add-on is
  built from do not include the driver.
- An antenna. This matters more than anything in the options below.

## Installation

1. Plug the SDR into the Home Assistant machine.
2. Add this repository under **Settings → Add-ons → Add-on store → ⋮ →
   Repositories** and install **AIS-catcher Receiver**. The image is built on
   your device; it downloads the AIS-catcher release package rather than
   compiling it, so this takes about a minute.
3. Open the **Configuration** tab. With one dongle and nothing else to say,
   the defaults are enough; see [Options](#options) for the rest.
4. Start the add-on and open **AIS Receiver** in the sidebar for the map.

The add-on asks for USB access, so Home Assistant shows it as unprotected.
That is the price of talking to a dongle; it does not use `full_access`.

## The two modes

### Manual (default)

`mode: manual` builds an AIS-catcher command line from the options below and
runs that. The configuration lives in the add-on options — in a backup, in a
snapshot, in version control — rather than in a file the program maintains.

The web viewer is always on in this mode, on port 8100, and it is what the
sidebar panel shows. Its plots are backed up to `/data/stat.bin` every ten
minutes, so a restart does not erase the history.

The exact command line is logged at every start. The sharing key is replaced
with `<sharing key>` there, so the log is safe to paste into an issue.

### Managed

`mode: managed` starts AIS-catcher with nothing but `-E`, which brings up its
own dashboard: device, gain, decoder and every output are set from the browser,
the receiver is started and stopped from there, and the settings live in
`/data/config.json`, which AIS-catcher writes itself. None of the other add-on
options are read.

**Managed mode needs a newer AIS-catcher than this add-on installs.** It is not
in the v0.70 release; in that release `-E` means something else entirely. The
add-on asks the binary what it supports and refuses to start with an
explanation rather than passing on a confusing error, so if you select managed
mode and the add-on stops with *"This AIS-catcher does not have managed
mode"*, that is why. Raise `AIS_CATCHER_VERSION` in `build.yaml` and rebuild to
use it.

The dashboard is published on **port 8118 of the Home Assistant host** and asks
you to set a password of its own the first time you open it. It can also be
shown in the sidebar by setting `managed_sidebar: dashboard`. The ingress proxy
makes the dashboard's root-relative API and viewer URLs relative as it serves
them, keeping login, controls, live logs and the embedded viewer inside the
add-on's ingress path.

With `managed_sidebar: web_viewer`, the sidebar instead shows the standalone
web viewer managed mode brings up on the control port plus one.

## Options

Only `mode`, `managed_sidebar` and `log_level` are read in managed mode.

| Option | Default | Description |
|---|---|---|
| `mode` | `manual` | `manual` builds the command line from the options below; `managed` hands configuration to AIS-catcher's own dashboard on port 8118, which needs a newer AIS-catcher than this add-on installs. |
| `managed_sidebar` | `dashboard` | In managed mode, show either the management `dashboard` or the standalone `web_viewer` in the sidebar. Ignored in manual mode. |
| `log_level` | `info` | `debug` prints every decoded message and statistics every 10s instead of every 60s. |

Manual mode only:

| Option | Description |
|---|---|
| `device_index` | Which SDR to use, counting from `0`. Only needed with more than one device. |
| `device_serial` | Serial number of the SDR. Survives replugging in a different order, and wins over `device_index` if both are set. |
| `tuner_gain` | RTL-SDR tuner gain in dB (0–50) or `auto`. |
| `sample_rate` | For example `1536K`, or `288K` on a slow machine. Empty means the device default. |
| `freq_correction` | Crystal error in PPM (−150 to 150). The web viewer shows the drift it measures. |
| `rtlagc` | RTL2832U automatic gain control. |
| `biastee` | Power up the antenna cable for a mast-head amplifier. |
| `station_name` | Name shown in the web viewer. |
| `latitude` / `longitude` | Station position. Both or neither — one on its own is ignored and logged. |
| `share_location` | Show the station and its range on the map. Without it the position is used for statistics only. |
| `web_plugins` | Load the plugins that ship with AIS-catcher (extra map layers, aggregator lookups on the ship card). |
| `share_community` | Upload what the station receives to the [aiscatcher.org](https://aiscatcher.org) community feed, anonymously. **Off by default** — see below. |
| `sharing_key` | Share under your own station at aiscatcher.org instead of anonymously. Setting a key turns sharing on by itself. |
| `udp_targets` | Raw NMEA over UDP, one `host`/`port` per entry — OpenCPN, MarineTraffic, VesselFinder. |
| `extra_args` | Passed to AIS-catcher unchanged. Space separated; quoting is not supported. |

A reasonable starting point for an RTL-SDR is `rtlagc: true` with
`tuner_gain: auto`, and `extra_args: -a 192K` is worth trying with and without.

```yaml
mode: manual
device_index: 0
tuner_gain: auto
rtlagc: true
station_name: Yokohama
latitude: 35.4437
longitude: 139.6380
share_location: true
udp_targets:
  - host: 192.168.1.30
    port: 10110
extra_args: -a 192K
```

## Sharing

AIS-catcher shares reception with the [aiscatcher.org](https://aiscatcher.org)
community feed unless it is told not to, and connects as soon as it starts.
This add-on turns that **off** by default: uploading what your station hears,
and with it a fairly good idea of where you live, should be something you chose
rather than something that happened.

Set `share_community: true` to share anonymously, or `sharing_key` to share
under your own station. Either one turns it on.

In managed mode this option does nothing — sharing is one of the outputs you
configure in AIS-catcher's dashboard, under its own defaults.

## Feeding the Statistics add-on

Install **AIS-catcher Statistics** and set its `url` to the address of this
add-on:

```
http://eb24ddf7-ais-catcher:8100
```

Add-ons reach each other by name on the Supervisor's own network, so this needs
no IP address and keeps working when the host's changes. The name is the
repository's identifier plus the add-on slug with underscores turned into
dashes — `local-ais-catcher` while you are testing a copy in `/addons`. Either
name is on the add-on's own page under *Hostname*.

`http://<your Home Assistant IP>:8100` works too, through the published port.

Do not use `localhost`: each add-on is its own container, so `localhost` there
is the Statistics add-on itself.

Both add-ons put a panel in the sidebar, and they show different things:

- **AIS Receiver** — the selected managed-mode sidebar view (in manual mode,
  always the web viewer).
- **AIS-catcher** — the web viewer, with the vessel trackers and sensors the
  Statistics add-on builds from it.

If you do not want two, turn off **Show in sidebar** on either add-on's page.

## Ports

`8100/tcp` carries the manual-mode web viewer, so that OpenCPN, a browser on
your phone and anything else on the network can reach it. `8118/tcp` carries
the managed-mode dashboard; nothing listens there in manual mode. The host side
of either can be changed under **Network** on the add-on page if something else
already uses that port; the container side is fixed.

The Statistics add-on needs neither — it reaches this add-on by name.

## Restarting on failure

Enable **Watchdog** on the add-on page. AIS-catcher is the add-on's main
process, so if it stops — a dongle that fell off the bus, an unrecoverable USB
error — the container stops with it and Home Assistant starts it again.

## Notes

- Settings are in `/data`, which is included in Home Assistant backups:
  `config.json` in managed mode, `stat.bin` for the plots in manual mode.
- Updating AIS-catcher itself means updating the add-on: the version is pinned
  in `build.yaml` and installed from the upstream release package.
- AIS-catcher is GPL-3.0. This add-on packages it; the program, its source and
  its own documentation are at
  [jvde-github/AIS-catcher](https://github.com/jvde-github/AIS-catcher).
- AIS-catcher is for hobby and research use. It is **not** approved for
  navigation or safety-of-life applications.

## Troubleshooting

**The add-on stops right after starting.** Look at the log. `usb_claim_interface
error -6` means something else already has the dongle — usually the kernel's DVB
driver, or another add-on such as one for rtl_433 or Zigbee. Only one program
can use an SDR at a time.

**No device found.** Check that the dongle is on the Home Assistant machine and
not on a USB hub that lost power, then restart the add-on. A dongle that is
unplugged and plugged back in while the add-on runs is not picked up again;
restart the add-on after replugging.

**Messages, but very few.** This is nearly always the antenna, not the
settings. AIS is at 162 MHz; a whip cut for that band, outside and as high as
possible, is worth more than any gain setting. After that, try `rtlagc` on and
off, and fixed tuner gains between 0 and 50.

**The sidebar panel is empty.** The proxy did not start; the add-on logs
`Could not start the ingress proxy` with the reason underneath, and keeps
receiving regardless. In manual mode the panel is also empty until the receiver
has actually started.

**The Statistics add-on cannot reach it.**
`http://eb24ddf7-ais-catcher:8100/api/stat.json` has to return JSON. In managed
mode the viewer is on the control port plus one instead, so point the
Statistics add-on at `:8119` or set the viewer to 8100 from the dashboard.

**The dashboard shows "Connection Error" in the sidebar.** Confirm that
`managed_sidebar` is `dashboard`, restart the add-on after saving the option,
and check the add-on log for an ingress proxy warning.

**The add-on stops with "This AIS-catcher does not have managed mode".** The
pinned AIS-catcher release does not have it. Set `mode` back to `manual`, or
raise `AIS_CATCHER_VERSION` in `build.yaml` and rebuild.
