import os
import math
import numpy as np
import rpy2.robjects as ro
from rpy2.robjects import conversion
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
    using R's gold-standard 'metafor' package via rpy2.
    """
    conversion.set_conversion(ro.default_converter)

    k = len(trial_data)
    if k < 2:
        raise ValueError("Meta-analysis requires at least 2 trial entries.")

    trials = []
    log_hrs = []
    vi_list = []
    hrs = []
    ci_lows = []
    ci_highs = []

    for entry in trial_data:
        nct_id = entry.get("nct_id", "Unknown")
        hr = float(entry.get("hr", 0.80))
        
        if "ci_lower" in entry and "ci_upper" in entry:
            ci_low = float(entry["ci_lower"])
            ci_high = float(entry["ci_upper"])
            se = (math.log(ci_high) - math.log(ci_low)) / (2 * 1.96)
        else:
            n_eval = float(entry.get("n_evaluable", 200))
            se = 2.0 / math.sqrt(n_eval)
            ci_low = math.exp(math.log(hr) - 1.96 * se)
            ci_high = math.exp(math.log(hr) + 1.96 * se)

        trials.append(nct_id)
        hrs.append(hr)
        ci_lows.append(ci_low)
        ci_highs.append(ci_high)
        log_hrs.append(math.log(hr))
        vi_list.append(se ** 2)

    os.makedirs(output_dir, exist_ok=True)
    plot_path = os.path.join(output_dir, f"forest_plot_{comparison_name}.png")

    # Pass data vectors to R environment
    ro.r.assign("yi", ro.FloatVector(log_hrs))
    ro.r.assign("vi", ro.FloatVector(vi_list))
    ro.r.assign("slab_names", ro.StrVector(trials))
    ro.r.assign("plot_file", plot_path)
    ro.r.assign("comp_title", f"Cross-Trial Forest Plot: {comparison_name.upper()}")

    # Execute R metafor analysis & render forest plot device
    r_code = """
    library(metafor)
    
    # 1. Random-Effects Model (DerSimonian-Laird)
    res_re <- rma(yi=yi, vi=vi, method="DL", slab=slab_names)
    
    # 2. Fixed-Effects Model
    res_fe <- rma(yi=yi, vi=vi, method="FE", slab=slab_names)
    
    # Extract weights (%)
    weights_re <- weights(res_re)
    
    # Render PNG via R graphics device
    png(filename=plot_file, width=2400, height=1400, res=300)
    forest(res_re, 
           atransf=exp, 
           at=log(c(0.2, 0.5, 1.0, 2.0)),
           xlab="Hazard Ratio (95% CI)", 
           main=comp_title,
           col="navy", 
           border="navy")
    dev.off()
    
    list(
        fe_b = as.numeric(res_fe$b[1]),
        fe_ci_lb = as.numeric(res_fe$ci.lb),
        fe_ci_ub = as.numeric(res_fe$ci.ub),
        re_b = as.numeric(res_re$b[1]),
        re_ci_lb = as.numeric(res_re$ci.lb),
        re_ci_ub = as.numeric(res_re$ci.ub),
        q_stat = as.numeric(res_re$QE),
        p_val_q = as.numeric(res_re$QEp),
        i_sq = as.numeric(res_re$I2),
        tau_sq = as.numeric(res_re$tau2),
        weights = as.numeric(weights_re)
    )
    """
    
    r_out = ro.r(r_code)
    
    fe_hr = math.exp(float(r_out.rx2('fe_b')[0]))
    fe_ci_low = math.exp(float(r_out.rx2('fe_ci_lb')[0]))
    fe_ci_high = math.exp(float(r_out.rx2('fe_ci_ub')[0]))

    re_hr = math.exp(float(r_out.rx2('re_b')[0]))
    re_ci_low = math.exp(float(r_out.rx2('re_ci_lb')[0]))
    re_ci_high = math.exp(float(r_out.rx2('re_ci_ub')[0]))

    q_stat = float(r_out.rx2('q_stat')[0])
    p_val_q = float(r_out.rx2('p_val_q')[0])
    i_sq = float(r_out.rx2('i_sq')[0])
    tau_sq = float(r_out.rx2('tau_sq')[0])
    w_re_percent = [float(x) for x in r_out.rx2('weights')]

    return MetaAnalysisResult(
        comparison_name=comparison_name,
        trials=trials,
        effect_sizes_hr=hrs,
        ci_lower_hr=ci_lows,
        ci_upper_hr=ci_highs,
        weights_random_percent=w_re_percent,
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
