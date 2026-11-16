# Shared helpers for the analysis notebooks: data loading, figure style, and statistics.
# python 3.14.10, pandas 2.3.3, numpy 2.5.4, scipy 1.18.1, matplotlib 3.11.2, scikit-learn 1.9.1
# Checked by test_helpers.py (run: python test_helpers.py from this folder).
#
# Section 1: Load the processed table
# Section 2: Figure style
# Section 3: DeLong test for AUC
# Section 4: Bootstrap confidence intervals
# Section 5: Model preprocessing
# Section 6: Model pipelines shared by notebooks 02 to 04
import warnings

import numpy as np
import pandas as pd
from scipy import stats

from config import CRASHES, FIGURES, PROCESSED, SEED

# --- Section 1: Load the processed table ---

# One row per firm per crash, written by 07_build_features.py
FIRMS_FILE = PROCESSED / "firm_crash.parquet"


def load_firms():
    if not FIRMS_FILE.exists():
        raise FileNotFoundError(f"{FIRMS_FILE.name} isn't built yet. "
                                "Run 06_build_labels.py and 07_build_features.py first.")
    return pd.read_parquet(FIRMS_FILE)


# --- Section 2: Figure style ---

# Crash colors are fixed, so a crash keeps its color in every figure and slide.
# They pass colorblind checks as a set, but aqua is low contrast on white,
# so always name crashes with a legend or direct labels, never color alone.
CRASH_COLORS = {"covid_2020": "#2a78d6", "rates_2022": "#eb6834", "tariff_2025": "#1baf7a"}
CRASH_LABELS = {"covid_2020": "COVID-19 (2020)", "rates_2022": "Rate hikes (2022)",
                "tariff_2025": "Tariffs (2025)"}
CRASH_SHORT = {"covid_2020": "2020", "rates_2022": "2022", "tariff_2025": "2025"}  # tight axes
INK, MUTED, GRID, BASELINE = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"
assert set(CRASH_COLORS) == set(CRASHES) == set(CRASH_LABELS) == set(CRASH_SHORT)


def set_style():
    """Use the same look for every figure: light horizontal grid, no top or right frame, 2px lines."""
    import matplotlib as mpl
    mpl.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
        "figure.facecolor": "white", "axes.facecolor": "white",
        "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.labelsize": 11,
        "text.color": INK, "axes.labelcolor": MUTED, "axes.edgecolor": BASELINE,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
        "lines.linewidth": 2, "lines.markersize": 7,
        "legend.frameon": False,
        "axes.prop_cycle": mpl.cycler(color=list(CRASH_COLORS.values())),
    })


def save_figure(fig, name):
    """Save to figures/<name>.png for the slides and report."""
    FIGURES.mkdir(exist_ok=True)
    path = FIGURES / f"{name}.png"
    fig.savefig(path)
    return path


# --- Section 3: DeLong test for AUC ---
# Fast DeLong (Sun and Xu, 2014). Ties get average ranks, matching scikit-learn's AUC.

def _delong_parts(y, scores):
    """AUCs and their covariance matrix for one or more score columns on the same rows."""
    y = np.asarray(y).astype(bool)
    scores = np.atleast_2d(np.asarray(scores, dtype=float))
    m, n = y.sum(), (~y).sum()
    if m < 2 or n < 2:
        raise ValueError("Need at least 2 positive and 2 negative cases.")
    pos, neg = scores[:, y], scores[:, ~y]
    rank_pos = stats.rankdata(pos, axis=1)
    rank_neg = stats.rankdata(neg, axis=1)
    rank_all = stats.rankdata(np.hstack([pos, neg]), axis=1)
    aucs = (rank_all[:, :m].sum(axis=1) - m * (m + 1) / 2) / (m * n)
    v_pos = (rank_all[:, :m] - rank_pos) / n
    v_neg = 1 - (rank_all[:, m:] - rank_neg) / m
    cov = np.atleast_2d(np.cov(v_pos)) / m + np.atleast_2d(np.cov(v_neg)) / n
    return aucs, cov


def delong_ci(y, scores, alpha=0.05):
    """AUC with a DeLong confidence interval."""
    aucs, cov = _delong_parts(y, scores)
    se = np.sqrt(cov[0, 0])
    z = stats.norm.ppf(1 - alpha / 2)
    return {"auc": aucs[0], "se": se,
            "low": max(0.0, aucs[0] - z * se), "high": min(1.0, aucs[0] + z * se)}


def delong_test(y, scores_a, scores_b):
    """Two-sided test that two models have the same AUC on the same test rows."""
    aucs, cov = _delong_parts(y, np.vstack([scores_a, scores_b]))
    diff = aucs[0] - aucs[1]
    se = np.sqrt(max(cov[0, 0] + cov[1, 1] - 2 * cov[0, 1], 0.0))
    z = diff / se if se > 0 else 0.0
    return {"auc_a": aucs[0], "auc_b": aucs[1], "diff": diff, "se": se,
            "z": z, "p": 2 * stats.norm.sf(abs(z))}


# --- Section 4: Bootstrap confidence intervals ---

def bootstrap_ci(statistic, *arrays, groups=None, n_boot=2000, alpha=0.05, seed=SEED):
    """Percentile interval for statistic(*arrays).

    With groups (such as firm IDs), whole firms are resampled, so a firm that appears
    in several crashes stays together. Draws where the statistic fails or isn't a
    finite number, like an AUC on a resample with only one class (scikit-learn returns
    nan there), are skipped and counted.
    """
    arrays = [np.asarray(a) for a in arrays]
    rng = np.random.default_rng(seed)
    if groups is None:
        index_sets = None
        n = len(arrays[0])
    else:
        codes, _ = pd.factorize(np.asarray(groups))
        order = np.argsort(codes, kind="stable")
        index_sets = np.split(order, np.cumsum(np.bincount(codes))[:-1])
        n = len(index_sets)
    values, skipped = [], 0
    for _ in range(n_boot):
        picks = rng.integers(0, n, n)
        rows = picks if index_sets is None else np.concatenate([index_sets[i] for i in picks])
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                value = statistic(*(a[rows] for a in arrays))
        except ValueError:
            value = np.nan
        if np.isfinite(value):
            values.append(value)
        else:
            skipped += 1
    values = np.asarray(values)
    return {"estimate": statistic(*arrays),
            "low": np.quantile(values, alpha / 2), "high": np.quantile(values, 1 - alpha / 2),
            "n_boot": len(values), "skipped": skipped}


# --- Section 5: Model preprocessing ---
# Used inside scikit-learn pipelines, so the limits come from training rows only.
from sklearn.base import BaseEstimator, TransformerMixin  # noqa: E402


class Winsorizer(BaseEstimator, TransformerMixin):
    """Clip each column to its training quantiles (default 1st and 99th percentile).

    Missing values stay missing, so an imputer can follow. Ratios like interest
    coverage have extreme tails that would otherwise dominate linear models.
    """

    def __init__(self, low=0.01, high=0.99):
        self.low = low
        self.high = high

    def fit(self, X, y=None):
        X = np.asarray(X, dtype=float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-missing columns
            self.low_ = np.nanquantile(X, self.low, axis=0)
            self.high_ = np.nanquantile(X, self.high, axis=0)
        self.n_features_in_ = X.shape[1]
        return self

    def transform(self, X):
        X = np.asarray(X, dtype=float)
        return np.clip(X, self.low_, self.high_)

    def get_feature_names_out(self, input_features=None):
        if input_features is None:
            input_features = [f"x{i}" for i in range(self.n_features_in_)]
        return np.asarray(input_features, dtype=object)


# --- Section 6: Model pipelines shared by notebooks 02 to 04 ---
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

FEATURES = ["current_ratio", "cash_to_assets", "debt_to_assets", "liabilities_to_assets",
            "interest_coverage", "net_margin", "operating_margin", "return_on_assets",
            "ocf_to_assets", "revenue_growth", "asset_growth", "log_assets",
            "log_market_value", "volatility_12m", "momentum_12_1", "beta"]
SIZE = ["log_assets", "log_market_value"]


def model_columns(firms):
    """Column sets for the full model and the sector-and-size baseline."""
    flags = [f"{f}_missing" for f in FEATURES if f"{f}_missing" in firms]
    full = {"numeric": FEATURES, "flags": flags + ["is_financial"], "category": ["sic_division"]}
    base = {"numeric": SIZE, "flags": [f for f in flags if f.split("_missing")[0] in SIZE],
            "category": ["sic_division"]}
    return full, base


def make_model(kind, cols):
    """Preprocessing fit on the training rows, then the classifier. Fixed settings
    (decided 2026-11-08): kind is "baseline" or "logit" (logistic regression),
    "forest", or "lgbm"."""
    from lightgbm import LGBMClassifier
    numeric = [("cap", Winsorizer()), ("impute", SimpleImputer(strategy="median"))]
    if kind in ("logit", "baseline"):
        numeric.append(("scale", StandardScaler()))
    prep = ColumnTransformer([
        ("num", Pipeline(numeric), cols["numeric"]),
        ("flags", "passthrough", cols["flags"]),
        ("sector", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cols["category"]),
    ])
    if kind in ("logit", "baseline"):
        clf = LogisticRegression(C=0.5, class_weight="balanced", max_iter=5000)
    elif kind == "forest":
        clf = RandomForestClassifier(n_estimators=500, min_samples_leaf=20, max_features="sqrt",
                                     class_weight="balanced_subsample", n_jobs=-1, random_state=SEED)
    elif kind == "lgbm":
        clf = LGBMClassifier(n_estimators=300, num_leaves=15, learning_rate=0.03,
                             min_child_samples=40, subsample=0.8, subsample_freq=1,
                             colsample_bytree=0.8, reg_lambda=1.0, class_weight="balanced",
                             random_state=SEED, verbose=-1)
    else:
        raise ValueError(kind)
    return Pipeline([("prep", prep), ("model", clf)])


def to_ranks(df, columns=FEATURES):
    """Each feature as a percentile within its own crash (uses no labels)."""
    out = df.copy()
    out[columns] = df.groupby("crash")[columns].rank(pct=True)
    return out
