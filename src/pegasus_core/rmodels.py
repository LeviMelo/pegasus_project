"""R reference implementations PegaSUS fits through rpy2 (R 4.4.1, glmmTMB): the established package for a model
statsmodels does not carry (a negative-binomial GLMM), never a hand-rolled substitute (established-packages rule).

R starts once per process with an empty user profile and English messages: a user profile that loads other packages
aborted the embedded R's start, and R's Portuguese-locale messages (Latin-1) made rpy2 raise a decoding error instead
of R's message (the ABNc studies' bridge, 2026-11-22)."""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile

import numpy as np

R_HOME = os.environ.get("R_HOME", "C:/Program Files/R/R-4.4.1")
_ro = None


def r():
    """rpy2's robjects with R started and glmmTMB loaded."""
    global _ro
    if _ro is None:
        os.environ["R_HOME"] = R_HOME
        empty = os.path.join(tempfile.gettempdir(), "pegasus_empty_rprofile.R")
        if not os.path.exists(empty):
            open(empty, "w").close()
        os.environ["R_PROFILE_USER"] = empty
        os.environ["R_ENVIRON_USER"] = empty
        os.environ["LANGUAGE"] = "en"
        os.environ["LC_MESSAGES"] = "C"
        dll = os.path.join(R_HOME, "bin", "x64")
        os.environ["PATH"] = dll + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(dll)
        import rpy2.rinterface_lib.callbacks as cb

        def _safe(x: str) -> None:            # R's console through stderr, never raising (a detached job's stdout)
            with contextlib.suppress(Exception):
                sys.stderr.write(x)
        cb.consolewrite_print = _safe
        cb.consolewrite_warnerror = _safe
        import rpy2.robjects as ro

        ro.r('invisible(Sys.setenv(LANGUAGE = "en")); invisible(suppressWarnings(Sys.setlocale("LC_MESSAGES", "C")))')
        ro.r("suppressWarnings(suppressPackageStartupMessages(library(glmmTMB)))")
        _ro = ro
    return _ro


def nb_random_intercept(y: np.ndarray, offset: np.ndarray, z: np.ndarray, group: np.ndarray) -> tuple[float, float, bool]:
    """glmmTMB ``y ~ z + offset(offset) + (1 | group)``, family nbinom2: the coefficient of ``z``, its variance, and
    whether the fit converged (pdHess)."""
    ro = r()
    from rpy2.robjects import FloatVector, StrVector

    ro.globalenv["y_"] = FloatVector(np.asarray(y, dtype=float))
    ro.globalenv["o_"] = FloatVector(np.asarray(offset, dtype=float))
    ro.globalenv["z_"] = FloatVector(np.asarray(z, dtype=float))
    ro.globalenv["g_"] = StrVector([str(g) for g in group])
    got = ro.r("""local({
        d <- data.frame(y = y_, o = o_, z = z_, g = factor(g_))
        m <- glmmTMB(y ~ z + offset(o) + (1 | g), family = nbinom2, data = d)
        s <- summary(m)$coefficients$cond
        c(s["z", "Estimate"], s["z", "Std. Error"]^2, as.numeric(isTRUE(m$sdr$pdHess)))
    })""")
    return float(got[0]), float(got[1]), bool(got[2])
