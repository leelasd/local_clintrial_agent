import os
import math
import numpy as np
import scipy.stats as stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class MetaAnalysisResult:
    comparison_name: str
    trials: List[str]
    effect_sizes_hr: List[float]
    ci_lower_hr: List[float]
    ci_upper_hr: List[float]
    weights_random_percent: List[float]
    
    # Meta-analysis statistics
    fe_pooled_hr: float
    fe_ci_lower_hr: float
    fe_ci_upper_hr: float
    
    re_pooled_hr: float
    re_ci_lower_hr: float
    re_ci_upper_hr: float
    
    q_statistic: float
    p_value_q: float
    i_squared: float
    tau_squared: float
    
    forest_plot_path: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparison_name": self.comparison_name,
            "trials": self.trials,
            "effect_sizes_hr": self.effect_sizes_hr,
            "ci_lower_hr": self.ci_lower_hr,
            "ci_upper_hr": self.ci_upper_hr,
            "weights_random_percent": [round(w, 2) for w in self.weights_random_percent],
            "fixed_effects_pooled_hr": round(self.fe_pooled_hr, 3),
            "fixed_effects_95_ci": [round(self.fe_ci_lower_hr, 3), round(self.fe_ci_upper_hr, 3)],
            "random_effects_pooled_hr": round(self.re_pooled_hr, 3),
            "random_effects_95_ci": [round(self.re_ci_lower_hr, 3), round(self.re_ci_upper_hr, 3)],
            "heterogeneity": {
                "cochran_q": round(self.q_statistic, 3),
                "p_value_q": round(self.p_value_q, 4),
                "i_squared_percent": round(self.i_squared, 2),
                "tau_squared": round(self.tau_squared, 4)
            },
            "forest_plot_path": self.forest_plot_path
        }


def calculate_meta_analysis(trial_data: List[Dict[str, Any]], comparison_name: str, output_dir: str = "images") -> MetaAnalysisResult:
    """
    Performs Inverse-Variance Fixed-Effects and DerSimonian-Laird Random-Effects Meta-Analysis
    on hazard ratios (HR) or odds ratios (OR) extracted across trials in a portfolio.
    """
    k = len(trial_data)
    if k < 2:
        raise ValueError("Meta-analysis requires at least 2 trial entries.")

    trials = []
    log_hrs = []
    se_log_hrs = []
    hrs = []
    ci_lows = []
    ci_highs = []

    for entry in trial_data:
        nct_id = entry.get("nct_id", "Unknown")
        hr = float(entry.get("hr", 0.80))
        
        # If CI bounds provided, extract SE from log CI width
        if "ci_lower" in entry and "ci_upper" in entry:
            ci_low = float(entry["ci_lower"])
            ci_high = float(entry["ci_upper"])
            se = (math.log(ci_high) - math.log(ci_low)) / (2 * 1.96)
        else:
            # Estimate standard error based on sample size or default assumption
            n_eval = float(entry.get("n_evaluable", 200))
            se = 2.0 / math.sqrt(n_eval)  # Schoenfeld SE approximation
            ci_low = math.exp(math.log(hr) - 1.96 * se)
            ci_high = math.exp(math.log(hr) + 1.96 * se)

        trials.append(nct_id)
        hrs.append(hr)
        ci_lows.append(ci_low)
        ci_highs.append(ci_high)
        log_hrs.append(math.log(hr))
        se_log_hrs.append(se)

    log_hrs = np.array(log_hrs)
    se_log_hrs = np.array(se_log_hrs)
    w_fe = 1.0 / (se_log_hrs ** 2)

    # 1. Fixed-Effects Pooled Estimate
    fe_log_hr = np.sum(w_fe * log_hrs) / np.sum(w_fe)
    se_fe_log_hr = 1.0 / math.sqrt(np.sum(w_fe))
    
    fe_hr = math.exp(fe_log_hr)
    fe_ci_low = math.exp(fe_log_hr - 1.96 * se_fe_log_hr)
    fe_ci_high = math.exp(fe_log_hr + 1.96 * se_fe_log_hr)

    # 2. Heterogeneity (Cochran's Q, I², Tau²)
    q_stat = np.sum(w_fe * ((log_hrs - fe_log_hr) ** 2))
    df = k - 1
    p_val_q = 1.0 - stats.chi2.cdf(q_stat, df=df)
    
    i_sq = max(0.0, ((q_stat - df) / q_stat) * 100.0) if q_stat > 0 else 0.0
    
    c_factor = np.sum(w_fe) - (np.sum(w_fe ** 2) / np.sum(w_fe))
    tau_sq = max(0.0, (q_stat - df) / c_factor) if c_factor > 0 else 0.0

    # 3. DerSimonian-Laird Random-Effects Pooled Estimate
    w_re = 1.0 / ((se_log_hrs ** 2) + tau_sq)
    re_log_hr = np.sum(w_re * log_hrs) / np.sum(w_re)
    se_re_log_hr = 1.0 / math.sqrt(np.sum(w_re))

    re_hr = math.exp(re_log_hr)
    re_ci_low = math.exp(re_log_hr - 1.96 * se_re_log_hr)
    re_ci_high = math.exp(re_log_hr + 1.96 * se_re_log_hr)

    w_re_percent = (w_re / np.sum(w_re)) * 100.0

    # 4. Generate Forest Plot
    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, f"forest_plot_{comparison_name}.png")
    generate_forest_plot(
        comparison_name=comparison_name,
        trials=trials,
        hrs=hrs,
        ci_lows=ci_lows,
        ci_highs=ci_highs,
        weights_percent=w_re_percent,
        fe_hr=fe_hr,
        fe_ci=(fe_ci_low, fe_ci_high),
        re_hr=re_hr,
        re_ci=(re_ci_low, re_ci_high),
        i_sq=i_sq,
        q_stat=q_stat,
        p_val_q=p_val_q,
        tau_sq=tau_sq,
        output_path=plot_path
    )

    return MetaAnalysisResult(
        comparison_name=comparison_name,
        trials=trials,
        effect_sizes_hr=hrs,
        ci_lower_hr=ci_lows,
        ci_upper_hr=ci_highs,
        weights_random_percent=w_re_percent.tolist(),
        fe_pooled_hr=fe_hr,
        fe_ci_lower_hr=fe_ci_low,
        fe_ci_upper_hr=fe_ci_high,
        re_pooled_hr=re_hr,
        re_ci_lower_hr=re_ci_low,
        re_ci_upper_hr=re_ci_high,
        q_statistic=q_stat,
        p_value_q=p_val_q,
        i_squared=i_sq,
        tau_squared=tau_sq,
        forest_plot_path=plot_path
    )


def generate_forest_plot(
    comparison_name: str,
    trials: List[str],
    hrs: List[float],
    ci_lows: List[float],
    ci_highs: List[float],
    weights_percent: np.ndarray,
    fe_hr: float,
    fe_ci: tuple,
    re_hr: float,
    re_ci: tuple,
    i_sq: float,
    q_stat: float,
    p_val_q: float,
    tau_sq: float,
    output_path: str
):
    """
    Renders a publication-grade Forest Plot using Matplotlib.
    """
    k = len(trials)
    fig, ax = plt.subplots(figsize=(10, 2 + 0.6 * k), dpi=300)
    
    y_positions = np.arange(k, 0, -1)
    
    # Line of No Effect (HR = 1.0)
    ax.axvline(1.0, color='gray', linestyle='--', linewidth=1, label='No Effect (HR=1.0)')
    
    # Plot individual trial points and CIs
    for i, (trial, hr, low, high, w) in enumerate(zip(trials, hrs, ci_lows, ci_highs, weights_percent)):
        y = y_positions[i]
        # Error bar
        ax.plot([low, high], [y, y], color='#1f77b4', lw=2)
        # Point estimate marker size proportional to study weight
        marker_size = max(6, min(14, math.sqrt(w) * 3))
        ax.plot(hr, y, marker='s', markersize=marker_size, color='#1f77b4', markeredgecolor='black')
        
        # Text annotation on plot right side
        label_text = f"{hr:.2f} [{low:.2f}, {high:.2f}] ({w:.1f}%)"
        ax.text(max(ci_highs) * 1.35, y, label_text, va='center', fontsize=9, fontfamily='monospace')

    # Draw Summary Diamond for Random-Effects Pooled Estimate at y=0
    diamond_y = 0
    diamond_x = [re_ci[0], re_hr, re_ci[1], re_hr]
    diamond_y_pts = [diamond_y, diamond_y + 0.25, diamond_y, diamond_y - 0.25]
    ax.fill(diamond_x, diamond_y_pts, color='#d62728', alpha=0.8, label=f'RE Pooled HR: {re_hr:.2f}')
    
    # Right-hand text for pooled estimate
    pooled_label = f"{re_hr:.2f} [{re_ci[0]:.2f}, {re_ci[1]:.2f}] (100.0%)"
    ax.text(max(ci_highs) * 1.35, diamond_y, pooled_label, va='center', fontsize=9, fontweight='bold', fontfamily='monospace')

    # Formatting axes
    y_ticks = list(y_positions) + [0]
    y_labels = trials + ['RE Pooled Model']
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels, fontsize=10, fontweight='bold')
    
    ax.set_xlabel('Hazard Ratio (HR) & 95% CI', fontsize=11, fontweight='bold')
    ax.set_title(f'Cross-Trial Meta-Analysis Forest Plot: {comparison_name.upper()}', fontsize=12, fontweight='bold', pad=15)
    
    # Heterogeneity Footnote Annotation
    het_text = f"Heterogeneity: I² = {i_sq:.1f}%, τ² = {tau_sq:.4f}, Cochran's Q = {q_stat:.2f} (p = {p_val_q:.3f})"
    plt.figtext(0.12, 0.02, het_text, fontsize=9, fontstyle='italic', bbox=dict(boxstyle="round,pad=0.3", fc="whitesmoke", ec="gray", lw=0.5))

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='x', linestyle=':', alpha=0.6)
    
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.15)
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
