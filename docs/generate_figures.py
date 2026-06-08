"""Generate the LP visualization figures for the Bradley motor-pool worked example.

Run from anywhere:  python docs/generate_figures.py
Outputs PNGs into docs/assets/.
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
os.makedirs(ASSETS, exist_ok=True)

# ---- Problem data --------------------------------------------------------- #
# Decision vars: x = scheduled services (svc), y = field-level repairs (flr).
# maximize 30x + 75y
# labor:      20x + 40y <= 800    ->  x + 2y <= 40
# parts:    1000x + 3000y <= 45000 -> x + 3y <= 45
# powerpacks:        y <= 12
OPT = (30, 5)
OPT_VALUE = 1275
# Feasible polygon vertices (counter-clockwise).
VERTICES = [(0, 0), (40, 0), (30, 5), (9, 12), (0, 12)]

NAVY = "#1f2d3d"
RED = "#c0392b"
GREEN = "#27ae60"
BLUE = "#2e6fb0"
ORANGE = "#e08e0b"
PURPLE = "#7b4fa3"


def fig_graphical_solution():
    fig, ax = plt.subplots(figsize=(9, 7))

    x = np.linspace(0, 46, 400)
    # Constraint boundary lines.
    ax.plot(x, (40 - x) / 2, color=BLUE, lw=2,
            label="labor: 20·svc + 40·flr ≤ 800")
    ax.plot(x, (45 - x) / 3, color=ORANGE, lw=2,
            label="parts: 1000·svc + 3000·flr ≤ 45000")
    ax.axhline(12, color=PURPLE, lw=2,
               label="powerpacks: flr ≤ 12")

    # Feasible region.
    poly = Polygon(VERTICES, closed=True, facecolor="#9ecae1",
                   alpha=0.35, edgecolor=NAVY, lw=1.5, zorder=1)
    ax.add_patch(poly)
    ax.text(11, 3.2, "feasible\nregion", fontsize=12, color=NAVY, ha="center")

    # Integer lattice points inside the feasible region.
    xs, ys = [], []
    for i in range(0, 46):
        for j in range(0, 13):
            if i + 2 * j <= 40 and i + 3 * j <= 45 and j <= 12:
                xs.append(i)
                ys.append(j)
    ax.scatter(xs, ys, s=9, color=NAVY, alpha=0.35, zorder=2,
               label="integer-feasible plans")

    # Objective contour lines 30x + 75y = c.
    for c in (600, 900, 1200, OPT_VALUE):
        yy = (c - 30 * x) / 75
        style = "-" if c == OPT_VALUE else "--"
        lw = 2.2 if c == OPT_VALUE else 1.0
        col = RED if c == OPT_VALUE else "#888888"
        ax.plot(x, yy, style, color=col, lw=lw, alpha=0.9, zorder=3)
        # Label each contour near the top.
        xlab = 2
        ax.text(xlab, (c - 30 * xlab) / 75 + 0.15, f"value={c}",
                color=col, fontsize=8.5, rotation=-18)

    # Objective improvement direction (gradient of 30x+75y).
    ax.annotate("", xy=(34, 11.2), xytext=(28, 8),
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=2))
    ax.text(34.4, 11.3, "improving\ndirection ∇(30,75)", color=RED, fontsize=9)

    # Vertices and the optimum.
    vx, vy = zip(*VERTICES)
    ax.scatter(vx, vy, s=45, facecolor="white", edgecolor=NAVY, zorder=4)
    ax.scatter(*OPT, s=200, color=RED, zorder=6, marker="*",
               edgecolor="black", linewidth=0.6)
    ax.annotate(f"OPTIMUM\nsvc=30, flr=5\nvalue={OPT_VALUE}",
                xy=OPT, xytext=(33, 6.6), fontsize=11, fontweight="bold",
                color=RED,
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.5))

    ax.set_xlim(0, 46)
    ax.set_ylim(0, 16)
    ax.set_xlabel("scheduled services  (svc)", fontsize=12)
    ax.set_ylabel("field-level repairs  (flr)", fontsize=12)
    ax.set_title("Graphical solution — feasible region, objective contours, optimum",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.95)
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(ASSETS, "graphical_solution.png")
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def fig_resource_utilization():
    names = ["labor\n(mech-hrs)", "Class IX parts\n($)", "powerpacks\n(units)"]
    used = [800, 45000, 5]
    cap = [800, 45000, 12]
    pct = [u / c * 100 for u, c in zip(used, cap)]
    binding = [True, True, False]

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = [RED if b else GREEN for b in binding]
    bars = ax.bar(names, pct, color=colors, edgecolor="black", width=0.6)
    ax.axhline(100, color="black", ls="--", lw=1, alpha=0.6)
    ax.text(2.45, 101.5, "capacity", fontsize=9, ha="right")

    for bar, u, c, b in zip(bars, used, cap, binding):
        label = f"{u:,} / {c:,}\n{'BINDING' if b else f'slack {c-u:,}'}"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                label, ha="center", fontsize=10,
                fontweight="bold" if b else "normal",
                color=RED if b else GREEN)

    ax.set_ylabel("% of weekly capacity consumed", fontsize=12)
    ax.set_ylim(0, 120)
    ax.set_title("Resource utilization at the optimum\n(red = bottleneck, green = slack)",
                 fontsize=13, fontweight="bold")
    ax.grid(True, axis="y", ls=":", alpha=0.4)
    fig.tight_layout()
    out = os.path.join(ASSETS, "resource_utilization.png")
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def fig_shadow_prices():
    names = ["labor\n(per mech-hr)", "parts\n(per $)", "powerpacks\n(per unit)"]
    sp = [0.75, 0.015, 0.0]
    # Value delivered by a +10% capacity bump on each binding resource.
    bump = [0.75 * 80, 0.015 * 4500, 0.0]  # +80 hrs, +$4500, +1.2 PP

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))

    b1 = ax1.bar(names, sp, color=[RED, RED, GREEN], edgecolor="black", width=0.6)
    for bar, v in zip(b1, sp):
        ax1.text(bar.get_x() + bar.get_width() / 2, v + 0.02,
                 f"{v:g}", ha="center", fontsize=11, fontweight="bold")
    ax1.set_ylabel("readiness pts per +1 unit of resource", fontsize=11)
    ax1.set_ylim(0, 0.9)
    ax1.set_title("Shadow prices (LP-relaxation basis)", fontsize=12, fontweight="bold")
    ax1.grid(True, axis="y", ls=":", alpha=0.4)

    b2 = ax2.bar(names, bump, color=[BLUE, ORANGE, "#bbbbbb"],
                 edgecolor="black", width=0.6)
    for bar, v in zip(b2, bump):
        ax2.text(bar.get_x() + bar.get_width() / 2, v + 1.0,
                 f"+{v:g}" if v else "0", ha="center", fontsize=11,
                 fontweight="bold")
    ax2.set_ylabel("readiness pts gained", fontsize=11)
    ax2.set_ylim(0, 80)
    ax2.set_title("Value of a +10% capacity bump\n(+80 hrs / +$4,500 / +1.2 PP)",
                  fontsize=12, fontweight="bold")
    ax2.grid(True, axis="y", ls=":", alpha=0.4)

    fig.suptitle("Where extra capacity is worth buying — and where it is not",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = os.path.join(ASSETS, "shadow_prices.png")
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


if __name__ == "__main__":
    for f in (fig_graphical_solution(), fig_resource_utilization(), fig_shadow_prices()):
        print("wrote", f)
