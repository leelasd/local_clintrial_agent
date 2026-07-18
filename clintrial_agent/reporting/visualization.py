import logging
from pathlib import Path
from clintrial_agent.config import CONFIG
from clintrial_agent.stats import _dichotomous_power_curve

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

def generate_power_plots(all_results, output_dir='images'):
    """Generate power curve visualizations from analysis results.
    
    Creates:
    1. images/power_curves.png — power curves for each trial
    2. images/power_comparison.png — bar chart of detectable effects
    """
    if not HAS_MPL:
        logger.warning("matplotlib/numpy not installed. Skipping power plots.")
        return

    Path(output_dir).mkdir(exist_ok=True)

    # Collect dichotomous trials with power data
    plot_trials = []
    for r in all_results:
        ss = r.get('sample_size')
        if not ss or not ss.get('power_analysis'):
            continue
        pa = ss['power_analysis']
        det = pa.get('detectable_absolute_difference')
        if det is None:
            continue
        plot_trials.append({
            'name': r.get('drug', r['nct_id']),
            'n': ss['estimated_n_per_arm'],
            'enrollment': ss['enrollment_actual'],
            'control_rate': ss.get('estimated_control_event_rate', 0.10),
            'alpha': pa.get('alpha', 0.05),
            'detectable_80': det,
            'power_20': pa.get('estimated_power_for_20pct_improvement', 0),
            'assessment': pa.get('assessment', 'N/A'),
        })

    if not plot_trials:
        logger.info("No dichotomous power data to plot.")
        return

    colors = plt.cm.Set2(np.linspace(0, 1, len(plot_trials)))
    markers = ['o', 's', '^', 'D', 'v', 'p', '*', 'h']

    for idx, t in enumerate(plot_trials):
        t['color'] = colors[idx]
        t['marker'] = markers[idx % len(markers)]

    # ── Figure 1: Power Curves ──
    fig, ax = plt.subplots(figsize=(10, 6))
    deltas = np.linspace(0.01, 0.40, 150)

    for t in plot_trials:
        powers = [_dichotomous_power_curve(t['n'], t['control_rate'], d, t['alpha']) for d in deltas]
        ax.plot(deltas * 100, powers, label=t['name'],
                color=t['color'], linewidth=2.5)
        idx_80 = np.argmin(np.abs(np.array(powers) - 0.80))
        ax.plot(deltas[idx_80] * 100, 0.80, marker=t['marker'],
                color=t['color'], markersize=10, zorder=5)

    ax.axhline(y=0.80, color='gray', linestyle='--', linewidth=1, alpha=0.7)
    ax.annotate('80% Power', xy=(0.5, 0.81), fontsize=10, color='gray', fontstyle='italic')

    ax.set_xlabel('Absolute Treatment Effect (Δ, %)', fontsize=12)
    ax.set_ylabel('Statistical Power', fontsize=12)
    ax.set_title('Power Curves by Trial', fontsize=14, fontweight='bold')
    ax.legend(fontsize=9, loc='lower right')
    ax.set_xlim(0, 40)
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(1.0, decimals=0))
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f%%'))

    for t in plot_trials:
        ax.annotate(f'{t["name"]}\n{t["n"]}/arm',
                    xy=(t['detectable_80'] * 100, 0.80),
                    xytext=(t['detectable_80'] * 100 + 2, 0.80 - 0.06 * (
                        1 if plot_trials.index(t) % 2 == 0 else -0.5
                    )),
                    fontsize=8, color=t['color'], fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color=t['color'], lw=1))

    plt.tight_layout()
    path1 = f'{output_dir}/power_curves.png'
    fig.savefig(path1, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"  ✓ Saved {path1}")

    # ── Figure 2: Bar chart comparison ──
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    x = np.arange(len(plot_trials))
    detectable = [t['detectable_80'] * 100 for t in plot_trials]
    bars = ax2.bar(x, detectable, 0.5, color=[t['color'] for t in plot_trials],
                   alpha=0.85, edgecolor='white', linewidth=1.2)

    for bar, val, t in zip(bars, detectable, plot_trials):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f'{val:.0f}%', ha='center', va='bottom', fontsize=10,
                 fontweight='bold', color=t['color'])
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() / 2,
                 f'{t["n"]}/arm', ha='center', va='center', fontsize=9,
                 color='white', fontweight='bold')

    thresholds = CONFIG['dichotomous_power_assessment']
    ax2.axhspan(0, thresholds['adequately_powered'] * 100, alpha=0.1, color='green', label='Adequately Powered')
    ax2.axhspan(thresholds['adequately_powered'] * 100, thresholds['borderline'] * 100, alpha=0.1, color='orange', label='Borderline')
    ax2.axhspan(thresholds['borderline'] * 100, thresholds['underpowered'] * 100, alpha=0.1, color='red', label='Underpowered')

    ax2.set_xticks(x)
    ax2.set_xticklabels([t['name'] for t in plot_trials], fontsize=9)
    ax2.set_ylabel('Minimum Detectable Effect (Δ, %)', fontsize=12)
    ax2.set_title('Smallest Effect Each Trial Can Detect\n(at 80% Power)', fontsize=14, fontweight='bold')
    ax2.legend(fontsize=9, loc='upper left')
    ax2.set_ylim(0, max(detectable) * 1.5 + 5)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    path2 = f'{output_dir}/power_comparison.png'
    fig2.savefig(path2, dpi=200, bbox_inches='tight')
    plt.close(fig2)
    print(f"  ✓ Saved {path2}")
