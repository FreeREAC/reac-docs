# reac-docs

User guides for FreeREAC: how to put REAC audio to work with the applications you
already run.

Part of [FreeREAC](https://github.com/FreeREAC) — *REAC Exposed Audio Communications*.

## Guides

- **[obs-studio.md](obs-studio.md)** — getting REAC channels into OBS Studio: take
  them from `reac-pw`'s PipeWire nodes (directly via a PipeWire-audio plugin, or
  through `pipewire-pulse` without one), the recipe for choosing 8 of a 16- or
  32-channel box's channels (the ceiling every OBS source has), and why FreeREAC
  ships this guide rather than a plugin that binds the wire itself. Includes the
  survey of the existing `obs-h8819-source` plugin and the three patches we owe
  it upstream.

For the on-wire protocol itself, see
[reac-protocol](https://github.com/FreeREAC/reac-protocol).

## The FreeREAC family

| repo | what it is |
|---|---|
| [reac-transport](https://github.com/FreeREAC/reac-transport) | carry REAC across an OpenWrt network — VLAN trunk or gretap tunnel |
| [reac-repacer](https://github.com/FreeREAC/reac-repacer) | de-jitter a REAC stream over a bursty link (Wi-Fi) |
| [reac-aes67](https://github.com/FreeREAC/reac-aes67) | terminate REAC into AES67 (RTP L24) |
| [reac-protocol](https://github.com/FreeREAC/reac-protocol) | the REAC protocol reference |
| [reac-tools](https://github.com/FreeREAC/reac-tools) | REAC traffic analysis + diagnostics |
| [reac-label](https://github.com/FreeREAC/reac-label) | Roland mixer → channel-name labeller |
| [reac-lab](https://github.com/FreeREAC/reac-lab) | REAC wire captures |

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
