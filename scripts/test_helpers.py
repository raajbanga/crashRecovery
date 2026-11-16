# Checks for helpers.py. Run from the scripts folder: python test_helpers.py
# Uses simulated data only, so it runs before any project data is ready.
import numpy as np
from scipy import stats
from sklearn.metrics import roc_auc_score

from helpers import bootstrap_ci, delong_ci, delong_test

rng = np.random.default_rng(42)


def make_scores(n, shift, corr=0.6, n_models=2):
    """Correlated scores for n_models on the same rows; positives are shifted up."""
    y = rng.random(n) < 0.3
    base = rng.normal(size=n)
    cols = [corr * base + np.sqrt(1 - corr**2) * rng.normal(size=n) + s * y
            for s in ([shift] * n_models if np.isscalar(shift) else shift)]
    return y.astype(int), cols


# Check 1: AUC matches scikit-learn, with and without ties
y, (a, b) = make_scores(400, [0.8, 0.5])
for scores in (a, np.round(a, 1)):
    assert np.isclose(delong_ci(y, scores)["auc"], roc_auc_score(y, scores))
result = delong_test(y, a, b)
assert np.isclose(result["auc_a"], roc_auc_score(y, a))
assert np.isclose(result["auc_b"], roc_auc_score(y, b))
print("1. AUC matches scikit-learn (ties included)")

# Check 2: DeLong standard errors agree with a large bootstrap
y, (a, b) = make_scores(600, [0.8, 0.5])
boot_auc = bootstrap_ci(roc_auc_score, y, a, n_boot=4000)
boot_se = (boot_auc["high"] - boot_auc["low"]) / (2 * 1.96)
delong_se = delong_ci(y, a)["se"]
assert abs(boot_se / delong_se - 1) < 0.10, (boot_se, delong_se)
diff = lambda yy, aa, bb: roc_auc_score(yy, aa) - roc_auc_score(yy, bb)
boot_diff = bootstrap_ci(diff, y, a, b, n_boot=4000)
boot_diff_se = (boot_diff["high"] - boot_diff["low"]) / (2 * 1.96)
test_se = delong_test(y, a, b)["se"]
assert abs(boot_diff_se / test_se - 1) < 0.10, (boot_diff_se, test_se)
print(f"2. Standard errors agree with bootstrap: single {delong_se:.4f} vs {boot_se:.4f}, "
      f"difference {test_se:.4f} vs {boot_diff_se:.4f}")

# Check 3: with equally good models, p < 0.05 about 5% of the time
p_values = [delong_test(*(lambda yy, cc: (yy, cc[0], cc[1]))(*make_scores(300, 0.7)))["p"]
            for _ in range(1000)]
false_alarms = np.mean(np.array(p_values) < 0.05)
assert 0.03 <= false_alarms <= 0.075, false_alarms
assert stats.kstest(p_values, "uniform").pvalue > 0.01
print(f"3. Equal models: p < 0.05 in {false_alarms:.1%} of 1,000 runs (expected about 5%)")

# Check 4: a real difference is detected
y, (a, b) = make_scores(800, [1.2, 0.3])
assert delong_test(y, a, b)["p"] < 0.001
print("4. A clear AUC gap is detected")

# Check 5: identical models give no difference and no error
y, (a, _) = make_scores(200, 0.5)
same = delong_test(y, a, a)
assert same["diff"] == 0 and same["p"] == 1.0
print("5. Identical models: difference 0, p = 1")

# Check 6: grouped bootstrap keeps firms together, so clustered data gets wider intervals
firms = np.repeat(np.arange(150), 3)  # each firm in all three crashes
firm_effect = np.repeat(rng.normal(size=150), 3)
values = firm_effect + 0.3 * rng.normal(size=450)
by_row = bootstrap_ci(np.mean, values)
by_firm = bootstrap_ci(np.mean, values, groups=firms)
assert (by_firm["high"] - by_firm["low"]) > 1.3 * (by_row["high"] - by_row["low"])
assert bootstrap_ci(np.mean, values, groups=firms) == by_firm  # same seed, same result
print(f"6. Firm bootstrap is wider for repeated firms: {by_firm['high'] - by_firm['low']:.3f} "
      f"vs {by_row['high'] - by_row['low']:.3f}, and repeatable")

# Check 7: draws with one class are skipped, not fatal
y_small = np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 1])
result = bootstrap_ci(roc_auc_score, y_small, np.linspace(0, 1, 10), n_boot=500)
assert result["skipped"] > 0 and result["n_boot"] + result["skipped"] == 500
print(f"7. One-class resamples skipped: {result['skipped']} of 500")

# Check 8: Winsorizer clips to training quantiles only and keeps missing values
from helpers import Winsorizer
train = np.c_[np.arange(100.0), np.r_[np.arange(99.0), np.nan]]
w = Winsorizer().fit(train)
test = np.array([[-50.0, np.nan], [500.0, 1e9]])
out = w.transform(test)
assert out[0, 0] == w.low_[0] and out[1, 0] == w.high_[0] and np.isnan(out[0, 1])
assert out[1, 1] == w.high_[1] < 99
print(f"8. Winsorizer clips test rows to training limits {w.low_[0]:.2f} to {w.high_[0]:.2f}, keeps NaN")

print("\nAll helper checks passed")
