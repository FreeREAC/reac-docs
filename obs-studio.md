# OBS Studio and REAC

How to get REAC channels into OBS Studio, and why FreeREAC does not ship an OBS
plugin that binds the wire itself.

## The short answer

**Take REAC audio from `reac-pw`'s PipeWire nodes.** `reac-pw` owns the segment,
speaks the protocol and publishes the channels; OBS is one more consumer of those
nodes, like any other application. There is nothing REAC-specific to install on
the OBS side.

A second consumer binding EtherType `0x8819` directly would be a second
implementation of a job `reac-pw` already does. RX-only binding is *technically*
safe beside a running master — `reac_seglock.h` is explicit that binding is not
mastering, and the kernel module counts frames on a live segment without
disturbing it — but "it would not break anything" is not a reason to build it.

## The recipe

Add an **Audio Input Capture (PulseAudio)** source and pick the `reac-capture`
node for the box you want.

Two things about this surprise people, both verified on OBS Studio 32.1.1:

- **Which source you use depends on whether a PipeWire AUDIO plugin is installed.**
  OBS's own `linux-pipewire` plugin is video only — it registers
  `pipewire-camera-source`, `pipewire-desktop-capture-source`,
  `pipewire-screen-capture-source` and `pipewire-window-capture-source`, and
  nothing for audio. Core OBS captures Linux audio through
  `pulse_input_capture` / `pulse_output_capture`, plus ALSA and JACK.

  **A separate plugin adds PipeWire audio capture, and the rig has it**:
  `linux-pipewire-audio` sits in `/usr/lib64/obs-plugins/` beside `obs-pwvideo`.
  With it, `reac-pw`'s nodes are selectable as PipeWire sources directly, with no
  Pulse layer in the path — which is the better arrangement, since it keeps the
  graph one hop shorter and the node names intact.

  Without it, the nodes still reach OBS through `pipewire-pulse`, appearing under
  their node names, e.g.

  ```
  reac-capture         float32le  8ch  48000Hz   RUNNING
  reac-capture.s1608   float32le 16ch  48000Hz   RUNNING
  ```

- **OBS caps a source at 8 channels.** `MAX_AUDIO_CHANNELS` is 8 and the widest
  speaker layout is `SPEAKERS_7POINT1`. A box wider than 8 inputs — an S-1608
  publishes 16, an S-4000S 32 — cannot arrive whole through one OBS source; OBS
  substitutes a channel count it supports and logs `%hhu channels not supported by
  OBS, using %hhu instead for recording`. *(The ceiling and the substitution are
  read from the OBS headers and binary; which channels survive a 16 ch node has
  not been measured.)*

  So for anything wider than 8 channels, do the selection **before** OBS: give
  `reac-pw` the routing, or interpose a PipeWire node, so what OBS sees is a
  node of at most 8 channels carrying the channels you actually want.

## Prior art: `obs-h8819-source`

There is an existing OBS plugin for REAC —
[`norihiro/obs-h8819-source`](https://github.com/norihiro/obs-h8819-source), by
Norihiro Kamae, GPL-3.0-or-later. `h8819` is the EtherType, `0x8819`. It is real,
working software: developed and listening-validated against a Roland M-200i.

What it does: a `libpcap` capture on a dedicated ethernet port, decoding the REAC
downstream broadcast into an OBS audio source. Capture runs in a separate
`obs-h8819-proc` helper process that is `setcap`'d for `CAP_NET_RAW` and pipes
decoded PCM back to the plugin, so OBS itself needs no privilege. It refcounts one
capture per interface across sources, and smooths the pcap timestamp into OBS's
clock.

Its limits, as shipped:

- **two channels per source** — a left and a right chosen from 1..40, so a full
  segment means many sources;
- **48 kHz hardcoded**, in the source's own `samples_per_sec` and in its
  sample-time arithmetic. A 96 kHz segment is not addressed;
- **one tested device**, the M-200i;
- **last commit 2023-08-20 (v0.3.1)**; no control plane — no head-amp, no box
  identity, no channel names.

**Nothing is left to harvest from it, because it has already been harvested.** Its
decoder, `convert_to_pcm24lep`, had the channel-pair byte braid right in 2022, and
that byte map is one of the two attributed sources of libreac's braid oracle —
`reac_braid.h` and `reac_decode.h` both credit it by name. Licences are compatible
in that direction and the credit is in the headers.

Worth knowing as well: libreac carried a **plain-LE** downstream layout as its
default until 0.5.0, while this plugin had the braid from the start. The braid is
the one true layout in both directions; plain LE survives only as the named
diagnostic `reac_decode_plain_le()`.

## If the question comes back

The reason not to build an OBS wire source is architectural, not legal and not
technical:

- **Licensing is fine.** OBS Studio is GPL-2.0-or-later and libreac is
  GPL-3.0-or-later. "Or later" lets the combined work be distributed under GPL-3,
  so no exception, dual-licence or carve-out is needed. (This is the mirror image
  of the kernel case, where GPL-2-*only* forecloses GPL-3.)
- **Coexistence is fine.** An RX-only consumer takes no segment lock and does not
  contend with a master.
- **The architecture is the objection.** REAC audio reaches applications through
  `reac-pw`. One protocol implementation, one owner per segment, one place where
  box identity, head-amp and naming live. An OBS-shaped bypass would duplicate all
  of it and drift.

The case would change if OBS had to take REAC on a machine that cannot run
`reac-pw` at all. That is not a situation the rig has.
