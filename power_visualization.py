"""
Power analysis visualization for TYK2 inhibitor trials.

Generates:
1. Power curves for each trial (power vs detectable difference)
2. Comparison of detectable effect sizes across trials
"""
import math
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from scipy import stats

# Trial data from our analysis
trials = [
    {
        'name': 'Zasocitinib (TAK-279)',
        'n': 231,
        'arms': 3,
        'enrollment': 693,
        'color': '#2196F3',
        'marker': 'o',
        'detectable_80': 0.10,
        'power_20': 1.00,
    },
    {
        'name': 'Deucravacitinib (BMS-986165)',
        'n': 110,
        'arms': 2,
        'enrollment': 220,
        'color': '#FF5722',
        'marker': 's',
        'detectable_80': 0.15,
        'power_20': 0.96,
    },
    {
        'name': 'JNJ-77242113',
        'n': 243,
        'arms': 3,
        'enrollment': 731,
        'color': '#4CAF50',
        'marker': '^',
        'detectable_80': 0.09,
        'power_20': 1.00,
    },
]

p0 = 0.10  # Control event rate (placebo)
alpha = 0.05
z_alpha = stats.norm.ppf(1 - alpha / 2)


def power_for_diff(n, p0, delta):
    """Compute power for a given per-arm N, control rate p0, and absolute difference delta."""
    p1 = p0 + delta
    phat = (p0 + p1) / 2
    se = math.sqrt(2 * phat * (1 - phat) / n)
    if se == 0:
        return 0
    z = delta / se
    z_beta = z - z_alpha
    return stats.norm.cdf(z_beta)


# ============================================================
# FIGURE 1: Power Curves
# ============================================================
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

ax = axes[0]
deltas = np.linspace(0.01, 0.30, 100)

for trial in trials:
    powers = [power_for_diff(trial['n'], p0, d) for d in deltas]
    ax.plot(deltas * 100, powers, label=trial['name'],
            color=trial['color'], linewidth=2.5, marker=None)
    # Mark the detectable difference at 80% power
    idx = np.argmin(np.abs(np.array(powers) - 0.80))
    ax.plot(deltas[idx] * 100, 0.80, marker=trial['marker'],
            color=trial['color'], markersize=10, zorder=5)

# Horizontal line at 80% power
ax.axhline(y=0.80, color='gray', linestyle='--', linewidth=1, alpha=0.7)
ax.annotate('80% Power', xy=(0.5, 0.81), fontsize=10, color='gray',
            fontstyle='italic')

ax.set_xlabel('Absolute Treatment Effect (Δ, %)', fontsize=12)
ax.set_ylabel('Statistical Power', fontsize=12)
ax.set_title('Power Curves by Trial Size', fontsize=14, fontweight='bold')
ax.legend(fontsize=9, loc='lower right')
ax.set_xlim(0, 30)
ax.set_ylim(0, 1.05)
ax.grid(True, alpha=0.3)
ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0, decimals=0))
ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f%%'))

# Annotate detectable differences
for trial in trials:
    ax.annotate(f'{trial["name"].split("(")[0].strip()}\n{trial["n"]}/arm',
                xy=(trial['detectable_80'] * 100, 0.80),
                xytext=(trial['detectable_80'] * 100 + 1.5, 0.80 - 0.08 * (
                    1 if trial['name'] == 'Deucravacitinib (BMS-986165)' else
                    (-1 if trial['name'] == 'Zasocitinib (TAK-279)' else 0)
                )),
                fontsize=8, color=trial['color'], fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=trial['color'], lw=1))

# ============================================================
# FIGURE 2: Bar chart comparison
# ============================================================
ax2 = axes[1]
x = np.arange(len(trials))
width = 0.35

# Detectable effect at 80% power (lower is better)
detectable = [t['detectable_80'] * 100 for t in trials]
bars = ax2.bar(x, detectable, width, color=[t['color'] for t in trials],
               alpha=0.85, edgecolor='white', linewidth=1.2)

# Label bars
for bar, val, trial in zip(bars, detectable, trials):
    ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
             f'{val:.0f}%', ha='center', va='bottom', fontsize=11,
             fontweight='bold', color=trial['color'])
    ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() / 2,
             f'{trial["n"]}/arm', ha='center', va='center', fontsize=9,
             color='white', fontweight='bold')

# Zone shadings
ax2.axhspan(0, 10, alpha=0.1, color='green', label='Adequately Powered')
ax2.axhspan(10, 15, alpha=0.1, color='orange', label='Borderline')
ax2.axhspan(15, 30, alpha=0.1, color='red', label='Underpowered')

ax2.set_xticks(x)
ax2.set_xticklabels([t['name'].split('(')[0].strip() for t in trials],
                     fontsize=9)
ax2.set_ylabel('Minimum Detectable Effect (Δ, %)', fontsize=12)
ax2.set_title('Smallest Effect Each Trial Can Detect\n(at 80% Power, α=0.05)',
              fontsize=14, fontweight='bold')
ax2.legend(fontsize=9, loc='upper left')
ax2.set_ylim(0, 22)
ax2.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
plt.savefig('power_analysis.png', dpi=200, bbox_inches='tight')
print("✓ Saved power_analysis.png")


# ============================================================
# FIGURE 3: Power vs Effect Size (detailed comparison)
# ============================================================
fig2, ax3 = plt.subplots(1, 1, figsize=(10, 6))

deltas_fine = np.linspace(0.01, 0.35, 200)

for trial in trials:
    powers = [power_for_diff(trial['n'], p0, d) for d in deltas_fine]
    label = f"{trial['name']}  (n={trial['n']}/arm, enrollment={trial['enrollment']})"
    ax3.plot(deltas_fine * 100, powers, label=label,
             color=trial['color'], linewidth=2.5)
    # Find exact 80% crossing
    for i, p in enumerate(powers):
        if p >= 0.80:
            ax3.plot(deltas_fine[i] * 100, 0.80, marker=trial['marker'],
                     color=trial['color'], markersize=12, zorder=5)
            break

ax3.axhline(y=0.80, color='gray', linestyle='--', linewidth=1, alpha=0.5)
ax3.axhline(y=0.90, color='gray', linestyle=':', linewidth=1, alpha=0.3)

# Typical psoriasis effect size range
ax3.axvspan(15, 25, alpha=0.08, color='blue', label='Typical Psoriasis Effect Range')

ax3.set_xlabel('Absolute Treatment Effect (Δ, %)', fontsize=12)
ax3.set_ylabel('Statistical Power', fontsize=12)
ax3.set_title('Power vs Effect Size for TYK2 Trials\n(Placebo Rate = 10%, α = 0.05 two-sided)',
              fontsize=14, fontweight='bold')
ax3.legend(fontsize=9, loc='lower right')
ax3.set_xlim(0, 35)
ax3.set_ylim(0, 1.05)
ax3.grid(True, alpha=0.3)
ax3.yaxis.set_major_formatter(mticker.PercentFormatter(1.0, decimals=0))
ax3.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f%%'))

# Annotations
ax3.annotate('80% Power threshold', xy=(0.5, 0.81), fontsize=9, color='gray')
ax3.annotate('90% Power', xy=(0.5, 0.91), fontsize=8, color='gray')

plt.tight_layout()
plt.savefig('power_vs_effect.png', dpi=200, bbox_inches='tight')
print("✓ Saved power_vs_effect.png")


# ============================================================
# Print summary
# ============================================================
print(f"\n{'='*70}")
print(f"{'Power Analysis Summary':^70}")
print(f"{'='*70}")
print(f"{'Trial':<30} {'N/arm':<8} {'Detect Δ@80%':<14} {'Power@20%':<12} {'Zone':<12}")
print(f"{'-'*70}")
for t in trials:
    det = f"{t['detectable_80']:.0%}"
    pwr = f"{t['power_20']:.0%}"
    if t['detectable_80'] <= 0.10:
        zone = 'Adequate'
    elif t['detectable_80'] <= 0.15:
        zone = 'Borderline'
    else:
        zone = 'Underpowered'
    print(f"{t['name']:<30} {t['n']:<8} {det:<14} {pwr:<12} {zone:<12}")

print(f"\nAssumptions: Placebo rate = {p0:.0%}, α = {alpha}, two-sided test")
print(f"Typical psoriasis drug effect: 15-25% absolute improvement over placebo")
