# Changelog

## 0.1.3

- Move gzip decompression into a separate internal nginx proxy stage. nginx's
  filter order prevented the 0.1.2 single-stage `gunzip` and `sub_filter`
  combination from rewriting the dashboard, so `/api/status` and `/viewer/`
  still escaped Home Assistant ingress and returned 404.

## 0.1.2

- Decompress the managed dashboard's always-gzipped responses inside the
  ingress proxy before rewriting its root-relative API and viewer URLs. This
  fixes `Connection Error` in the sidebar caused by requests escaping to Home
  Assistant's `/api/status` and returning 404.

## 0.1.1

- Add `managed_sidebar`, allowing managed mode's sidebar panel to show either
  the web viewer (the default) or the management dashboard.
- Rewrite the dashboard's root-relative API and viewer URLs at the ingress
  proxy so its controls, login, event stream and embedded viewer remain under
  Home Assistant's ingress path.

## 0.1.0

First release. Runs AIS-catcher on Home Assistant itself, with the SDR plugged
into the host, instead of pointing the Statistics add-on at a receiver
somewhere else on the network.

- Manual mode by default: the command line is built from the add-on options —
  device, gain, sample rate, frequency correction, station name and position,
  web viewer, community feed sharing key and UDP targets — plus `extra_args`
  for everything else AIS-catcher accepts.
- Managed mode for handing configuration to AIS-catcher's own dashboard, on
  port 8118 of the host and under a password of its own; the sidebar panel
  shows the web viewer it brings up alongside. It is not in the AIS-catcher
  release this add-on installs; the add-on checks and says so rather than
  passing on the unrelated error AIS-catcher gives for `-E` there.
- The web viewer is published on port 8100 for the Statistics add-on and for
  the rest of the network.
- Community feed sharing is off unless asked for, with `share_community` or a
  `sharing_key`. AIS-catcher shares by default and starts uploading as soon
  as it runs; an add-on should not opt its user into that by saying nothing.
- The plots survive a restart: `/data/stat.bin` is backed up every 10 minutes
  and on shutdown.
- Built from the upstream release package for `aarch64` and `amd64`, so
  installing does not compile anything.
