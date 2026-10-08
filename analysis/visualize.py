"""Part 2, Task 11: save the two charts to visualizations/ from the raw CSVs.

Rebuilds the cleaned data via clean_and_eda.run(quiet=True), so no intermediate files are needed.
"""
import sys
from pathlib import Path

import matplotlib
import matplotlib.ticker
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean_and_eda import run  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "visualizations"
INK, MUTED, GRID = "#1f2933", "#6b7785", "#e4e7eb"
ACCENT, NEUTRAL = "#c2410c", "#9aa5b1"  # highlight vs. context bars


def style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def return_rate_chart(by_pay):
    rates = (by_pay["mean"] * 100).sort_values(ascending=False)
    colors = [ACCENT if m == rates.index[0] else NEUTRAL for m in rates.index]
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)
    bars = ax.bar(rates.index, rates.values, color=colors, width=0.5)
    for bar, v in zip(bars, rates.values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.8, f"{v:.1f}%", ha="center", va="bottom",
                color=INK, fontsize=11, fontweight="bold")
    others = rates.iloc[1:]
    ratio = rates.iloc[0] / others.min()
    ax.set_title(f"{rates.index[0]} Returns at {rates.iloc[0]:.1f}% — {ratio:.0f}x {others.idxmin().title()}",
                 loc="left", color=INK, fontsize=14, fontweight="bold")
    ax.set_xlabel("Payment method", color=MUTED)
    ax.set_ylabel("Return rate (% of orders)", color=MUTED)
    ax.set_ylim(0, rates.iloc[0] * 1.15)
    style(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "return_rate_by_payment.png")
    plt.close(fig)


def monthly_revenue_chart(monthly):
    peak = monthly.idxmax()
    peak_label = pd.Period(peak).strftime("%B %Y")
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    ax.plot(monthly.index, monthly.values, color=NEUTRAL, linewidth=2, marker="o", markersize=7,
            markeredgecolor="white", markeredgewidth=2)
    ax.plot([peak], [monthly[peak]], color=ACCENT, marker="o", markersize=9, markeredgecolor="white",
            markeredgewidth=2, linestyle="none")
    ax.annotate(f"{monthly[peak]:,.0f}", (peak, monthly[peak]), textcoords="offset points", xytext=(0, 12),
                ha="center", color=INK, fontsize=11, fontweight="bold")
    ax.set_title(f"Revenue Peaks in {peak_label} (outliers excluded)", loc="left", color=INK,
                 fontsize=14, fontweight="bold")
    ax.set_xlabel("Month", color=MUTED)
    ax.set_ylabel("Revenue (INR)", color=MUTED)
    ax.set_ylim(0, monthly.max() * 1.18)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    style(ax)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "monthly_revenue_trend.png")
    plt.close(fig)


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    result = run(quiet=True)
    return_rate_chart(result["by_pay"])
    monthly_revenue_chart(result["monthly_clean"])
    print("Saved:", *(p.name for p in sorted(OUT_DIR.glob("*.png"))))
