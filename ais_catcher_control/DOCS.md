# AIS-catcher Control Panel

Shows an existing remote
[AIS-catcher-control](https://github.com/jvde-github/AIS-catcher-control)
installation in the Home Assistant sidebar.

This add-on is a proxy only. It does not install AIS-catcher or
AIS-catcher-control on the receiver and it does not need access to its SDR.

## Setup

1. Install AIS-catcher and AIS-catcher-control on the remote Linux machine.
2. Confirm that `http://<receiver>:8110` opens from your local network.
3. Set `url` to that address and start this add-on.
4. Open **AIS Control** in the Home Assistant sidebar.

AIS-catcher-control's own password is still required. Its default password is
`admin`; change it when prompted. The password and session are handled directly
by the remote control application and are not stored in the add-on options.

## Options

| Option | Default | Description |
|---|---|---|
| `url` | `http://192.168.1.10:8110` | Remote AIS-catcher-control base URL. |
| `verify_ssl` | `true` | Verify the certificate when `url` uses HTTPS. |

## Statistics

This panel does not create Home Assistant entities. Install **AIS-catcher
Statistics** separately and point it at the same receiver's webviewer, normally
`http://<receiver>:8100`.

## Security

The control UI can start and stop AIS-catcher and, depending on the remote
installation, reboot or halt its host. Do not expose port 8110 directly to the
internet. Home Assistant ingress protects access to this proxy, while the
remote application's password remains a second layer of authentication.

## Troubleshooting

**502 Bad Gateway** means Home Assistant cannot reach `url`. Check the address,
port, firewall and that the `ais-catcher-control` systemd service is running on
the receiver.

If the page opens but a button or menu navigates outside the panel, report the
affected page and the AIS-catcher-control version. The upstream application is
written for `/`, so this add-on translates its links for the Home Assistant
ingress path.
