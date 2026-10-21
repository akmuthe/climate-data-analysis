"""
Climate Data Processing & Visual Analytics
==========================================
End-to-end pipeline: ingest -> clean -> validate -> reconcile -> analyse -> visualise.

Data (public, via the open "datasets" GitHub org, originally NASA GISS / NOAA):
  * Global monthly temperature anomalies from two independent sources (GISTEMP, GCAG)
  * Mauna Loa monthly atmospheric CO2 (NOAA)

Run:  python climate_pipeline.py
"""
from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"
PROC_DIR = ROOT / "data" / "processed"
FIG_DIR = ROOT / "outputs" / "figures"
for d in (RAW_DIR, PROC_DIR, FIG_DIR):
    d.mkdir(parents=True, exist_ok=True)

BASE = "https://raw.githubusercontent.com/datasets"
SOURCES = {
    "temperature": f"{BASE}/global-temp/main/data/monthly.csv",
    "co2": f"{BASE}/co2-ppm/main/data/co2-mm-mlo.csv",
}
# The CO2 file's header is mislabelled (6 names for 7 columns), so we name them ourselves.
CO2_COLUMNS = ["date", "decimal_date", "co2_monthly", "co2_deseasonalised",
               "n_days", "std_dev", "uncertainty"]
BASELINE = ("1951-01-01", "1980-12-31")  # common baseline used to reconcile sources

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("climate")
sns.set_theme(style="whitegrid", context="notebook", font="DejaVu Sans")


# --------------------------------------------------------------------------- #
# 1. Ingestion (cached so reruns work offline)
# --------------------------------------------------------------------------- #
def fetch(name: str) -> Path:
    path = RAW_DIR / f"{name}.csv"
    if not path.exists():
        log.info("Downloading %s ...", name)
        urllib.request.urlretrieve(SOURCES[name], path)
    return path


# --------------------------------------------------------------------------- #
# 2. Cleaning
# --------------------------------------------------------------------------- #
def clean_temperature(path: Path) -> pd.DataFrame:
    """Long-format temperature anomalies -> tidy frame (source, date, anomaly)."""
    df = pd.read_csv(path).rename(columns={"Source": "source", "Year": "date", "Mean": "anomaly"})
    n0 = len(df)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m", errors="coerce")
    df["anomaly"] = pd.to_numeric(df["anomaly"], errors="coerce")
    df = df.dropna(subset=["date", "anomaly"])
    n_dupes = df.duplicated(["source", "date"]).sum()
    df = df.drop_duplicates(["source", "date"]).sort_values(["source", "date"])
    log.info("Temperature: %d raw rows -> %d clean (%d dropped, %d duplicates)",
             n0, len(df), n0 - len(df), n_dupes)
    return df.reset_index(drop=True)


def clean_co2(path: Path) -> pd.DataFrame:
    """Fix the mislabelled header, convert sentinel codes to NaN, enforce a full monthly index."""
    df = pd.read_csv(path, header=0, names=CO2_COLUMNS, index_col=False)
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m", errors="coerce")
    df = df.dropna(subset=["date"]).drop_duplicates("date").set_index("date").sort_index()

    # NOAA flags missing values with negative codes (-1 days, -9.99 std, -0.99 uncertainty).
    for col in ["n_days", "std_dev", "uncertainty"]:
        df.loc[df[col] < 0, col] = np.nan
    for col in ["co2_monthly", "co2_deseasonalised"]:
        df.loc[df[col] <= 0, col] = np.nan

    full_index = pd.date_range(df.index.min(), df.index.max(), freq="MS")
    df = df.reindex(full_index).rename_axis("date")
    df["co2_was_missing"] = df["co2_monthly"].isna()
    df["co2_monthly"] = df["co2_monthly"].interpolate(limit=3)  # only fill short gaps
    log.info("CO2: %d months (%s to %s), %d gaps filled",
             len(df), df.index.min().date(), df.index.max().date(), int(df["co2_was_missing"].sum()))
    return df


# --------------------------------------------------------------------------- #
# 3. Reconciliation: do two "independent" sources agree?
# --------------------------------------------------------------------------- #
def reconcile_temperature(tidy: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    wide = tidy.pivot(index="date", columns="source", values="anomaly")
    # Sources use different baselines (GISTEMP: 1951-80, GCAG: 20th-century mean),
    # so rebase both to a common period before comparing.
    base = wide.loc[BASELINE[0]:BASELINE[1]].mean()
    rebased = wide - base
    both = rebased.dropna()
    diff = both["GISTEMP"] - both["GCAG"]
    stats_ = {
        "overlap_months": int(len(both)),
        "overlap_period": f"{both.index.min():%Y-%m} to {both.index.max():%Y-%m}",
        "pearson_r": round(float(both["GISTEMP"].corr(both["GCAG"])), 4),
        "rmse_c": round(float(np.sqrt((diff ** 2).mean())), 4),
        "max_abs_diff_c": round(float(diff.abs().max()), 4),
        "baseline_offset_c": {k: round(float(v), 3) for k, v in base.items()},
    }
    log.info("Reconciliation: r=%.4f, RMSE=%.3f C over %d months",
             stats_["pearson_r"], stats_["rmse_c"], stats_["overlap_months"])
    return rebased, stats_


# --------------------------------------------------------------------------- #
# 4. Validation / data-quality checks
# --------------------------------------------------------------------------- #
def robust_outliers(s: pd.Series, thresh: float = 5.0) -> pd.Series:
    """Flag month-to-month jumps that are > `thresh` robust z-scores (median/MAD)."""
    d = s.diff().dropna()
    mad = np.median(np.abs(d - d.median())) or 1e-9
    z = 0.6745 * (d - d.median()) / mad
    return z[np.abs(z) > thresh]


def run_quality_checks(tidy: pd.DataFrame, co2: pd.DataFrame) -> list[dict]:
    checks = []

    def add(name: str, passed: bool, detail: str, severity: str = "error") -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail, "severity": severity})

    for src, g in tidy.groupby("source"):
        expected = pd.date_range(g["date"].min(), g["date"].max(), freq="MS")
        missing = len(expected.difference(g["date"]))
        add(f"{src}: no missing months", missing == 0, f"{missing} missing")
        add(f"{src}: anomalies in plausible range (-5, 5) C",
            g["anomaly"].between(-5, 5).all(), f"range {g['anomaly'].min():.2f} to {g['anomaly'].max():.2f}")
        out = robust_outliers(g.set_index("date")["anomaly"])
        add(f"{src}: no extreme month-to-month jumps", out.empty,
            f"{len(out)} flagged: {[d.strftime('%Y-%m') for d in out.index]}", severity="warn")

    add("CO2: monotonic, unique monthly index", co2.index.is_monotonic_increasing and co2.index.is_unique, "")
    add("CO2: no remaining missing values", co2["co2_monthly"].notna().all(),
        f"{int(co2['co2_monthly'].isna().sum())} NaN")
    add("CO2: values in plausible range (280-500 ppm)", co2["co2_monthly"].between(280, 500).all(),
        f"range {co2['co2_monthly'].min():.1f} to {co2['co2_monthly'].max():.1f}")
    out = robust_outliers(co2["co2_deseasonalised"])
    add("CO2: deseasonalised series has no extreme jumps", out.empty, f"{len(out)} flagged", severity="warn")
    for c in checks:
        status = "PASS" if c["passed"] else ("WARN" if c["severity"] == "warn" else "FAIL")
        c["status"] = status
        log.info("[%s] %s %s", status, c["check"], c["detail"])
    return checks


# --------------------------------------------------------------------------- #
# 5. Analysis
# --------------------------------------------------------------------------- #
def decimal_year(idx: pd.DatetimeIndex) -> np.ndarray:
    return idx.year + (idx.month - 0.5) / 12


def trend_per_decade(s: pd.Series, start: str, unit_scale: float = 10.0) -> dict:
    s = s.loc[start:].dropna()
    r = stats.linregress(decimal_year(s.index), s.values)
    return {"from": start, "slope_per_decade": round(r.slope * unit_scale, 3),
            "r2": round(r.rvalue ** 2, 3)}


def annual_mean(s: pd.Series) -> pd.Series:
    """Annual means using only complete years (12 observations)."""
    g = s.dropna().groupby(s.dropna().index.year)
    return g.mean()[g.count() == 12]


def analyse(rebased: pd.DataFrame, co2: pd.DataFrame) -> dict:
    res: dict = {}
    gcag, gis = rebased["GCAG"].dropna(), rebased["GISTEMP"].dropna()

    res["temperature_trends_c_per_decade"] = {
        "GCAG_since_1880": trend_per_decade(gcag, "1880"),
        "GCAG_since_1970": trend_per_decade(gcag, "1970"),
        "GISTEMP_since_1970": trend_per_decade(gis, "1970"),
    }
    res["co2_trend_ppm_per_decade"] = {
        "since_1958": trend_per_decade(co2["co2_deseasonalised"], "1958"),
        "since_2000": trend_per_decade(co2["co2_deseasonalised"], "2000"),
    }

    # Seasonal cycle of CO2 (monthly minus deseasonalised, averaged by calendar month)
    seasonal = (co2["co2_monthly"] - co2["co2_deseasonalised"]).groupby(co2.index.month).mean()
    res["co2_seasonal_amplitude_ppm"] = round(float(seasonal.max() - seasonal.min()), 2)
    res["co2_seasonal_peak_month"] = int(seasonal.idxmax())

    # Decadal means
    dec = gcag.groupby((gcag.index.year // 10) * 10).mean().round(3)
    res["decadal_mean_anomaly_c"] = {f"{k}s": v for k, v in dec.items()}

    # CO2 vs temperature on annual data. Both trend upward, so a raw correlation is inflated;
    # also report the correlation of year-on-year *changes* as a more honest check.
    ann = pd.concat({"temp": annual_mean(gcag), "co2": annual_mean(co2["co2_monthly"])}, axis=1).dropna()
    r_levels = stats.pearsonr(ann["co2"], ann["temp"])
    r_diff = stats.pearsonr(ann["co2"].diff().dropna(), ann["temp"].diff().dropna())
    res["co2_vs_temp_annual"] = {
        "years": f"{ann.index.min()}-{ann.index.max()}",
        "pearson_r_levels": round(float(r_levels.statistic), 3),
        "pearson_r_year_on_year_changes": round(float(r_diff.statistic), 3),
        "warming_c_per_100ppm": round(float(stats.linregress(ann["co2"], ann["temp"]).slope * 100), 2),
    }
    res["_annual"] = ann
    res["_seasonal"] = seasonal
    return res


# --------------------------------------------------------------------------- #
# 6. Visualisation
# --------------------------------------------------------------------------- #
def save(fig: plt.Figure, name: str) -> None:
    fig.tight_layout()
    fig.savefig(FIG_DIR / name, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_temperature_trend(rebased: pd.DataFrame) -> None:
    s = rebased["GCAG"].dropna()
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(s.index, s, color="lightgrey", lw=0.8, label="Monthly")
    ax.plot(s.index, s.rolling(12, center=True).mean(), color="tab:orange", lw=1.5, label="12-month mean")
    ax.plot(s.index, s.rolling(120, center=True).mean(), color="firebrick", lw=2.5, label="10-year mean")
    ax.axhline(0, color="black", lw=0.7)
    ax.set(title="Global temperature anomaly (baseline 1951-1980)", ylabel="Anomaly (°C)", xlabel="")
    ax.legend(loc="upper left")
    save(fig, "01_temperature_trend.png")


def plot_warming_stripes(rebased: pd.DataFrame) -> None:
    a = annual_mean(rebased["GCAG"])
    fig, ax = plt.subplots(figsize=(12, 2.6))
    lim = float(np.abs(a).max())
    ax.imshow(a.values[None, :], aspect="auto", cmap="RdBu_r", vmin=-lim, vmax=lim,
              extent=[a.index.min(), a.index.max() + 1, 0, 1])
    ax.set_yticks([])
    ax.set_title(f"Warming stripes, {a.index.min()}-{a.index.max()}")
    ax.grid(False)
    save(fig, "02_warming_stripes.png")


def plot_month_year_heatmap(rebased: pd.DataFrame) -> None:
    s = rebased["GCAG"].dropna().loc["1950":]
    grid = s.groupby([s.index.month, s.index.year]).mean().unstack()
    fig, ax = plt.subplots(figsize=(13, 5))
    sns.heatmap(grid, cmap="RdBu_r", center=0, ax=ax, cbar_kws={"label": "Anomaly (°C)"},
                xticklabels=10, yticklabels=["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][: grid.shape[0]])
    ax.set(title="Temperature anomaly by month and year", xlabel="Year", ylabel="")
    ax.grid(False)
    plt.setp(ax.get_yticklabels(), rotation=0)
    save(fig, "03_month_year_heatmap.png")


def plot_co2(co2: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), gridspec_kw={"width_ratios": [2, 1]})
    axes[0].plot(co2.index, co2["co2_monthly"], color="tab:blue", lw=0.8, label="Monthly")
    axes[0].plot(co2.index, co2["co2_deseasonalised"], color="black", lw=1.5, label="Deseasonalised")
    axes[0].set(title="Atmospheric CO₂ at Mauna Loa (Keeling curve)", ylabel="ppm")
    axes[0].legend()
    seasonal = (co2["co2_monthly"] - co2["co2_deseasonalised"]).groupby(co2.index.month).mean()
    axes[1].bar(seasonal.index, seasonal.values, color="tab:green")
    axes[1].set(title="Average seasonal cycle", xlabel="Month", ylabel="ppm vs trend", xticks=range(1, 13))
    save(fig, "04_co2_keeling_and_seasonality.png")


def plot_co2_vs_temp(ann: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    sns.regplot(data=ann, x="co2", y="temp", ax=ax, scatter_kws={"s": 25}, line_kws={"color": "firebrick"})
    ax.set(title="Annual CO₂ vs temperature anomaly", xlabel="CO₂ (ppm)", ylabel="Anomaly (°C)")
    save(fig, "05_co2_vs_temperature.png")


def plot_reconciliation(rebased: pd.DataFrame) -> None:
    both = rebased.dropna()
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    axes[0].plot(both.index, both["GCAG"].rolling(12).mean(), label="GCAG (12-mo mean)")
    axes[0].plot(both.index, both["GISTEMP"].rolling(12).mean(), label="GISTEMP (12-mo mean)", ls="--")
    axes[0].set(title="Source reconciliation (common 1951-1980 baseline)", ylabel="Anomaly (°C)")
    axes[0].legend()
    axes[1].plot(both.index, both["GISTEMP"] - both["GCAG"], color="grey", lw=0.8)
    axes[1].axhline(0, color="black", lw=0.7)
    axes[1].set(ylabel="GISTEMP - GCAG (°C)")
    save(fig, "06_source_reconciliation.png")


# --------------------------------------------------------------------------- #
# 7. Reporting
# --------------------------------------------------------------------------- #
def write_report(checks: list[dict], recon: dict, results: dict) -> None:
    public = {k: v for k, v in results.items() if not k.startswith("_")}
    (ROOT / "outputs" / "results.json").write_text(
        json.dumps({"reconciliation": recon, **public}, indent=2))

    lines = ["# Data quality & results summary\n", "## Quality checks\n",
             "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {c['check']} | {c['status']} | {c['detail']} |" for c in checks]
    lines += ["\n## Source reconciliation (GISTEMP vs GCAG)\n", "```", json.dumps(recon, indent=2), "```",
              "\n## Key results\n", "```", json.dumps(public, indent=2), "```"]
    (ROOT / "outputs" / "report.md").write_text("\n".join(lines))


def main() -> None:
    tidy = clean_temperature(fetch("temperature"))
    co2 = clean_co2(fetch("co2"))
    rebased, recon = reconcile_temperature(tidy)
    checks = run_quality_checks(tidy, co2)
    results = analyse(rebased, co2)

    rebased.to_csv(PROC_DIR / "temperature_rebased_monthly.csv")
    co2.to_csv(PROC_DIR / "co2_monthly_clean.csv")
    results["_annual"].to_csv(PROC_DIR / "annual_co2_temperature.csv")

    plot_temperature_trend(rebased)
    plot_warming_stripes(rebased)
    plot_month_year_heatmap(rebased)
    plot_co2(co2)
    plot_co2_vs_temp(results["_annual"])
    plot_reconciliation(rebased)
    write_report(checks, recon, results)

    log.info("Done. Figures in %s", FIG_DIR)
    print(json.dumps({k: v for k, v in results.items() if not k.startswith("_")}, indent=2))


if __name__ == "__main__":
    main()
