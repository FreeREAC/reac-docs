# Native AES67 firmware for REAC stageboxes — feasibility

Part of [FreeREAC](https://github.com/FreeREAC). Distilled from a 2026 feasibility
study. Detailed device-firmware reverse-engineering is kept private per project
policy; this records only the architectural conclusion and the path that follows
from it.

## The question

Can we write custom **firmware** that makes a Roland REAC stagebox natively
**receive AES67** instead of REAC — turning the box into a vendor-neutral
network-audio node?

## Verdict: infeasible *as a firmware project* (high confidence)

Not "hard" — structurally impossible to do by reflashing firmware, for one
decisive reason:

**The audio datapath is not in the CPU you would reflash — it is in the box's FPGA.**

In these stageboxes the FPGA owns the entire audio path: the codec I/O, the
word/sample clock, the REAC framing and counter, the link-check, and the
REAC↔AES3 crossbar. The CPU is **supervisory only** — it runs the
connection/clock state machine and reaches the audio engine solely *through* the
FPGA; it never touches a sample or a codec register. So custom CPU firmware has
**no path to retarget the audio** to AES67.

Making the box AES67 therefore means **replacing the FPGA design**, not the
firmware — a clean-room FPGA + PCB-level effort (codec masters + a
PTP-disciplined media clock + an RTP/L24 packetizer + SAP/SDP), i.e. building a
new device, not flashing one. The existing FPGA design is proprietary and not
reversible to a new media-access layer.

Several independent factors reinforce the verdict:

- **Fast Ethernet, not gigabit.** REAC at 96 kHz / 40 ch already ~saturates a
  100 Mbit link; AES67 multichannel practice assumes gigabit.
- **No hardware PTP.** AES67 media-clock accuracy needs hardware timestamping
  (a PTP hardware clock); the stagebox silicon has none, and software PTP is
  monitoring-grade only.
- **Clock-domain bridging needs genlock.** A Roland word clock and a PTP
  grandmaster free-run at tens of ppm; without one house clock you get drift and
  periodic clicks unless you resample (ASRC).
- **Reflash risk.** The update path has no signed-image rollback — bricking
  irreplaceable show gear, with no community precedent.

## The path that actually works

You do **not** need to touch the stagebox. Two pieces, both already built in the
FreeREAC / openmixer line, deliver the "generic open node" outcome with the
stagebox untouched:

1. **openmixer as the REAC master.** `reac-pw` is a full REAC
   **transmitter / master**: it builds and transmits valid REAC frames and runs
   the master handshake, so openmixer can **drive the stageboxes natively over
   REAC** — the stagebox stays a dumb REAC I/O endpoint while openmixer owns the
   DSP (PipeWire + LV2), with full insert freedom.
2. **An external REAC↔AES67 bridge.**
   [`reac-aes67`](https://github.com/FreeREAC/reac-aes67) converts the stream and
   **publishes the stagebox as an AES67 endpoint** (SAP/SDP) — which then
   interops with **Dante** (via its AES67 mode) and **PipeWire** (via RTP /
   `module-rtp`). AES67 is just constrained RTP, so this is equally the answer for
   plain PipeWire-to-PipeWire links.

### The bridge as a small appliance

Package the bridge in a dedicated box that presents each REAC stagebox as an
AES67 (→ Dante / → PipeWire) node:

| Board | Clocking | Use |
|-------|----------|-----|
| **Raspberry Pi 4** (real gigabit + USB3 for a 2nd NIC) | software PTP + in-bridge ASRC (no PTP hardware clock) | monitoring-grade — IEMs, wedges, monitor feeds |
| **x86 mini-PC with Intel i210 / i225 / i226** | **hardware PTP** | sample-accurate / Dante-strict; the i226 box doubles as the TSN/ETF egress router |

*Not* a Pi Zero — it has no wired Ethernet. A Pi 3 works only as a casual
low-channel floor: its Ethernet is USB-attached (shared bus, added jitter).

## What still needs a rig to confirm

For strict AES67 / Dante interop the bridge's three open unknowns must be closed
on a test rig:

1. live **PTPv2 slave lock** to a real grandmaster under software timestamping;
2. **Dante Controller** accepting the SDP (RFC 7273 strictness, payload type,
   sendonly / recvonly);
3. a **genlock soak** confirming drift stays bounded — i.e. genlock the Roland
   word clock and the PTP grandmaster to one house clock, or accept
   monitoring-grade software-PTP + ASRC.

For sample-accurate multi-source alignment the bridge endpoint belongs on a
**PTP-hardware-clock-capable host** (i210 / i225 / i226 class) rather than a
router SoC.

## See also

- [findings.md](findings.md) — the Wi-Fi REAC investigation and the i226 / TSN
  hardware wall.
- [rig-recipe.md](rig-recipe.md) — building the two-router REAC bridge.
- [reac-protocol](https://github.com/FreeREAC/reac-protocol),
  [reac-aes67](https://github.com/FreeREAC/reac-aes67), `reac-pw`.
