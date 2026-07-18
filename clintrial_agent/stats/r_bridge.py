import json
import os
import subprocess
from typing import Any
from rpy2.rinterface_lib.embedded import RRuntimeError

# Resolve R_HOME before importing rpy2 to ensure it loads the Homebrew R build
_R_HOME = os.environ.get("R_HOME", "")
if not _R_HOME:
    try:
        _r_home_result = subprocess.run(
            ["R", "RHOME"], capture_output=True, text=True, check=True
        )
        os.environ["R_HOME"] = _r_home_result.stdout.strip()
    except Exception:
        # Fallback to standard Homebrew Apple Silicon R directory if not in PATH
        mac_homebrew_r = "/opt/homebrew/Cellar/r/4.6.1/lib/R"
        if os.path.exists(mac_homebrew_r):
            os.environ["R_HOME"] = mac_homebrew_r
        else:
            mac_homebrew_r_alt = "/opt/homebrew/lib/R"
            if os.path.exists(mac_homebrew_r_alt):
                os.environ["R_HOME"] = mac_homebrew_r_alt

import rpy2.robjects as ro
from rpy2.robjects.packages import PackageNotInstalledError, importr

class RPackageError(Exception):
    """Raised when a required R package is not installed or fails to load."""
    pass

class RBridge:
    """
    Bridge to R clinical trial packages via rpy2.
    Uses ro.r('expr') in ABI-compatible mode for robustness and jsonlite for data serialization.
    """
    def __init__(self):
        self._loaded_packages: dict[str, Any] = {}
        self._load_core_packages()

    def _load_core_packages(self) -> None:
        """Load the 4 core R packages. Raises if any are missing."""
        core_packages = ["rpact", "gsDesign", "gsDesign2", "graphicalMCP"]
        for pkg_name in core_packages:
            try:
                self._loaded_packages[pkg_name] = importr(pkg_name, on_conflict="warn")
            except PackageNotInstalledError as e:
                raise RPackageError(
                    f"R package '{pkg_name}' is not installed. "
                    f"Install with: Rscript -e 'install.packages(\"{pkg_name}\")'"
                ) from e

    @staticmethod
    def _ensure_jsonlite() -> None:
        """Ensure jsonlite is loaded for R-to-JSON marshalling."""
        if not hasattr(RBridge, "_jsonlite_loaded"):
            importr("jsonlite", on_conflict="warn")
            RBridge._jsonlite_loaded = True

    def _ensure_package(self, pkg_name: str) -> None:
        """Ensure an R package is loaded."""
        if pkg_name not in self._loaded_packages:
            try:
                self._loaded_packages[pkg_name] = importr(pkg_name, on_conflict="warn")
            except PackageNotInstalledError as e:
                raise RPackageError(
                    f"R package '{pkg_name}' is not installed. "
                    f"Install with: Rscript -e 'install.packages(\"{pkg_name}\")'"
                ) from e

    def _eval_to_json(self, r_expr: str) -> dict | list:
        """
        Evaluate an R expression and return the result as a Python dict/list.
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

    def rpact_group_sequential(
        self,
        alpha: float = 0.025,
        beta: float = 0.2,
        sided: int = 1,
        information_rates: list[float] | None = None,
        spending_function: str = "asOF",
    ) -> dict:
        """Create a group sequential design using rpact."""
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
        """Compute sample size for a survival trial using rpact."""
        if accrual_time is None:
            accrual_time = [0, 12]

        at_str = ",".join(str(x) for x in accrual_time)

        if design is not None:
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
        """Simulate a Multi-Arm Multi-Stage (MAMS) trial with drop-the-losers."""
        if effect_sizes is None:
            effect_sizes = [0.75] * num_arms
        if len(effect_sizes) != num_arms:
            raise ValueError(f"effect_sizes must have {num_arms} entries, got {len(effect_sizes)}")

        hr_str = ",".join(str(h) for h in effect_sizes)
        r_code = f"""
        design <- getDesignInverseNormal(kMax = 2, alpha = 0.025, typeOfDesign = "asOF")
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
        """Compute a group sequential survival design using gsDesign::gsSurv."""
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
        """Compute fixed-sample survival sample size using gsDesign::nSurvival."""
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
        """Compute exact binomial boundaries for single-arm trials using gsDesign::gsBinomialExact."""
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
        """Compute a fixed-sample NPH survival design using gsDesign2."""
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

    def graphical_mcp(
        self,
        num_hypotheses: int = 2,
        alpha: float = 0.025,
        weights: list[float] | None = None,
        transition_matrix: list[list[float]] | None = None,
    ) -> dict:
        """Create a graphical multiple comparison procedure."""
        if weights is None:
            weights = [1.0 / num_hypotheses] * num_hypotheses
        if transition_matrix is None:
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

    def dfcrm_crm(
        self,
        prior: list[float],
        target: float,
        tox: list[int],
        level: list[int],
    ) -> dict:
        """Update the Continual Reassessment Method (CRM) model to recommend the next dose."""
        self._ensure_package("dfcrm")
        prior_str = ",".join(str(p) for p in prior)
        tox_str = ",".join(str(t) for t in tox)
        level_str = ",".join(str(l) for l in level)

        r_code = f"""
        fit <- crm(
            prior = c({prior_str}),
            target = {target},
            tox = c({tox_str}),
            level = c({level_str})
        )
        .result <- list(
            mtd = as.integer(fit$mtd),
            ptox = as.numeric(fit$ptox),
            dose_next = as.integer(fit$mtd)
        )
        """
        return self._eval_to_json(r_code)

    def blockrand_generate(
        self,
        n: int,
        num_levels: int = 2,
        levels: list[str] | None = None,
        block_sizes: list[int] | None = None,
    ) -> dict:
        """Generate a blocked randomization list for trial participants."""
        self._ensure_package("blockrand")
        if levels is None:
            levels = [chr(65 + i) for i in range(num_levels)]
        if block_sizes is None:
            block_sizes = [2, 4]

        levels_str = ",".join(f'"{l}"' for l in levels)
        bs_str = ",".join(str(b) for b in block_sizes)

        r_code = f"""
        res <- blockrand(
            n = {n},
            num.levels = {num_levels},
            levels = c({levels_str}),
            block.sizes = c({bs_str})
        )
        .result <- list(
            id = as.integer(res$id),
            block_id = as.integer(res$block.id),
            block_size = as.integer(res$block.size),
            treatment = as.character(res$treatment)
        )
        """
        return self._eval_to_json(r_code)

    def powertost_sample_size(
        self,
        alpha: float = 0.05,
        target_power: float = 0.8,
        cv: float = 0.2,
        theta0: float = 0.95,
        theta1: float = 0.8,
        theta2: float = 1.25,
        design: str = "2x2",
    ) -> dict:
        """Calculate sample size for bioequivalence testing (TOST)."""
        self._ensure_package("PowerTOST")
        r_code = f"""
        res <- sampleN.TOST(
            alpha = {alpha},
            targetpower = {target_power},
            CV = {cv},
            theta0 = {theta0},
            theta1 = {theta1},
            theta2 = {theta2},
            design = "{design}",
            print = FALSE
        )
        .result <- list(
            sample_size = as.integer(res[["Sample size"]]),
            achieved_power = as.numeric(res[["Achieved power"]]),
            alpha = {alpha},
            cv = {cv},
            target_power = {target_power}
        )
        """
        return self._eval_to_json(r_code)

    def clinfun_simon2stage(
        self,
        pu: float,
        pa: float,
        ep1: float = 0.05,
        ep2: float = 0.2,
    ) -> dict:
        """Calculate Simon's optimal and minimax two-stage designs for Phase II trials."""
        self._ensure_package("clinfun")
        r_code = f"""
        res <- ph2simon(
            pu = {pu},
            pa = {pa},
            ep1 = {ep1},
            ep2 = {ep2}
        )
        adm <- clinfun:::twostage.admissible(res)
        minimax <- adm[1, ]
        optimal <- adm[nrow(adm), ]
        .result <- list(
            pu = {pu},
            pa = {pa},
            alpha = {ep1},
            beta = {ep2},
            optimal = list(
                r1 = as.integer(optimal["r1"]),
                n1 = as.integer(optimal["n1"]),
                r = as.integer(optimal["r"]),
                n = as.integer(optimal["n"]),
                en_p0 = as.numeric(optimal["EN(p0)"]),
                pet_p0 = as.numeric(optimal["PET(p0)"])
            ),
            minimax = list(
                r1 = as.integer(minimax["r1"]),
                n1 = as.integer(minimax["n1"]),
                r = as.integer(minimax["r"]),
                n = as.integer(minimax["n"]),
                en_p0 = as.numeric(minimax["EN(p0)"]),
                pet_p0 = as.numeric(minimax["PET(p0)"])
            )
        )
        """
        return self._eval_to_json(r_code)

    @staticmethod
    def check_installed(packages: list[str] | None = None) -> dict[str, bool]:
        """Check which R packages from the CRAN Task View are installed."""
        if packages is None:
            packages = [
                "rpact", "gsDesign", "gsDesign2", "graphicalMCP",
                "jsonlite", "survival", "maxcombo", "multcomp",
                "TrialSize", "PowerTOST", "clinfun", "blockrand",
                "carat", "mmrm", "lme4", "metafor", "mice", "rbmi",
                "dfcrm",
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
