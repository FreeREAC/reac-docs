# reac-docs

Engineering **findings** and the **rig recipe** behind FreeREAC — the distilled
result of getting Roland REAC to run across a 5 GHz Wi-Fi link, and how the pieces
(transport + re-pacer + converter) fit together.

Part of [FreeREAC](https://github.com/FreeREAC) — *REAC Exposed Audio Communications*.

## Documents

- **[findings.md](findings.md)** — the investigation, distilled: why Wi-Fi breaks
  REAC, why a software re-pacer is the right first move, the clock-recovery problem
  and how it was resolved, and where software hits a hard wall — and what hardware
  (i226 / TSN) fixes it.
- **[rig-recipe.md](rig-recipe.md)** — how to build a two-router Wi-Fi REAC bridge:
  the transport fabric (gretap + VLAN trunk), where the re-pacer goes and why
  de-jitter is directional, buffer sizing against the link-status budget, and the
  netifd/UCI persistence traps.

For the on-wire protocol itself, see
[reac-protocol](https://github.com/FreeREAC/reac-protocol); for the raw working
material these are distilled from, [reac-lab](https://github.com/FreeREAC/reac-lab).

## The FreeREAC family

| repo | what it is |
|---|---|
| [reac-transport](https://github.com/FreeREAC/reac-transport) | carry REAC across an OpenWrt network — VLAN trunk or gretap tunnel |
| [reac-repacer](https://github.com/FreeREAC/reac-repacer) | de-jitter a REAC stream over a bursty link (Wi-Fi) |
| [reac-aes67](https://github.com/FreeREAC/reac-aes67) | terminate REAC into AES67 (RTP L24) |
| [reac-protocol](https://github.com/FreeREAC/reac-protocol) | the REAC protocol reference |
| [reac-tools](https://github.com/FreeREAC/reac-tools) | REAC traffic analysis + diagnostics |
| [reac-label](https://github.com/FreeREAC/reac-label) | Roland mixer → channel-name labeller |
| [reac-lab](https://github.com/FreeREAC/reac-lab) | the raw working material |

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
