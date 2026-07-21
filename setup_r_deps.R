#!/usr/bin/env Rscript
# ==============================================================================
# R CRAN Dependency Verification & Setup Script
# ==============================================================================
# Verifies and installs required biostatistical R packages for local_clintrial_agent.
# Grounded in Friedman, Furberg & DeMets, "Fundamentals of Clinical Trials" (4th ed.).

cat("==============================================================================\n")
cat("  CLINICAL TRIAL AGENT — R DEPENDENCY VERIFICATION & SETUP\n")
cat("==============================================================================\n\n")

# Minimum R version requirement
min_r_version <- "4.2.0"
current_r_version <- paste(R.version$major, R.version$minor, sep = ".")

if (numeric_version(current_r_version) < numeric_version(min_r_version)) {
  stop(sprintf("R version >= %s required. Found: %s", min_r_version, current_r_version))
}
cat(sprintf("✓ R Engine Version: %s (>= %s)\n\n", current_r_version, min_r_version))

# Required CRAN Packages with Minimum Versions
required_packages <- list(
  jsonlite     = "1.8.0",   # JSON marshalling for RBridge
  rpact        = "3.5.0",   # Group sequential & adaptive trial designs (LGPL-3)
  gsDesign     = "3.6.0",   # Group sequential & survival sizing (GPL-3)
  gsDesign2    = "1.1.0",   # Non-proportional hazards survival sizing
  graphicalMCP = "0.2.0",   # Graphical multiple comparison procedures
  clinfun      = "1.1.0",   # Simon's two-stage Phase II design
  PowerTOST    = "1.5.0",   # Bioequivalence crossover sample size
  dfcrm        = "0.2.0",   # Continual Reassessment Method (CRM) for dose-finding
  blockrand    = "1.5.0",   # Blocked & stratified randomization schedule generation
  metafor      = "4.0.0"    # Inverse-variance & DerSimonian-Laird meta-analysis
)

# Configure CRAN mirror if not set
options(repos = c(CRAN = "https://cloud.r-project.org"))

missing_packages <- c()
installed_pkgs <- rownames(installed.packages())

cat("Checking Required Biostatistical R Packages:\n")
cat("------------------------------------------------------------------------------\n")

for (pkg in names(required_packages)) {
  min_ver <- required_packages[[pkg]]
  if (pkg %in% installed_pkgs) {
    curr_ver <- as.character(packageVersion(pkg))
    if (numeric_version(curr_ver) >= numeric_version(min_ver)) {
      cat(sprintf("  ✓ %-15s v%-10s (Minimum: v%s)\n", pkg, curr_ver, min_ver))
    } else {
      cat(sprintf("  ⚠ %-15s v%-10s (OUTDATED — Need: v%s)\n", pkg, curr_ver, min_ver))
      missing_packages <- c(missing_packages, pkg)
    }
  } else {
    cat(sprintf("  ✗ %-15s NOT INSTALLED  (Required: v%s)\n", pkg, min_ver))
    missing_packages <- c(missing_packages, pkg)
  }
}

cat("------------------------------------------------------------------------------\n")

if (length(missing_packages) > 0) {
  cat(sprintf("\nInstalling %d missing/outdated package(s): %s...\n\n", 
              length(missing_packages), paste(missing_packages, collapse = ", ")))
  install.packages(missing_packages, quiet = FALSE)
  cat("\n✓ Installation complete!\n")
} else {
  cat("\n✓ All R dependencies are installed and up to date!\n")
}

cat("==============================================================================\n")
