# Changelog

## 0.1.0

First release. Runs AIS-catcher on Home Assistant itself, with the SDR plugged
into the host, instead of pointing the Statistics add-on at a receiver
somewhere else on the network.

- Manual mode by default: the command line is built from the add-on options —
  device, gain, sample rate, frequency correction, station name and position,
  web viewer, community feed sharing key and UDP targets — plus `extra_args`
  for everything else AIS-catcher accepts.
- Managed mode for handing configuration to AIS-catcher's own dashboard, which
  lands in the sidebar through ingress, bound to localhost inside the add-on so
  that its password is not needed on top of the Home Assistant login. It is not
  in the AIS-catcher release this add-on installs; the add-on checks and says
  so rather than passing on the unrelated error AIS-catcher gives for `-E`
  there.
- The web viewer is published on port 8100 for the Statistics add-on and for
  the rest of the network.
- Community feed sharing is off unless asked for, with `share_community` or a
  `sharing_key`. AIS-catcher shares by default and starts uploading as soon
  as it runs; an add-on should not opt its user into that by saying nothing.
- The plots survive a restart: `/data/stat.bin` is backed up every 10 minutes
  and on shutdown.
- Built from the upstream release package for `aarch64` and `amd64`, so
  installing does not compile anything.
