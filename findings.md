# REAC over Wi-Fi — the engineering findings

The investigation, distilled into one narrative: from *why does Wi-Fi break REAC*,
through *why a software re-pacer was the right first move*, to *where software hits a
hard wall and what hardware fixes it*. Two routers carry a REAC fabric across a 5 GHz
link — a **master-side router** (faces the mixer) and a **box-side router** (faces the
stageboxes). Where a model name appears it's a neutral example of the device class.

For the on-wire details referenced here, see
[reac-protocol](https://github.com/FreeREAC/reac-protocol).

## What REAC is, for this problem

REAC is a quasi-isochronous Layer-2 stream (EtherType `0x8819`). The master broadcasts
one frame per slot and every slave (stagebox) recovers its word clock directly from the
arrival cadence — **there is no jitter buffer in a stagebox**. Frame rate is fixed per
sample rate: 48 kHz → 4000 frames/s (~250 µs/frame), 96 kHz → ~8000 frames/s (~125 µs),
44.1 kHz scales the same. The audio counter (frame bytes 14–15) increments by one per
frame and advances even across a lost frame, which makes it a **drop-immune rate
reference**. REAC audio is pair-interleaved (even/odd channels share a 6-byte cell with
shuffled byte order); a naive flat-3-byte decode produces false "distortion", so every
measurement here uses the corrected pair-interleave decoder.

## Finding 1 — Wi-Fi delivers every byte but destroys the timing

The 5 GHz WDS delivers REAC with **zero loss, zero reorder, content byte-for-byte
intact** on a strong clean link — and still ruins the audio, because it wrecks the
cadence. Measured wired vs Wi-Fi, same stream:

| metric | wired | over Wi-Fi |
|---|---|---|
| inter-arrival variance | ~5,300 µs² | ~159,000 µs² (~30×) |
| frames per delivery burst | ~1.0 (max 5) | ~1.9 avg (up to 18) |
| gap after a burst | ~258 µs | up to ~8,800 µs |
| arrival distribution | unimodal ~250 µs | bimodal (~47% at 0–50 µs, tail to 8.8 ms) |

The root cause is **structural, not tunable**: REAC is on the order of 16,000 tiny
packets/s (both directions, multiple zones). Wi-Fi's per-packet airtime overhead forces
A-MPDU aggregation — frames get clumped and released in bursts. Disabling aggregation
would exhaust airtime; a cleaner channel does nothing because *we are the load*. The
bursts plus millisecond gaps wreck the stagebox's clock recovery, producing continuous
metallic/saturated audio while every packet counter stays perfect.

The conclusion that motivates everything after: the stagebox lacks the de-jitter buffer
a wired link gave it for free, so **insert that buffer in software** — receive the
bursty-but-correct stream, hold a few ms, re-emit a clean cadence locally. That is the
re-pacer.

## Finding 2 — the re-pacer is a transparent L2 timing smoother, and there is only one clock

The re-pacer relays the real master/slave frames (MACs, payload, type, counter all
unchanged) onto the local REAC segment, changing only *when* each frame leaves. It is
**not** a REAC master synthesizer: the mixer stays the one true master, the stagebox
stays handshake-connected to the mixer's MAC. This sidesteps the hard, unverified
master-TX/handshake-synthesis work.

The key reason it's tractable: unlike a Dante/AES67 clock-domain bridge, **there is one
clock here** — the mixer's. Because no frames are lost, the long-term average arrival
rate equals the mixer's word clock. The re-pacer recovers that rate and re-emits at
exactly it; the stagebox locks to the re-paced cadence, which is the recovered mixer
clock. No cross-domain drift, only added latency.

## Finding 3 — five things that make a software re-pacer actually clean

1. **Real-time pacing is feasible on a stock kernel.** A userspace
   `clock_nanosleep(TIMER_ABSTIME)` loop under `SCHED_FIFO`, pinned to the IRQ-handling
   CPU with PM-QoS held at zero wake latency, sustains the slot period at ~1 µs standard
   deviation. `PREEMPT_RT` is not required for the pacing itself.
2. **Pace every frame in counter order; never fast-path control frames.** Every REAC
   frame, including periodic control frames, carries audio in its counter slot.
   Forwarding control frames immediately to "preserve handshake timing" delivers their
   audio ahead of cadence — one click per control frame. Buffer and pace all frame types
   uniformly; the buffer latency is far below the connection-loss timeout, so handshakes
   are unaffected.
3. **Conceal underruns; never drop.** A clock-slave receiver tolerates no gap in the
   counter sequence. On underrun, repeat the previous frame's audio under the *next*
   counter value (the relay owns its output counter). A verbatim repeat that reuses a
   counter value reads as near-total loss because the unsigned counter difference wraps.
   A single repeat (one slot) is inaudible; only a run is perceptible, which the buffer
   is sized to prevent.
4. **Grow the buffer, don't shrink it.** Growing is silent; shrinking drops a frame — an
   audible click on a continuous signal. Default policy: grow-only, starting below the
   link's burst floor and growing up into it, converging from beneath onto the lowest
   clean latency. Reclaim latency purely through the playout clock (run a hair fast to
   drain, a hair slow to fill, clamped to a few hundred ppm — inaudible because
   audibility is in the rate of change, not the magnitude), so no frame is ever dropped
   to recover latency.
5. **Detect sample rate continuously, not just at startup.** The slot period is derived
   from the input frame rate, so 44.1/48/96 kHz run with no configuration and a live
   rate change at the console is followed without a restart. Two guards: snap a measured
   rate to the nearest standard rate before believing it (a link stall must not look like
   a rate change); require a change to persist several seconds before re-locking.

## Finding 4 — clock recovery: the central difficulty, resolved by stopping the servo

The recovered word clock must follow only the slow rate offset between source and relay
and ignore the fast occupancy swings bursts cause (the buffer already absorbs those). A
servo that reacts quickly to occupancy chases those swings and frequency-modulates the
clock — audibly. The iterations:

- an early gain-scheduled occupancy servo corrected per-frame → regular metallic clicks;
- a frozen period drifts ~500 ppm off the master, drains the buffer → periodic beeps;
- a binary-search converge-then-lock floored resolution near ~250 ppm with 1 s windows,
  leaving a ~59 ppm residual still audible.

The final rate source is the **cumulative counter-mean**: because the master's REAC clock
is a hardware crystal (constant), the true pace is the long-term average period =
(ns elapsed since frame #1) / (frames elapsed since frame #1). Frame count comes from the
drop-immune REAC counter, so the estimate is immune to Wi-Fi losses; as frames accumulate
the mean sharpens (sub-ppm within seconds; convergence to within ±5 ns of the full-span
value by ~5 s). After a converge window (default ~20 s) the period **freezes and is never
touched again**: emit rate equals input rate, occupancy holds with no drift. Occupancy is
corrected only at cold start or on a real thermal drift, and that correction biases the
emit temporarily while leaving the measured rate frozen, so it can never corrupt the rate.

General principle: **separate clock stability from latency control** — the frozen
counter-mean rate owns stability; the grow-only / clock-rate-bias buffer owns latency.

## Finding 5 — track the wired device, not the Wi-Fi arrival

A subtle trap: holding the jitter buffer constant is mathematically identical to matching
the emit rate to the *input* rate — and the input is the frame stream arriving over
Wi-Fi. So a buffer-nulling clock loop locks the emit clock to the **Wi-Fi arrival
cadence** — the far device's clock smeared by Wi-Fi delivery jitter. The local stagebox
then recovers its word clock from that smeared emit, putting Wi-Fi jitter *inside* the
box's clock loop and corrupting its A/D.

Evidence: transport is bit-faithful (re-time only); the downstream / D-A path is pristine
(coherence ~0.991); only the jitter-sensitive A/D is corrupted — upstream coherence ~0.91
over Wi-Fi versus ~0.99 on the same box wired. A pure clock problem.

Fix: a **`--clock-source local`** mode meters the local *wired* device's cadence (the
master's downstream frame counter, or the box's upstream) and drives the emit period from
that, so Wi-Fi carries data only, never timing. A `local-in` variant binds the meter to
the downstream-over-Wi-Fi counter (drop-immune, so still the mixer's exact rate even
though it arrives jittery) for the box-facing leg. In testing this collapsed the
box-vs-mixer frequency beat from roughly −71/+58 ppm to about −10 ppm.

## Finding 6 — the asymmetry: only the upstream clock-domain crossing is audible

**Downstream** (master → box) is a one-way flow into the box's clock domain: the box
recovers its word clock from the arriving cadence and plays everything synchronized to
that one clock, so any mismatch with the mixer's true clock is self-consistent and
inaudible. **Upstream** (box → master) is the only clock-domain crossing: the box captures
at its clock, the master reads at the master's clock. On a direct wire those are physically
identical (PHY clock recovery); through the rig the box's clock is a reconstruction of the
mixer's — right rate, residual wobble — and the upstream is the one place that wobble
becomes audible.

So the same physical jitter is **harmless downstream and permanent upstream**. This is why
the rig treats the two directions differently and why ETF / hardware timing is only needed
on the master-facing leg. Confound-free profiling of the residual upstream artifact
(decode the loop sine, FFT) showed silence perfectly clean, harmonics around −73 dB,
broadband floor around −94 dB — the artifact is pure timing jitter manifesting as FM
sidebands on the carrier (a dominant ±0.8 Hz term plus a 15–30 Hz cluster), not content
corruption.

## Finding 7 — ETF kernel-timed egress: helps the master leg, hurts the box leg

`SO_TXTIME` / ETF lets the kernel `sch_etf` qdisc release each frame on a hardware timer at
a programmed transmit time, instead of whenever `sendmsg` happens to run. On the
master-facing leg, ETF tightened the egress cadence from ~3.6 µs to ~1.4 µs standard
deviation (at the AF_PACKET TX timestamp) — the right tool there, because the master is
phase-strict. On the box-facing leg, ETF **backfired**: it disturbed the servo and caused
underruns. The box is a tolerant PLL slave; it recovers the clock itself and is harmed by
kernel-timed egress.

Two practical traps:

- ETF is a **silent no-op without a qdisc** — if the egress device has `qdisc noqueue`,
  `SCM_TXTIME` is ignored and frames leave at sendmsg-time with full scheduler jitter. You
  must `tc qdisc add dev <port> root etf clockid CLOCK_TAI delta <ns>` for the stamp to
  mean anything.
- ETF on a port whose frames lack `SO_TXTIME` risks dropping them.

`sch_etf` is mainline but not packaged by some OpenWrt feeds; it builds cleanly out-of-tree
against the SDK-prepared kernel (the same recipe builds `sch_cbs` / `sch_taprio`). The
qdisc needs `clockid CLOCK_TAI`.

## Finding 8 — the master-clock wall: where software ends

Re-pacing the upstream into a phase-strict FPGA TDM master still produces granular/clippy
audio that a wired path never has — and exhaustive on-rig elimination proved the cause is
**not** content, headers, counters, phase offset, or rate. You can hand the master a
byte-perfect sine (purity 1.000, −18 dBFS) and it outputs granular. Each negative result
ruled out: audio bytes (re-pacer copies audio byte-exact); box A/D + Wi-Fi (a sine injected
after A/D, after Wi-Fi, is still granular); the downstream path (an injected stream to a
wired output is also broken — pure copper); frame headers; counter value; phase offset
(swept across its measured value — no change); emit-rate source (every
clock-source/servo/prefill/ETF/offset variant locks to wire +0 ppm but settles a few ns
apart).

Root cause: **the master is phase-strict**. A wired stagebox answers every downstream frame
in a tight window — ~25 µs response latency, p10–p90 of 22–29 µs (a ~7 µs jitter window),
inter-frame 125 µs with std ~4.7 µs, zero counter gaps. The master demultiplexes the
upstream *assuming* that hardware phase lock (the protocol assumes jitter-free 100BASE-TX
full-duplex). A software re-pacer emits with microsecond-scale scheduler/qdisc jitter, so
the master's input sampler slips and resamples the upstream — a continuous ~3.6–6 Hz wobble
plus scattered clicks. The content is perfect; the master ruins it on the wrong timing. The
residual floor on this hardware was a few-Hz wobble / ~100 clicks/s and is **not tunable in
software there**.

The silicon limit is concrete: a typical Wi-Fi router SoC (MediaTek mt7986-class with an
mt7531 switch) physically cannot do hardware-timed TX — the integrated switch is the only
egress silicon, ETF hardware offload fails on both the switch port and the SoC GMAC, and
there is no PTP hardware clock (software timestamping only). "Take it out of the bridge"
doesn't help — the switch is the only egress path.

## The hardware verdict — i226 LaunchTime/TSN + PTP

Move the master-facing leg onto hardware that has both **ETF hardware offload (TSN
LaunchTime)** and a **PTP hardware clock**:

- **NIC:** Intel **i226** (`igc` driver) — ETF hardware offload on all four TX queues plus
  a PHC and PTM. With `--etf` + `tc … etf … offload`, frames leave at the exact programmed
  transmit time, clocked in hardware. i225 is identical; i210 has ETF on two queues and is
  also fine.
- **Host:** a fanless x86 mini-PC (Intel N100 / i3-N305 class) with 2–4 i226 ports and M.2
  Wi-Fi, running OpenWrt or Debian + the re-pacer.
- **Box radios:** MediaTek MT7915-class 5 GHz (mt76, solid AP/WDS); MT7916 a newer
  alternative.

How it works: the i226's LaunchTime hardware releases each upstream frame at its programmed
txtime, timed by the i226 PHC; the re-pacer locks that PHC's rate to the master's downstream
frame count and uses ETF offload for egress — reproducing in hardware what a wired box does.
Wi-Fi delay remains on the box side, but the box tolerates it. The deeper correct fix is
**true loop timing**: recover the master's clock from the downstream and discipline the
upstream emit to a disciplinable PTP clock — exactly what a REAC slave does in hardware.

Avoid SoCs marketed for TSN-*tunnel* offload (e.g. mt7988 "TOPS") — that's tunnel offload,
not TSN/ETF, and does nothing here.

Architecturally cleanest alternative: **don't carry synchronous REAC across the wireless
link at all.** Terminate REAC at each end, carry audio as clocked AES67/RTP over the
network, and regenerate hardware-clean REAC into the master, with the relay acting as the
local REAC master at the far end. Carrying a synchronous transport over a variable-latency
wireless link is inherently adversarial (the buffer must always be sized against the worst
recent burst); a jitter-tolerant packet-audio format removes that constraint entirely —
this is the original goal of the [reac-aes67](https://github.com/FreeREAC/reac-aes67)
project. The transparent re-pacer is the drop-in fix; the AES67 path is the robust one.

Prior public software-REAC efforts (`per-gron/reacdriver`) hit the same master/slave jitter
wall and shipped listen-only; the ETF + clock-repeater approach here gets further but
confirms the same silicon ceiling.

## A note on the original Wi-Fi-jitter theory

The standing symptom was the mixer's REAC sync LED locking / flapping / dropping, with the
leading hypothesis that the hardware clock slave couldn't tolerate the arrival jitter the
WDS injects loss-free. A separate, earlier instance of that exact symptom turned out to be a
**stagebox channel-count mismatch** (a 40-channel box on a 32-channel console), not clocking
— with a correctly-sized box, REAC connects and streams over the Wi-Fi/gretap/VLAN path. The
jitter-as-clock-killer finding above stands on its own measurements (variance 30×, A-MPDU
bursts, the audible upstream wobble); the channel-count note is the reminder to **rule out a
sizing mismatch before blaming timing**.
