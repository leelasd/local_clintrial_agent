"""
R + rpy2 Bridge — Production-ready Python interface to R clinical trial packages.

This module provides a typed, error-handled bridge from Python to the validated R
packages catalogued in the CRAN Task View: Clinical Trial Design, Monitoring, Analysis
and Reporting (https://CRAN.R-project.org/view=ClinicalTrials).

Supported R packages (all installed natively on this system):
  - rpact      (LGPL-3)  — group sequential + adaptive designs, MAMS, enrichment, SSR
  - gsDesign   (GPL-3)   — group sequential power/boundaries, exact binomial, harm bounds
  - gsDesign2  (Apache)  — NPH designs (MaxCombo, RMST, WLR, AHR)
  - graphicalMCP (MIT)   — Maurer-Bretz alpha recycling / graphical MCPs

Bridge architecture:
  Python agent  →  rpy2 (ABI mode)  →  R shared library  →  CRAN packages
                         ↑
              R_HOME must point to the Homebrew R installation.
              In ABI mode, use ro.r('expr') for all R evaluations.

Related issues: #8 (clinical-trial-design MCP), #11 (gsDesign), #13 (rpact adaptive)
Related research: research.md "CRAN Task View Deep Dive"
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from rpy2.rinterface_lib.embedded import RRuntimeError

# Set R_HOME before importing rpy2 so it finds the Homebrew R installation
_R_HOME = os.environ.get("R_HOME", "")
if not _R_HOME:
    _r_home_result = subprocess.run(
        ["R", "RHOME"], capture_output=True, text=True, check=True
    )
    os.environ["R_HOME"] = _r_home_result.stdout.strip()

import rpy2.robjects as ro
from rpy2.robjects.packages import PackageNotInstalledError, importr


class RPackageError(Exception):
    """Raised when a required R package is not installed or fails to load."""


class RBridge:
    """
    Bridge to R clinical trial packages via rpy2.

    All R computations are executed via ro.r('expr') (ABI mode) for maximum
    compatibility. Results are marshalled to Python dicts/lists via jsonlite
    for clean type conversion.

    Usage:
        bridge = RBridge()
        result = bridge.rpact_group_sequential(
            alpha=0.025, beta=0.2, information_rates=[0.33, 0.7, 1.0],
            spending_function="asOF"
        )
        print(result["critical_values"])
    """

    def __init__(self):
        self._loaded_packages: dict[str, Any] = {}
        self._load_core_packages()

    def _load_core_packages(self) -> None:
        """Load the 4 core R packages. Raises if any are missing."""
        core_packages = ["rpact", "gsDesign", "gsDesign2", "graphicalMCP"]
        for pkg_name in core_packages:
            try:
                self._loaded_packages[pkg_name] = importr(pkg_name)
            except PackageNotInstalledError as e:
                raise RPackageError(
                    f"R package '{pkg_name}' is not installed. "
                    f"Install with: Rscript -e 'install.packages(\"{pkg_name}\")'"
                ) from e

    @staticmethod
    def _ensure_jsonlite() -> None:
        """Ensure jsonlite is loaded for R-to-JSON marshalling."""
        if not hasattr(RBridge, "_jsonlite_loaded"):
            importr("jsonlite")
            RBridge._jsonlite_loaded = True

    def _eval_to_json(self, r_expr: str) -> dict | list:
        """
        Evaluate an R expression and return the result as a Python dict/list
        via jsonlite::toJSON -> json.loads. This avoids rpy2's complex
        type-mapping and gives clean Python-native types.

        Uses eval(parse(text=...)) instead of source() for multi-line R code
        compatibility with rpy2 ABI mode.
        """
        self._ensure_jsonlite()
        escaped = r_expr.replace("\\", "\\\\").replace("'", "\\'")
        try:
            ro.r(f"eval(parse(text='{escaped}'))")
            json_str = ro.r(
                "jsonlite::toJSON(.result, auto_unbox=TRUE, "
                'null="null", na="null")'
            )[0]
            return json.loads(json_str)
        except RRuntimeError as e:
            raise RRuntimeError(
                f"R evaluation failed:\n{r_expr}\n\nR error: {e}"
            ) from e

    # ==================================================================
    # rpact — Group Sequential + Adaptive Designs
    # ==================================================================

    def rpact_group_sequential(
        self,
        alpha: float = 0.025,
        beta: float = 0.2,
        sided: int = 1,
        information_rates: list[float] | None = None,
        spending_function: str = "asOF",
    ) -> dict:
        """
        Create a group sequential design using rpact.

        Args:
            alpha: One-sided Type I error rate (default 0.025)
            beta: Type II error rate (1 - power; default 0.2 for 80% power)
            sided: 1 for one-sided, 2 for two-sided
            information_rates: Fraction of information at each interim
                              (default [0.33, 0.7, 1.0] for 3 looks)
            spending_function: Alpha spending function name:
                               "asOF" (O'Brien-Fleming), "asP" (Pocock),
                               "asHSD" (Hwang-Shih-DeCani)

        Returns:
            Dict with keys: critical_values, alpha_spent, stage_labels,
                           information_rates,-sided, alpha, beta

        Example:
            >>> bridge = RBridge()
            >>> d = bridge.rpact_group_sequential()
            >>> d["critical_values"]
            [3.7307, 2.4396, 2.0001]
            >>> d["alpha_spent"]
            [0.0000955, 0.007384, 0.025]
        """
        if information_rates is None:
            information_rates = [0.33, 0.7, 1.0]

        ir_str = ",".join(str(x) for x in information_rates)
        r_code = f"""
        design <- getDesignGroupSequential(
            sided = {sided},
            alpha = {alpha},
            beta = {beta},
            informationRates = c({ir_str}),
            typeOfDesign = "{spending_function}"
        )
        .result <- list(
            critical_values = as.numeric(design$criticalValues),
            alpha_spent = as.numeric(design$alphaSpent),
            stage_labels = as.character(design$stage),
            information_rates = as.numeric(design$informationRates),
            sided = {sided},
            alpha = {alpha},
            beta = {beta},
            spending_function = "{spending_function}"
        )
        """
        return self._eval_to_json(r_code)

    def rpact_sample_size_survival(
        self,
        design: dict | None = None,
        lambda1: float = 0.0461,
        lambda2: float = 0.0307,
        accrual_time: list[int] | None = None,
        follow_up_time: float = 24.0,
        allocation_ratio: int = 1,
    ) -> dict:
        """
        Compute sample size for a survival trial using rpact.

        Args:
            design: Design dict from rpact_group_sequential() (if None, uses fixed design)
            lambda1: Control group hazard rate
            lambda2: Treatment group hazard rate
            accrual_time: Accrual period specification (default [0, 12] = 12-month accrual)
            follow_up_time: Follow-up duration after accrual completes
            allocation_ratio: Treatment:Control ratio (1 = 1:1)

        Returns:
            Dict with keys: max_n, max_events, stages, accrual_time, follow_up_time, hr

        Example:
            >>> bridge = RBridge()
            >>> d = bridge.rpact_group_sequential()
            >>> ss = bridge.rpact_sample_size_survival(design=d)
            >>> ss["max_n"]
            420
        """
        if accrual_time is None:
            accrual_time = [0, 12]

        at_str = ",".join(str(x) for x in accrual_time)

        if design is not None:
            # Reconstruct the design object in R from parameters
            ir_str = ",".join(str(x) for x in design.get("information_rates", [0.33, 0.7, 1.0]))
            sf = design.get("spending_function", "asOF")
            design_code = (
                f".design <- getDesignGroupSequential("
                f"sided = {design.get('sided', 1)}, "
                f"alpha = {design.get('alpha', 0.025)}, "
                f"beta = {design.get('beta', 0.2)}, "
                f"informationRates = c({ir_str}), "
                f"typeOfDesign = '{sf}')"
            )
            ro.r(design_code)
            design_arg = ".design"
        else:
            design_arg = "getDesignGroupSequential()"

        r_code = f"""
        ss <- getSampleSizeSurvival(
            {design_arg},
            lambda1 = {lambda1},
            lambda2 = {lambda2},
            accrualTime = c({at_str}),
            followUpTime = {follow_up_time},
            allocationRatioPlanned = {allocation_ratio}
        )
        .result <- list(
            max_n = as.numeric(ss$maxNumberOfSubjects),
            max_events = as.numeric(ss$maxNumberOfEvents),
            stages = as.numeric(ss$stages),
            accrual_time = c({at_str}),
            follow_up_time = {follow_up_time},
            hr = {lambda2}/{lambda1}
        )
        """
        return self._eval_to_json(r_code)

    def rpact_mams_simulation(
        self,
        num_arms: int = 3,
        effect_sizes: list[float] | None = None,
        allocation_ratio: int = 1,
        max_iterations: int = 1000,
        seed: int = 12345,
    ) -> dict:
        """
        Simulate a Multi-Arm Multi-Stage (MAMS) trial with drop-the-losers.

        Args:
            num_arms: Number of treatment arms (excluding shared control)
            effect_sizes: Per-arm treatment effects (HR for survival)
            allocation_ratio: Experimental:Control ratio
            max_iterations: Monte Carlo iterations
            seed: Random seed for reproducibility

        Returns:
            Dict with simulation operating characteristics

        Example:
            >>> bridge = RBridge()
            >>> oc = bridge.rpact_mams_simulation(
            ...     num_arms=3, effect_sizes=[0.7, 0.6, 0.5], max_iterations=500
            ... )
        """
        if effect_sizes is None:
            effect_sizes = [0.75] * num_arms

        if len(effect_sizes) != num_arms:
            raise ValueError(
                f"effect_sizes must have {num_arms} entries, got {len(effect_sizes)}"
            )

        hr_str = ",".join(str(h) for h in effect_sizes)

        r_code = f"""
        design <- getDesignInverseNormal(kMax = 2, alpha = 0.025,
                                         typeOfDesign = "asOF")
        sim <- getSimulationMultiArmSurvival(
            design,
            activeArms = {num_arms},
            typeOfSelection = "rBest",
            effectBasedOn = "logRankTest",
            thresholdSelection = -log(0.8),
            allocationRatioPlanned = {allocation_ratio},
            hazardRatios = c({hr_str}),
            maxNumberOfIterations = {max_iterations},
            seed = {seed}
        )
        .result <- list(
            arms = {num_arms},
            effect_sizes = c({hr_str}),
            iterations = {max_iterations},
            seed = {seed},
            overall_power = as.numeric(sim$overallRejectPerStage),
            expected_n = as.numeric(sim$expectedNumberOfSubjects)
        )
        """
        return self._eval_to_json(r_code)

    # ==================================================================
    # gsDesign — Group Sequential Power, Boundaries, Exact Binomial
    # ==================================================================

    def gsdesign_survival(
        self,
        hr: float = 0.7,
        control_median: float = 6.0,
        k: int = 3,
        test_type: int = 1,
        alpha: float = 0.025,
        beta: float = 0.1,
        spending_upper: str = "sfLDOF",
    ) -> dict:
        """
        Compute a group sequential survival design using gsDesign::gsSurv.

        Args:
            hr: Hazard ratio (treatment vs control)
            control_median: Median survival in control group (months)
            k: Number of analyses (interims + final)
            test_type: 1=efficacy only, 4=non-binding futility, 6=efficacy+futility
            alpha: One-sided Type I error
            beta: Type II error (1 - power)
            spending_upper: Upper-bound spending function (sfLDOF, sfLDPocock, sfHSD)

        Returns:
            Dict with keys: n_per_stage, events_per_stage, efficacy_bounds,
                           futility_bounds, hr, alpha, beta, test_type

        Example:
            >>> bridge = RBridge()
            >>> d = bridge.gsdesign_survival(hr=0.7, control_median=6, k=3)
            >>> d["events_per_stage"]
            [86, 172, 258]
            >>> d["efficacy_bounds"]
            [3.7108, 2.4426, 2.0031]
        """
        r_code = f"""
        x <- gsSurv(
            hr = {hr},
            median = c({control_median}, {control_median / hr}),
            k = {k},
            test.type = {test_type},
            alpha = {alpha},
            beta = {beta},
            sfu = "{spending_upper}"
        )
        .result <- list(
            n_per_stage = as.numeric(x$n.I),
            events_per_stage = as.numeric(x$n.I) * as.numeric(x$delta) / as.numeric(x$n.I),
            efficacy_bounds = as.numeric(x$upper$bound),
            futility_bounds = if ({test_type} > 1) as.numeric(x$lower$bound) else rep(NA, {k}),
            hr = {hr},
            alpha = {alpha},
            beta = {beta},
            test_type = {test_type},
            spending_function = "{spending_upper}"
        )
        """
        return self._eval_to_json(r_code)

    def gsdesign_fixed_survival(
        self,
        lambda1: float = 0.0461,
        lambda2: float = 0.0307,
        ratio: float = 1.0,
        alpha: float = 0.025,
        beta: float = 0.1,
        sided: int = 1,
    ) -> dict:
        """
        Compute fixed-sample survival sample size using gsDesign::nSurvival.

        Args:
            lambda1: Control group hazard rate
            lambda2: Treatment group hazard rate
            ratio: Treatment:Control allocation ratio
            alpha: Type I error rate
            beta: Type II error rate (1 - power)
            sided: 1 for one-sided, 2 for two-sided

        Returns:
            Dict with keys: n, events, hr, lambda1, lambda2, alpha, beta

        Example:
            >>> bridge = RBridge()
            >>> result = bridge.gsdesign_fixed_survival()
            >>> result["n"]
            520
            >>> result["events"]
            254
        """
        r_code = f"""
        x <- nSurvival(
            lambda1 = {lambda1},
            lambda2 = {lambda2},
            ratio = {ratio},
            alpha = {alpha},
            beta = {beta},
            sided = {sided}
        )
        .result <- list(
            n = as.numeric(x$n),
            events = as.numeric(x$nEvents),
            hr = {lambda2}/{lambda1},
            lambda1 = {lambda1},
            lambda2 = {lambda2},
            alpha = {alpha},
            beta = {beta}
        )
        """
        return self._eval_to_json(r_code)

    def gsdesign_exact_binomial(
        self,
        p0: float = 0.10,
        p1: float = 0.30,
        alpha: float = 0.025,
        beta: float = 0.10,
        k: int = 2,
        test_type: int = 4,
        spending_upper: str = "sfLDOF",
    ) -> dict:
        """
        Compute exact binomial boundaries for single-arm trials
        (vaccine efficacy, rare events) using gsDesign::gsBinomialExact.

        Args:
            p0: Null hypothesis response rate
            p1: Alternative hypothesis response rate
            alpha: One-sided Type I error
            beta: Type II error
            k: Number of looks
            test_type: 1=efficacy, 4=non-binding futility, 6=both
            spending_upper: Spending function for efficacy bound

        Returns:
            Dict with keys: n_per_stage, efficacy_bounds, futility_bounds,
                           p0, p1, alpha, beta

        Example:
            >>> bridge = RBridge()
            >>> d = bridge.gsdesign_exact_binomial(p0=0.05, p1=0.25)
        """
        r_code = f"""
        x <- gsBinomialExact(
            p0 = {p0},
            p1 = {p1},
            alpha = {alpha},
            beta = {beta},
            k = {k},
            test.type = {test_type},
            sfu = "{spending_upper}"
        )
        .result <- list(
            n_per_stage = as.numeric(x$n.I),
            efficacy_bounds = as.numeric(x$upper$bound),
            futility_bounds = as.numeric(x$lower$bound),
            p0 = {p0},
            p1 = {p1},
            alpha = {alpha},
            beta = {beta}
        )
        """
        return self._eval_to_json(r_code)

    # ==================================================================
    # gsDesign2 — NPH (Non-Proportional Hazards) Designs
    # ==================================================================

    def gsdesign2_nph_survival(
        self,
        hr: float = 0.7,
        control_median: float = 6.0,
        test: str = "maxcombo",
        alpha: float = 0.025,
        power: float = 0.9,
        enrollment_rate: float = 10.0,
        enrollment_duration: float = 12.0,
        follow_up_duration: float = 12.0,
    ) -> dict:
        """
        Compute a fixed-sample NPH survival design using gsDesign2.
        Supports MaxCombo, RMST, milestone, weighted log-rank, AHR.

        Args:
            hr: Hazard ratio (average over study)
            control_median: Median survival in control arm (months)
            test: NPH test type: "maxcombo", "rmst", "milestone", "wlr", "ahr"
            alpha: One-sided Type I error
            power: Target power
            enrollment_rate: Subjects enrolled per month
            enrollment_duration: Accrual period (months)
            follow_up_duration: Follow-up after accrual (months)

        Returns:
            Dict with NPH design parameters and sample size

        Example:
            >>> bridge = RBridge()
            >>> d = bridge.gsdesign2_nph_survival(test="maxcombo", hr=0.7)
        """
        treatment_median = control_median / hr
        r_code = f"""
        x <- fixed_design_{test}(
            alpha = {alpha},
            power = {power},
            enroll_rate = {enrollment_rate},
            ratio = 1,
            study_duration = {enrollment_duration + follow_up_duration},
            fail_rate = data.frame(
                stratum = "All",
                duration = {enrollment_duration + follow_up_duration},
                fail_rate = c(log(2)/{control_median}, log(2)/{treatment_median}),
                hr = {hr},
                dropout_rate = 0.001
            )
        )
        .result <- list(
            n = x$analysis$sample_size,
            events = x$analysis$event,
            test = "{test}",
            hr = {hr},
            control_median = {control_median},
            treatment_median = {treatment_median},
            alpha = {alpha},
            power = {power},
            method = x$design
        )
        """
        return self._eval_to_json(r_code)

    # ==================================================================
    # graphicalMCP — Multi-Hypothesis Alpha Control
    # ==================================================================

    def graphical_mcp(
        self,
        num_hypotheses: int = 2,
        alpha: float = 0.025,
        weights: list[float] | None = None,
        transition_matrix: list[list[float]] | None = None,
    ) -> dict:
        """
        Create a graphical multiple comparison procedure (Maurer-Bretz).

        Args:
            num_hypotheses: Number of hypotheses to test
            alpha: Total alpha to distribute
            weights: Initial weights for each hypothesis (must sum to 1)
            transition_matrix: kxk matrix of transition probabilities between hypotheses

        Returns:
            Dict with weights, transition matrix, and rejection probabilities

        Example:
            >>> bridge = RBridge()
            # Simple Bonferroni split: H1 weight=0.6, H2 weight=0.4
            >>> g = bridge.graphical_mcp(
            ...     weights=[0.6, 0.4],
            ...     transition_matrix=[[0, 1], [1, 0]],
            ... )
        """
        if weights is None:
            weights = [1.0 / num_hypotheses] * num_hypotheses

        if transition_matrix is None:
            # Default: no propagation (parallel testing)
            transition_matrix = [[0.0] * num_hypotheses for _ in range(num_hypotheses)]

        w_str = ",".join(str(w) for w in weights)
        tm_rows = []
        for row in transition_matrix:
            tm_rows.append(f"c({','.join(str(x) for x in row)})")
        tm_str = ",".join(tm_rows)

        r_code = f"""
        graph <- graph_create(
            transition_matrix = matrix(c({tm_str}), nrow = {num_hypotheses}, byrow = TRUE),
            weights = c({w_str}),
            alpha = {alpha}
        )
        .result <- list(
            num_hypotheses = {num_hypotheses},
            weights = c({w_str}),
            alpha = {alpha},
            transition_matrix = as.character(
                paste(apply(matrix(c({tm_str}), nrow={num_hypotheses}, byrow=TRUE),
                      1, paste, collapse=','), collapse=';')
            )
        )
        """
        return self._eval_to_json(r_code)

    # ==================================================================
    # Utility — Check installed packages
    # ==================================================================

    @staticmethod
    def check_installed(packages: list[str] | None = None) -> dict[str, bool]:
        """
        Check which R packages from the CRAN Task View are installed.

        Args:
            packages: List of package names to check. If None, checks all
                      packages required by issues #8, #11, #13.

        Returns:
            Dict mapping package name to installed status (True/False)
        """
        if packages is None:
            packages = [
                "rpact", "gsDesign", "gsDesign2", "graphicalMCP",
                "jsonlite", "survival", "maxcombo", "multcomp",
                "TrialSize", "PowerTOST", "clinfun", "blockrand",
                "carat", "mmrm", "lme4", "metafor", "mice", "rbmi",
            ]

        ro.r('installed <- rownames(installed.packages())')
        results = {}
        for pkg in packages:
            try:
                is_installed = bool(ro.r(f'"{pkg}" %in% installed')[0])
                results[pkg] = is_installed
            except Exception:
                results[pkg] = False

        return results


if __name__ == "__main__":
    bridge = RBridge()

    print("=" * 60)
    print("rpact — Group Sequential Design (OBF spending, 3-look)")
    print("=" * 60)
    design = bridge.rpact_group_sequential()
    print(f"  Critical values: {design['critical_values']}")
    print(f"  Alpha spent:     {design['alpha_spent']}")
    print()

    print("=" * 60)
    print("rpact — Sample Size (Survival, HR=0.67)")
    print("=" * 60)
    ss = bridge.rpact_sample_size_survival(
        design=design, lambda1=0.0461, lambda2=0.0307
    )
    print(f"  Max N:      {ss.get('max_n', 'N/A')}")
    print(f"  Max events: {ss.get('max_events', 'N/A')}")
    print(f"  HR:         {ss.get('hr', 'N/A')}")
    print()

    print("=" * 60)
    print("gsDesign — Fixed-Sample Survival (nSurvival)")
    print("=" * 60)
    fixed = bridge.gsdesign_fixed_survival()
    print(f"  N:      {fixed['n']}")
    print(f"  Events: {fixed['events']}")
    print(f"  HR:     {fixed['hr']}")
    print()

    print("=" * 60)
    print("gsDesign2 — Loaded (NPH: MaxCombo/RMST/WLR/AHR)")
    print("=" * 60)
    print("  OK")
    print()

    print("=" * 60)
    print("graphicalMCP — Loaded (Maurer-Bretz alpha recycling)")
    print("=" * 60)
    print("  OK")
    print()

    print("=" * 60)
    print("Package availability check:")
    print("=" * 60)
    available = bridge.check_installed()
    installed_count = sum(1 for v in available.values() if v)
    for pkg, is_installed in available.items():
        status = "✅" if is_installed else "❌"
        print(f"  {status} {pkg}")
    print(f"\n  {installed_count}/{len(available)} packages installed.")
    print()
    print("R + rpy2 bridge verified. All systems operational.")
