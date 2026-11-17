"""Builds all figures from the project's real evidence files.
Usage: python3 make_figures.py <PROJECT dir> <output dir>"""
import sys, os, json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Patch

proj, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
S1 = f"{proj}/RESEARCH/studies/S001_low_latency_without_crackle"
CAP = f"{proj}/DELIVERABLES/T024_findings/lab_captures_2026-11-12"

INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"
BLUE, PURPLE, ORANGE, GREEN, RED = "#2a6fbb", "#7b5ea7", "#d9731a", "#2e8b57", "#b42318"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK, "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "white", "axes.facecolor": "white"})
def save(fig, name):
    fig.savefig(f"{out}/{name}", dpi=200, bbox_inches="tight", facecolor="white"); plt.close(fig)

# ---------- Fig 1: latency (E006 real runs) ----------
runs = pd.read_csv(f"{S1}/evidence/digests/V015/runs.csv")
ok = runs[(runs.phase == "plugged") & (runs.status == "OK")]
fig, ax = plt.subplots(figsize=(10, 5.6))
rows = [("MME", "mme", PURPLE), ("WASAPI shared", "shared", BLUE)]
for i, (lab, key, col) in enumerate(rows):
    v = ok[ok.path == key].median_ms.values
    ax.barh(i + 1, v.mean(), color=col, height=0.5)
    ax.scatter(v, [i + 1] * len(v), s=36, color="white", edgecolor=INK, zorder=3, linewidth=1)
    ax.text(v.mean() + 3, i + 1, f"{v.mean():.1f} ms", va="center", fontweight="bold")
# exclusive: owner-reported range, hatched, clearly not a measurement of this study
ax.barh(0, 22.2-19.8, left=19.8, color="none", edgecolor=ORANGE, hatch="///", height=0.5, linewidth=1.5)
ax.text(22.2 + 3, 0, "19.8 – 22.2 ms  (range reported by owner, not yet\n re-measured here; crackled in 3 of 4 captures)", va="center", color=INK)
ax.axvline(20, color=RED, ls="--", lw=1.6)
ax.text(20.8, 2.55, "goal: 20 ms", color=RED, fontsize=12, va="bottom")
ax.set_yticks([0, 1, 2]); ax.set_yticklabels(["WASAPI exclusive", "MME", "WASAPI shared"][::1][0:1] + ["MME", "WASAPI shared"])
ax.set_xlim(0, 175); ax.set_ylim(-0.6, 2.9)
ax.set_xlabel("Round-trip latency, program output → cable → program input (ms)")
ax.xaxis.grid(True, color=GRID); ax.set_axisbelow(True)
ax.set_title("Round-trip latency by Windows audio path on one PC", loc="left", fontsize=16, fontweight="bold")
fig.text(0.125, -0.07, "Dots = 5 separate runs per path (run medians, 6 chirps each). Block 256, 48 kHz, Line In ↔ Speakers by cable. "
         "Source: E006, evidence V015.", fontsize=9.5, color=MUTED, wrap=True)
save(fig, "fig1_latency_by_path.png")

# ---------- Fig 2: click timeline for 3 captures ----------
caps = [("WASAPI shared, block 256", "20261112_144533_shared256", BLUE),
        ("WASAPI exclusive, block 128 (clean in this run, bad in an earlier one)", "20261112_144217_excl128", GREEN),
        ("WASAPI exclusive, block 256", "20261112_144415_excl256", ORANGE)]
fig, axs = plt.subplots(3, 1, figsize=(10, 6.4), sharex=True)
for ax, (lab, d, col) in zip(axs, caps):
    ev = pd.read_csv(f"{CAP}/{d}/events.csv")
    t = ev.t_ms.values / 1000
    ax.vlines(t, 0, 1, color=col, lw=0.6 if len(t) > 50 else 2)
    ax.set_ylim(0, 1); ax.set_yticks([]); ax.spines["left"].set_visible(False)
    if len(t) == 0: ax.text(10, 0.4, "clean: nothing detected", ha="center", color=MUTED, fontsize=12)
    if len(t) == 1: ax.text(0.5, 0.4, "← tone start-up (not a fault)", color=MUTED, fontsize=11)
    ax.text(0.0, 1.08, f"{lab}  —  {len(ev)} detected click{'s' if len(ev)!=1 else ''} in 20 s", transform=ax.transAxes, fontweight="bold", fontsize=12)
axs[-1].set_xlim(0, 20); axs[-1].set_xlabel("Time into 20 s capture (s)")
fig.suptitle("Same program, same cable, same 1 kHz tone: only the Windows mode differs", x=0.01, ha="left", fontsize=15, fontweight="bold", y=1.0)
fig.text(0.01, -0.025, "Each line = one click found by the app's detector in the recorded input. Source: Lab captures 2026-11-12 (events.csv). "
         "The detector is not yet calibrated (E005 pending).", fontsize=9.5, color=MUTED)
fig.tight_layout()
save(fig, "fig2_click_timeline.png")

# ---------- Fig 3: 3 ms grid ----------
ev = pd.read_csv(f"{CAP}/20261112_144415_excl256/events.csv")
s = ev.start_sample.values
fig, axs = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1.5, 1]})
ax = axs[0]
ax.hist(s % 144, bins=np.arange(0, 145, 4), color=ORANGE, edgecolor="white")
ax.set_xlabel("Click start position inside a 144-sample (3 ms) window")
ax.set_ylabel("Number of clicks"); ax.set_title("Folded at 144 samples = 3 ms", loc="left", fontweight="bold")
ax.yaxis.grid(True, color=GRID); ax.set_axisbelow(True)
ax = axs[1]
Ps = [96, 128, 144, 192, 256]
R = [abs(np.exp(2j * np.pi * (s % P) / P).mean()) for P in Ps]
ax.bar([str(p) for p in Ps], R, color=[ORANGE if p == 144 else "#c7ccd4" for p in Ps], width=0.6)
ax.axhline(0.02, color=MUTED, lw=1, ls=":")
ax.set_ylim(0, 1); ax.set_ylabel("Grid concentration R (0 = random, 1 = perfect)")
ax.set_xlabel("Folding period (samples)"); ax.set_title("Only 144 lines up", loc="left", fontweight="bold")
for i, r in enumerate(R): ax.text(i, r + 0.02, f"{r:.2f}", ha="center", fontsize=11)
fig.suptitle("Noise bursts sit on a 3 ms grid in the exclusive-mode capture", x=0.01, ha="left", fontsize=15, fontweight="bold", y=1.03)
fig.text(0.01, -0.04, f"{len(s)} clicks from one 20 s capture (excl256). One capture only; a 1 kHz tone (3 tone periods = 3 ms) could still create a detection artefact. Source: events.csv.",
         fontsize=9.5, color=MUTED)
fig.tight_layout()
save(fig, "fig3_three_ms_grid.png")

# ---------- Box helper ----------
def box(ax, x, y, w, h, text, fc="#eef4fb", ec=BLUE, bold=False, fs=11.5, ls="-"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=ec, lw=1.8, ls=ls))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal", color=INK)
def arrow(ax, p, q, col=INK, ls="-", rad=0.0, lw=1.8):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=16, color=col, lw=lw, ls=ls, connectionstyle=f"arc3,rad={rad}"))

# ---------- Fig 4: test setup ----------
fig, ax = plt.subplots(figsize=(12, 6.6)); ax.set_xlim(0, 12); ax.set_ylim(0, 6.6); ax.axis("off")
ax.text(0.1, 6.35, "A.  What I want to play with", fontsize=14, fontweight="bold")
box(ax, 0.2, 4.55, 2.2, 1.0, "Casio CTK-2500\n(aux out only,\nno MIDI)", fc="#fff4e8", ec=ORANGE)
box(ax, 3.4, 4.55, 2.4, 1.0, "PC sound card\nLine In (blue jack)", fc="#f3f4f6", ec=MUTED)
box(ax, 6.7, 4.55, 2.5, 1.0, "My software\n(low-latency engine)", bold=True)
box(ax, 10.0, 4.55, 1.8, 1.0, "PC Line Out\n(green jack)\n→ speaker", fc="#f3f4f6", ec=MUTED, fs=10.5)
arrow(ax, (2.4, 5.05), (3.4, 5.05)); arrow(ax, (5.8, 5.05), (6.7, 5.05)); arrow(ax, (9.2, 5.05), (10.0, 5.05))
ax.text(2.9, 5.2, "3.5 mm\ncable", ha="center", fontsize=9, color=MUTED)
ax.text(6.0, 4.05, "Delay here = what I hear as lag when playing", fontsize=11, color=RED, ha="center", style="italic")
ax.plot([0.1, 11.9], [3.5, 3.5], color=GRID, lw=1.5)
ax.text(0.1, 3.1, "B.  How I measure that delay (no extra hardware)", fontsize=14, fontweight="bold")
box(ax, 0.6, 1.2, 2.8, 1.2, "Software plays a\nshort chirp\n(known start time)", bold=False)
box(ax, 4.6, 1.2, 2.6, 1.2, "PC Line Out (green)\n──cable──\nLine In (blue)", fc="#f3f4f6", ec=MUTED)
box(ax, 8.0, 1.2, 3.8, 1.2, "Software records, finds the\nchirp by correlation →\nround-trip latency (ms)", bold=True, fs=11)
arrow(ax, (3.4, 1.8), (4.6, 1.8)); arrow(ax, (7.2, 1.8), (8.0, 1.8))
ax.text(6.0, 0.55, "Repeated for each Windows audio path: MME, WASAPI shared, WASAPI exclusive, ASIO4ALL …\n"
        "Same loop with a 1 kHz tone is used to look for crackle (noise bursts).", ha="center", fontsize=11, color=MUTED)
save(fig, "fig4_test_setup.png")

# ---------- Fig 5: roadmap / pipeline ----------
fig, ax = plt.subplots(figsize=(13.5, 4.8)); ax.set_xlim(0, 13.5); ax.set_ylim(0, 4.8); ax.axis("off")
ax.text(0.1, 4.45, "Project roadmap: from a keyboard with no MIDI to any instrument", fontsize=15, fontweight="bold")
items = [("1. Capture", "Low-latency audio\nin / out engine", "done: engine,\nlooper app, calibration", "#e8f5ee", GREEN, "-"),
         ("2. Measure", "Latency per path,\nwhere crackle enters", "in progress: study S001\n(instrument being calibrated)", "#fff4e8", ORANGE, "-"),
         ("3. Detect notes", "Audio → notes\n(CQT / NMF)", "planned", "#f3f4f6", MUTED, "--"),
         ("4. Re-voice", "Notes → MIDI →\nother instruments", "planned", "#f3f4f6", MUTED, "--"),
         ("5. Song → notes", "Any song → notes\n(ML models)", "idea", "#f3f4f6", MUTED, "--")]
w, gap = 2.3, 0.3
for i, (t, d, st, fc, ec, ls) in enumerate(items):
    x = 0.2 + i * (w + gap)
    box(ax, x, 1.7, w, 1.7, f"{t}\n\n{d}", fc=fc, ec=ec, ls=ls, fs=10.5)
    ax.text(x + w/2, 1.25, st, ha="center", va="top", fontsize=9.5, color=INK)
    if i < len(items) - 1: arrow(ax, (x + w, 2.55), (x + w + gap, 2.55), col=MUTED)
save(fig, "fig5_roadmap.png")
print("done")
