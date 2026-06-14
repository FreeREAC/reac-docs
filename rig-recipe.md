# The two-router Wi-Fi REAC rig recipe

How the three pieces — [reac-transport](https://github.com/FreeREAC/reac-transport),
[reac-repacer](https://github.com/FreeREAC/reac-repacer), and
[reac-aes67](https://github.com/FreeREAC/reac-aes67) — fit on a two-router Wi-Fi REAC
bridge. Roles, not host names: a **master-side router** (faces the mixer) and a
**box-side router** (faces the stageboxes), joined by a 5 GHz WDS. The *why* behind
each choice is in [findings.md](findings.md).

## Transport fabric

- **Underlay:** 5 GHz WDS, one router AP and one STA.
- **Tunnel:** a point-to-point **gretap** over the WDS (peer A ↔ peer B).
- **REAC rings** ride as **802.1q VLANs** (one VID per ring, e.g. `11`=A, `12`=B,
  `13`=C) tagged across the gretap, bridged into a VLAN-filtering `br-lan` with the
  matching access port per ring (PVID untagged).
- **MTU:** the inner REAC broadcast is ~1496 B, so keep the gretap at MTU 1500 and the
  underlay bridge / WDS at ~1700 to carry the encapsulation.
- **Bridge tuning:** `multicast_snooping=0`, `stp=0`, IGMP snooping off, per-port
  mcast/bcast flood **on** (REAC uses broadcast and non-IGMP multicast).

**The elegant split:** the bridge does the cheap raw L2 relay for every direction over
the tunnel; an **nftables bridge drop** removes only the single latency-critical
direction (tunnel → local REAC port) at the bridge; the re-pacer re-delivers exactly
that one dropped direction, de-jittered. Each device sees exactly one copy of every
frame — never the raw burst and the re-paced copy together.

## Re-pacer placement — de-jitter is directional

De-jitter happens *after* the Wi-Fi (where the jitter is added), on whichever device
consumes that direction.

- **Master-side router** re-paces the **upstream** (box → master), protecting the
  phase-strict master input:
  - `--clock-source local` — count the master's own downstream frame counter on the
    wired side (= exact master rate)
  - `--pace-by-downstream` — phase-align the emit to the master's TDM answer slot via a
    PI loop
  - `--etf` — kernel-timed egress (hardware-offloaded on an i226 box, software-only on a
    plain Wi-Fi SoC)
  - plus a small clock margin and a rate-detect interval moved off the audible band.
- **Box-side router** re-paces the **downstream** (master → box), feeding the
  PLL-tolerant boxes: it free-runs on `--clock-source local-in` (the drop-immune
  downstream counter), needs **no** ETF, and must **not** have ETF forced on it (it
  disturbs the servo and drops frames).

The opposite direction on each router is plain bridge-forwarded. **Do not flatten this
asymmetry:** the master is phase-strict and needs kernel-timed, disciplined egress; the
boxes recover the clock themselves and free-run.

## Per-port ETF is tuned per ring, not global

`tc … etf delta` is set per egress port and is an ear-validated tuning knob, not a global
constant. In practice one ring tuned to a tighter delta (tens of µs) and the others left
at a proven larger default (a few hundred µs). A too-tight delta can leave a ring's buffer
sitting shallow; the larger default lets it fill to a healthy depth. Only change a ring's
delta after confirming by ear, and keep the others at the validated baseline.

## Buffer-depth sizing against the link-status budget

REAC link-status promotion is a **heartbeat / gap-watchdog**, not a phase or latency
measurement. Re-expressed from the slave link-check behaviour: status advances on an
accepted link-check message (a plain ready flag, no sample-accurate timing window);
survival is governed by a consecutive-missed-tick counter — more than 3 missed ticks
drops the link fully, more than 1 while up demotes it to a transient lost state, any
accepted link-check resets the counter.

So the link needs **gap-freeness, not low latency**: a relay that adds bounded latency
promotes fine as long as a link-check lands inside the tick budget. The failure that
breaks promotion is **latency amplification**: when the source pauses briefly (the
master's establishment-retry cycle), a grow-on-resume buffer underruns and re-prefills,
turning a ~170 ms source pause into a 700–820 ms output gap that overruns the 3-tick
budget and flaps the link.

The cure is **bounded latency with no re-prefill**: hold a small target depth, cover real
source gaps with a cadence-holding fill frame (so the downstream word clock stays alive
and the fill is inaudible because there was no real audio to miss), and on resume splice
real frames back in at the target depth — collapse the backlog so latency returns to the
target, not target-plus-pause. Combined with keep-the-buffer-small, the practical floor is
the WDS worst-case stall (tens of ms on a typical link); an adaptive depth (shallow in the
common case, deepen only when a stall demands it) beats a fixed depth. To get genuinely
lower latency, **harden the 5 GHz link to cut the worst-case stall first**.

## Shared-word-clock caveat

All REAC ports on a router share one output word clock (the mixer's ports are
sample-phase-aligned). Buffer prefill sets depth globally; you cannot independently shrink
one zone below the others via a live drain — a **warm restart** (re-prefill, near-seamless
thanks to the persisted converged clock) is the clean way to change depth. A snappy ~70 ms
keeps one zone clean but a fragile second zone can underrun; raise toward ~120 ms to keep
every zone clean at the cost of latency.

## Native vs imperative fabric, and the netifd/UCI persistence trap

The fabric can be stood up imperatively (a boot script that builds the gretap, adds VLANs
to the bridge, installs the nft drop, launches the re-pacer) or declaratively (OpenWrt UCI
for the gretap + trunk VLANs, an `/etc/nftables.d` drop file that survives
`service network restart`, a procd service for the daemon). The ownership rule is firm
either way: **the OS config owns the fabric; the daemon owns only the daemon.** A daemon
init that touches topology (`ip link set … nomaster`, `bridge vlan`, …) pulls ports out of
the bridge and kills the raw relay.

The load-bearing operational fact: **`service network restart` rebuilds `br-lan` from UCI
and silently wipes the manual `bridge vlan add dev reactap.N` entries** (a gretap subif as
a bridge port isn't cleanly UCI-representable), killing cross-router REAC until reboot. Two
defenses:

- **Imperative:** `rc.local` builds the fabric at boot; a `hotplug.d/iface` re-run hook
  rebuilds after any network restart; a `hotplug.d/net` wifi-mtu hook re-applies MTU +
  WDS-STA VLAN after a wifi reload — watch that the re-run guard tests `$INTERFACE`/
  `$ACTION` correctly, or the whole persistence layer is inert.
- **Declarative:** move the fabric under netifd + fw4 so a reload rebuilds it — needs
  `apk add gre` first, since the gretap proto handler is absent by default and a bare
  `proto 'gretap'` block no-ops without it; ship the nft drop as a fw4-sourced
  `/etc/nftables.d/10-reac.nft`.

Deploy declarative one router at a time (STA box first), back up first, neutralize the
imperative files before the first `service network restart`, and use that restart as the
reversible GO/NO-GO test before rebooting. **VXLAN-per-zone was evaluated and ruled out:**
`kmod-vxlan` isn't published for this target/release, it adds encap overhead with no MTU
win, and it doesn't retire the bridge-VLAN wipe anyway (the wipe hits any manual bridge
port regardless of tunnel type — the fix is declaring membership in UCI, not changing the
tunnel).

## Boot persistence and recovery

Make power-cycle safe on both routers: rebuild the gretap fabric at boot, wait for the
tunnel sub-interface, then relaunch the re-pacer. If a ring goes dark after heavy testing,
a stagebox link FSM can get stuck; clear it with a single stagebox replug. Judge stream
health by the **delta** of the underrun/PLC counters (frozen = clean), never the cumulative
total — large cumulative counters are scars from restart transients.

## The converter leg

The REAC→AES67 converter keeps its own README and usage docs; in the rig it's the path that
terminates REAC and carries audio as clocked AES67/RTP — the recommended robust architecture
for removing the synchronous constraint from the wireless segment. Keep the AES67 egress on a
dedicated L2 network (its own bridge / VLAN / SSID) so the multicast never crosses the loaded
REAC airtime, and run the converter on the host nearest the receiver.
