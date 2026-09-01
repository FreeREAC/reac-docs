# OBS and REAC — the three routes, assessed

**2026-09-01.** Evidence read from a live rig running two REAC segments at 96 kHz.

Three ways to get REAC channels into OBS Studio were put side by side: consume
`reac-pw`'s PipeWire nodes (no new code), adopt the existing third-party
`obs-h8819-source` plugin, or build an OBS source on `libreac`. This document
records what each one actually costs, the live-graph evidence behind the first,
and the decision.

The conclusion is not new — [obs-studio.md](obs-studio.md) settled it on
2026-08-25. It is re-examined here because the question was asked again, and
because that document's evidence had gone stale in three specific ways.
**The verdict stands. Three of its numbers did not, and are corrected below.**

---

## 1. Verdict

> **Ship route 1, and only route 1. FreeREAC should not publish an OBS plugin —
> neither its own nor a fork of the existing one.**
>
> REAC audio reaches applications through `reac-pw`, which owns the segment,
> speaks the protocol, and publishes every channel as an ordinary PipeWire node.
> OBS is one more consumer of those nodes, exactly like any other application,
> and needs nothing REAC-specific installed. That is not a workaround for a
> missing plugin; it is the architecture working as designed. A plugin that binds
> EtherType `0x8819` itself would be a second implementation of a job `reac-pw`
> already does — a second owner of the segment, and a second place for box
> identity, head-amp and channel naming to live and to drift. Licensing permits
> it (OBS Studio is GPL-2.0-or-later, libreac is GPL-3.0-or-later, so a combined
> work distributes as GPL-3) and coexistence permits it (an RX-only binder takes
> no segment lock). Neither is a reason to build it. The single condition that
> would reopen the question is OBS having to take REAC on a machine that cannot
> run `reac-pw` at all — a situation this rig does not have.
>
> What FreeREAC ships for OBS is **documentation, not a repository**: the guide
> in §5 below. The one piece of code worth writing goes *upstream*, to
> `obs-h8819-source`, as three small patches described in §3.

That block is written to be lifted verbatim into the publishing roster.

**Order, if it is ever asked for as a sequence:** route 1 now (done — it is a
guide); the upstream patches to `obs-h8819-source` when someone has an afternoon
(§3.4); route 3 never, unless the reopening condition above is actually met.

---

## 2. Route 1 — consume `reac-pw`'s PipeWire nodes (the zero-code route)

**Status: works today, no code, no install. This is the answer.**

The operator's hunch was right, and the live graph says so directly.

### 2.1 What is on the graph, read 2026-09-01

`pw-dump` returned 470 objects / 26 nodes / 324 ports / 51 links (counts recorded
as a positive control — an empty scan and a broken scan look identical). Four
REAC nodes, all served by a single `reac-pw` process:

| node | class | ch | rate | format | channel positions | state |
|---|---|---|---|---|---|---|
| `reac-capture` | Audio/Source | **16** | **96000** | F32P | `AUX0`…`AUX15` | running |
| `reac-capture.seg2` | Audio/Source | **32** | **96000** | F32P | `AUX0`…`AUX31` | running |
| `reac-playback` | Audio/Sink | 8 | 96000 | F32P | `AUX0`…`AUX7` | suspended |
| `reac-playback.seg2` | Audio/Sink | 8 | 96000 | F32P | `AUX0`…`AUX7` | suspended |

Their `node.description` strings carry the box identity, which is what the
operator sees in a device list:

```
reac-capture        S-1608 (16 in / 8 out) — 16 ch (REAC box inputs)
reac-capture.seg2   S-4000S (32 in / 8 out) — 32 ch (REAC box inputs)
reac-playback       S-1608 (16 in / 8 out) — 8 ch (REAC box outputs)
reac-playback.seg2  S-4000S (32 in / 8 out) — 8 ch (REAC box outputs)
```

Ports are one per channel — `capture_AUX0` … `capture_AUX31` on the sources,
`playback_AUX0`…`playback_AUX7` plus `monitor_AUX0`…`monitor_AUX7` on the sinks.
The monitor ports matter: they expose *what the console is sending to the stage
box outputs*, so a recording of the monitor feed is available without touching
the console's routing.

Through `pipewire-pulse`, the same four appear as:

```
reac-capture.seg2           float32le  32ch  96000Hz  RUNNING
reac-playback.seg2.monitor  float32le   8ch  96000Hz  SUSPENDED
reac-playback.monitor       float32le   8ch  96000Hz  SUSPENDED
reac-capture                float32le  16ch  96000Hz  RUNNING
```

### 2.2 Three corrections to the 2026-08-25 document

`obs-studio.md` quoted the Pulse view as:

```
reac-capture         float32le   8ch  48000Hz   RUNNING
reac-capture.s1608   float32le  16ch  48000Hz   RUNNING
```

Every field of that has moved:

- **the rate is 96000, not 48000** — both segments are configured `REAC_RATE=96000`;
- **the second segment's suffix is `.seg2`, not `.s1608`** — the suffix comes from
  `REAC_NAME` in that segment's env file and is deliberately *not* the box model,
  because it is the address the console's patches name;
- **the widths are 16 and 32, not 8 and 16** — the boxes on the rig changed.

It also stated that the OBS PipeWire-audio plugin "sits in `/usr/lib64/obs-plugins/`".
It does not, on this machine. It is installed in the **user** plugin directory,
`~/.config/obs-studio/plugins/linux-pipewire-audio/bin/64bit/`. A reader who
checked the system directory and found only `linux-pipewire.so` and
`obs-pwvideo.so` would have concluded, wrongly, that the plugin was missing.
(That is what happened during this assessment, and it was caught only by sweeping
every plugin location instead of trusting the first empty result.)

### 2.3 What the route presumes

`reac-pw` runs as a **user** systemd unit — it is a PipeWire client and needs the
user's session and `$HOME`:

```
reac-pw.service                 active   (Conflicts=reac-pw-master.service)
```

One daemon serves every segment. Configuration is two layers:

```
~/.config/reac-pw/reac-pw.env     REAC_IFACES=<ifaceA>,<ifaceB>   # the config-once fact
~/.config/reac-pw/<iface>.env     REAC_TX / REAC_ROLE / REAC_MIXER
                                  REAC_RATE / REAC_NAME / REAC_HEADAMP
```

`REAC_NAME` is what suffixes a segment's node names. Changing it re-points every
patch that names those nodes — including an OBS source, which stores its target
by node **name** (see §5.4).

### 2.4 Why attaching OBS is safe for a live console

Two independent facts, both read off the running graph:

- **The nodes fan out.** `node.exclusive` is unset on all four; PipeWire sources
  serve any number of consumers. `reac-capture.seg2` currently feeds the console
  over 29 links and `reac-capture` over 4. An OBS source *adds* links and removes
  none — it cannot take the channels away from the desk.
- **The graph clock is pinned.** `clock.force-rate=192000` and
  `clock.force-quantum=1024`. A newly arriving client therefore cannot renegotiate
  the graph rate or period, which is the usual way a casual application disturbs a
  live audio graph. It is worth checking this before a show on any rig that has not
  set it.

### 2.5 The rate story at 96 kHz

Three paces, all different, and that is fine:

| stage | rate |
|---|---|
| the REAC segments | 96 000 Hz (`REAC_RATE=96000`) |
| the PipeWire graph | 192 000 Hz (`clock.force-rate`) |
| OBS's recording | 48 000 Hz (OBS offers 44.1 and 48 kHz only) |

`reac-pw`'s nodes are `pw_stream` adapters, so PipeWire re-paces between the wire
and the graph; the OBS plugin then asks for OBS's own rate and PipeWire converts
again. **OBS never sees 96 kHz, and does not need to.** Nothing has to be matched
by hand. The practical consequence is only this: do not expect a 96 kHz capture
file out of OBS, because OBS cannot make one at any sample rate above 48 kHz.

### 2.6 The one real constraint — OBS caps a source at 8 channels

This is structural, and it is structural twice over. Read from the installed
OBS 32.1.1 headers:

- `/usr/include/obs/media-io/audio-io.h:29` — `#define MAX_AUDIO_CHANNELS 8`
- `/usr/include/obs/media-io/media-io-defs.h:20` — `#define MAX_AV_PLANES 8`
- a source hands OBS audio as `struct obs_source_audio`, whose `speakers` field is
  an `enum speaker_layout`; the widest member is `SPEAKERS_7POINT1 = 8`
  (`audio-io.h:74`). There is no layout above 7.1, so there is no way for a source
  to describe more than 8 channels.

`audio-io.h:30` also defines `MAX_DEVICE_INPUT_CHANNELS 64`, which is tempting and
is a red herring: it appears in no public header interface, and the source-facing
contract is the speaker layout. **8 is the number.**

The two ways of reaching a node fail *differently* above 8 channels, and the
difference decides which one to use:

- **the PulseAudio source substitutes.** `linux-pulseaudio.so` logs
  `pulse-input: %hhu channels not supported by OBS, using %hhu instead for recording`
  and picks a count for you.
- **the PipeWire source negotiates.** `linux-pipewire-audio.so` carries
  `obs_channels_to_spa_audio_position` and the full `SPA_AUDIO_CHANNEL_AUX0…AUX31`
  vocabulary: it asks PipeWire for OBS's configured layout and lets PipeWire do the
  conversion. It has no substitution warning because it never needs one.

*Not measured:* which specific channels of a 16- or 32-channel node survive that
conversion. Determining it requires running OBS against the live graph, which was
out of scope for a read-only assessment. §5.3 gives a recipe that makes the
question moot rather than one that depends on the answer.

---

## 3. Route 2 — the existing third-party plugin, `obs-h8819-source`

**Status: real, working, well-built software. Not what FreeREAC should ship — but
we owe it patches.**

[`norihiro/obs-h8819-source`](https://github.com/norihiro/obs-h8819-source), by
Norihiro Kamae. `h8819` is the EtherType, `0x8819`.

### 3.1 License

**GPL-3.0-or-later, © 2022 Norihiro Kamae.** `LICENSE` is the verbatim GNU GPL
v3. The grant is stated as a prose header in `src/plugin-main.c:1-17` and
`src/plugin-macros.h.in:1-17` ("either version 3 of the License, or (at your
option) any later version"); there is no SPDX identifier in any first-party file.
The only SPDX lines in the tree belong to vendored Wireshark code
(`src/wireshark/capture_win_ifnames.{c,h}`, GPL-2.0-or-later, Windows-only and not
compiled on Linux).

That confirms the credit libreac already carries is accurate, and that
GPL-3.0-or-later → GPL-3.0-or-later is compatible in the direction we used it.

### 3.2 What it does

A `libpcap` capture — BPF filter `ether proto 0x8819` — running inside a separate
helper binary, `obs-h8819-proc`, which is `setcap`'d for `CAP_NET_RAW` at install
so that OBS itself stays unprivileged. Helper and plugin talk over two anonymous
pipes: the plugin sends a `channel_mask` so the helper only decodes channels
somebody is listening to, and the helper returns a small header plus packed 24-bit
LE planar PCM. One capture per NIC is refcounted across all sources that use it.
Timestamps come from pcap and are slewed onto OBS's clock by an offset estimator
that snaps on first packet or past 70 ms of drift and otherwise integrates the
error slowly. It is **RX-only and audio-only**: no transmit path anywhere, and no
head-amp, box identity, or channel names.

### 3.3 Its limits as shipped

- **Two channels per source**, a left/right pair chosen from 1..40
  (`src/source.c:41-42`), emitted as hard stereo (`source.c:126-138`). Forty
  channels therefore means twenty sources. Notably the layer *below* is already
  n-channel — the stereo cap is imposed by `source.c` alone.
- **48 kHz hardcoded**, in exactly two places: `source.c:130`
  (`.samples_per_sec = 48000, // TODO: retrieve from the packet`) and the
  sample-time arithmetic at `capdev-internal.h:43-46`
  (`n_samples * 62500 / 3`). 96 kHz is addressed nowhere; the README acknowledges
  44.1 kHz is unsupported for the same reason.
- **One tested device**, a Roland M-200i — a README claim, not a code
  restriction. There are no device IDs, MACs or model checks anywhere. What *is*
  baked in is 40 channels and 12 samples per packet.
- **Last release v0.3.1, 2023-08-20.** No control plane.

### 3.4 What our findings could improve — three patches worth sending

Our braid oracle and this plugin's decoder are byte-identical, which makes the
relationship a two-way street. The credit already flows one way; these flow back.

1. **A sample rate that is not 48 kHz — the highest-value patch, and it is tiny.**
   Our geometry work establishes that the REAC frame is *rate-invariant*: 40 ch ×
   12 samples × 3 B = 1440 B at every rate, and only the **packet rate** changes
   (3675 / 4000 / 8000 pps at 44.1 / 48 / 96 kHz). So this plugin's braid, its
   1440-byte window and its 12-sample block are *already correct at 96 kHz*. The
   only wrong things are the two constants above. A rate property threaded into
   `sample_time()` closes both the 44.1 kHz gap and the 96 kHz gap in one change —
   and it can even be auto-detected, since the helper already timestamps every
   packet and 4000 vs 8000 pps over one second is unambiguous.
2. **A frame-length guard — this one is a memory-safety fix.** Frame acceptance is
   only two tests: the EtherType, and a `C2 EA` tail marker
   (`capdev-proc.c:62-76`). There is no length check, but the decoder then reads
   1440 bytes unconditionally. A REAC **upstream return** (a stage box's own
   feed — 340 / 628 / 1204 bytes on the boxes we have measured) carries the same
   EtherType *and* the same `C2 EA` tail, so it passes both tests and causes a
   roughly 1150-byte buffer overread — inside the `CAP_NET_RAW`-privileged helper.
   Our rule "the geometry is the role" is the one-line fix, and it resolves the
   author's own `// TODO: Check destination is broadcast address` at
   `capdev-proc.c:70`.
3. **Tolerate the 2-byte FCS residue.** The tail-marker test rejects any frame
   whose last two bytes are not `C2 EA`. Our corpus shows that residue is the
   frame's own Ethernet FCS, left in place by many capture paths — present in 56
   of 76 captures we hold, and not specific to any console family. On an affected
   capture path this plugin rejects 100% of frames and the source is silent, with
   only a line on stderr to say why. Accepting the marker at either `caplen-2` or
   `caplen-4` fixes it.

Two more are plausible but optional: parameterising the hardcoded `40 * 3` braid
stride, and replacing the stereo pair with a first-channel/count pair to give
4- or 8-channel sources (everything below `source.c` already supports it).

Out of scope, and correctly so: head-amp control (needs TX, and an OBS box that
starts transmitting contends with the real console for mastery), and box
identity/channel names (a large control-block dependency for a cosmetic label).

### 3.5 Does it build here?

Yes, with one caveat worth recording.

`libobs` 32.1.1 development files are installed and `find_package(libobs)`
resolves. **`libpcap-devel` is not installed** — only the runtime library. A
first configure nevertheless succeeded, and the reason is a **pre-existing local
edit in the checkout**, dated 2024, not made during this assessment:

```diff
-if(UNIX AND NOT APPLE)
+if(UNIXZZ AND NOT APPLE)
     find_package(PkgConfig)
     pkg_check_modules(LIBPCAP REQUIRED libpcap)
```

`UNIXZZ` is never defined, so the required-libpcap check is skipped. On a pristine
upstream checkout, configure would have **failed** at that line. The plugin module
built; the helper then failed on the missing `pcap.h`.

With a scratch-local pcap sysroot (RPM unpacked into a scratch directory, nothing
installed system-wide), the build completed cleanly — exit 0, no warnings under
`-Wall -Wextra` — producing both `obs-h8819-source.so` (NEEDED `libobs.so.30`, a
valid OBS 30/32 module) and the `obs-h8819-proc` helper. Nothing was installed;
`make install` was never run, since it would invoke the `setcap` script.

---

## 4. Route 3 — an OBS source built on `libreac`

**Status: technically clean, architecturally wrong. Not built.**

`libreac` 0.7.1, GPL-3.0-or-later, is installed on this rig with a working
pkg-config (`pkg-config --modversion libreac` → `0.7.1`). Its capture surface is
four functions and a one-field struct — `reac_capture_open` on a named interface,
optional non-blocking, `reac_capture_next` per frame, `reac_capture_close` — with
decode into a caller-owned buffer as **planar signed 24-bit LE**. It needs
`CAP_NET_RAW`. 96 kHz is fully supported (`REAC_MODE_96K` = 8000 pps). There is no
multi-segment concept and that is deliberate: two segments are two `reac_capture`
instances in your own loop.

### 4.1 What it would add over routes 1 and 2

Honestly assessed, less than it first appears:

| capability | over route 1 | over route 2 |
|---|---|---|
| 96 kHz | no gain — route 1 already runs at 96 k | **yes** (but see §3.4.1: a ~10-line upstream patch gets the same thing) |
| multi-segment | no gain — route 1 already serves two segments | no gain — route 2 refcounts a capture per NIC already |
| upstream + downstream | marginal for a *listener* | yes |
| box identity | **route 1 already has it**, in `node.description` | yes |
| head-amp | requires TX ⇒ contends for segment mastery. Not wanted. | — |
| channel names | **libreac has none** — naming lives outside it | — |
| no PipeWire dependency | only matters on a host that cannot run `reac-pw` | — |

The decisive row is the last one, and it is the reopening condition from §1.

### 4.2 The honest cost

libreac gives away the hard part — braid decode both directions, s24↔float, frame
validation, FCS handling, loss counting, rate detection from cadence, the
AF_PACKET open, box geometry. Perhaps 600–800 lines you do not write.

What remains is still substantial, roughly **1 200–1 800 lines of C plus a
packaging story**:

- **the privilege problem, which dictates the architecture.** `reac_capture_open`
  needs `CAP_NET_RAW` in the calling process, and granting that to OBS is not
  acceptable. So you inherit exactly `obs-h8819-source`'s shape: a separate
  `setcap`'d helper, an IPC framing, lifecycle and per-interface refcounting — and
  a packaging step that breaks under Flatpak or Snap builds of OBS.
- **threading and batching** — libreac owns no thread and no ring by design, and a
  REAC frame is 12 samples (8000 frames/s at 96 kHz).
- **clock smoothing onto OBS's clock** — the part most likely to be subtly wrong.
- **rate handling** across a mid-session re-clock, which is a real event on this rig.
- **channel selection** against the 8-channel ceiling, **properties UI**, and
  module boilerplate.

Every one of those is work that routes 1 and 2 have already paid for.

### 4.3 Disposition

**No skeleton was laid, and no repository was created.** The task's condition was
"if and only if the assessment says this route is warranted"; it says the
opposite, and the settled architecture says the opposite. Creating an empty
`obs-reac-source` repository would advertise an intention FreeREAC does not have.

For the record, the coexistence question that would gate such a plugin is settled
and is *not* the obstacle. The rule lives in `reac-pw`'s `reac_seglock.h` — not in
libreac, which documents no coexistence policy at all:

> BINDING IS NOT MASTERING. RX is a copy: observing, counting or capturing a
> segment takes no lock and must stay safe beside a live master. Only asserting
> mastery claims it, and only immediately before the first frame goes out.

An RX-only OBS binder would be safe beside the running console. It is simply
unnecessary.

---

## 5. The route-1 guide

*This section is the publishable deliverable.*

### 5.1 What you need

- `reac-pw` running and owning the segment (§2.3). Confirm with
  `systemctl --user is-active reac-pw.service` and then `pw-cli ls Node`, where the
  `reac-capture` nodes should be listed and `running`.
- OBS Studio on Linux.
- Preferably the **PipeWire audio** plugin,
  [`dimtpap/obs-pipewire-audio-capture`](https://github.com/dimtpap/obs-pipewire-audio-capture).
  OBS's own `linux-pipewire.so` is **video only** — it registers
  `pipewire-camera-source`, `pipewire-desktop-capture-source`,
  `pipewire-screen-capture-source` and `pipewire-window-capture-source`, and
  nothing for audio. Without the extra plugin the nodes still reach OBS through
  `pipewire-pulse`; with it, the path is one hop shorter and node names stay intact.

### 5.2 The simple recipe — up to 8 channels

1. **Sources → Add → "Audio Input Capture (PipeWire)"**.
2. In **Device**, pick the node for the box you want — they are listed by their
   descriptions, e.g. *S-1608 (16 in / 8 out) — 16 ch (REAC box inputs)*.
3. Set OBS's channel count in **Settings → Audio → Channels** to what you actually
   want (up to 7.1). OBS asks PipeWire for that layout and PipeWire converts.

Without the PipeWire plugin, use **"Audio Input Capture (PulseAudio)"** and pick
`reac-capture` or `reac-capture.seg2` by name. Be aware that above 8 channels the
Pulse path substitutes a channel count for you and says so only in the log.

To record what the console is *sending to the stage box*, pick the
`reac-playback…monitor` source instead.

### 5.3 The recipe that scales — choosing 8 of 32 channels

A 16- or 32-channel node cannot arrive whole through one OBS source, because no
OBS source can describe more than 8 channels (§2.6). Do the selection **before**
OBS. The cleanest way needs no extra node at all:

1. Add a **"JACK Input Client"** source (`linux-jack.so`, shipped with OBS) and set
   **Number of Channels** to what you want, up to 8. It registers that many JACK
   input ports named `in_1`, `in_2`, … under a client called `OBS Studio: <source
   name>`.
2. PipeWire *is* the JACK server here — `pipewire-jack` provides `libjack.so.0` —
   so those ports appear as ordinary PipeWire ports.
3. Wire exactly the channels you want with `pw-link`, or by dragging in `helvum`
   or `qpwgraph`:

   ```
   pw-link 'reac-capture.seg2:capture_AUX6'  'OBS Studio: Stage:in_1'
   pw-link 'reac-capture.seg2:capture_AUX7'  'OBS Studio: Stage:in_2'
   ```

   Remember the ports are named from `AUX0`, so REAC channel *n* is
   `capture_AUX<n-1>`.

This gives arbitrary per-channel selection out of a 32-channel segment, and it is
the correction to the earlier advice that you would have to "interpose a PipeWire
node" — you do not.

The alternative, if you prefer a persistent named device over ad-hoc links, is a
PipeWire loopback node of ≤8 channels fed from the channels you want, which OBS
then picks up like any other device.

### 5.4 Things that will surprise you

- **The rate does not need matching.** REAC at 96 kHz, the graph at 192 kHz and
  OBS at 48 kHz coexist; PipeWire converts (§2.5). OBS cannot record above 48 kHz
  regardless.
- **The PipeWire source binds by node *name*.** It stores `TargetName` (the
  `node.name`, with `TargetId` left as the `-1` sentinel), so the source survives a
  `reac-pw` restart — *provided the name is stable*. The name is set by `REAC_NAME`
  in that segment's env file; changing it silently orphans the OBS source.
- **You are not stealing the channels from the desk.** PipeWire sources fan out and
  these nodes are not exclusive; OBS adds links and removes none (§2.4).
- **Check the graph clock is pinned before a show.** With `clock.force-rate` and
  `clock.force-quantum` set, no arriving application can renegotiate the graph.
  Without them, one can.

---

## 6. What publishes where

| item | destination | form |
|---|---|---|
| the §5 guide | `reac-docs`, public | the standing operator guide; [obs-studio.md](obs-studio.md) corrected to agree with it |
| the §1 verdict | FreeREAC publishing roster | lift verbatim; the roster entry for OBS is a *guide*, not a repository |
| the §3.4 patches | upstream `norihiro/obs-h8819-source` | three patches — a rate property, a frame-length guard, FCS-residue tolerance — sent as our findings, with the braid relationship acknowledged |
| the §2.1 node table | this document | evidence of record, dated; it will go stale again when the boxes change |

No new repository is created by this assessment.
