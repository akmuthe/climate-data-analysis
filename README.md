# Climate Data Processing & Visual Analytics

A reproducible Python pipeline that cleans, validates, reconciles and analyses long-run
climate data, then turns it into publication-style visuals.

**Stack:** Python, Pandas, NumPy, SciPy, Matplotlib, Seaborn

## Data (public, auto-downloaded and cached)
| Dataset | Content | Span |
|---|---|---|
| Global temperature anomalies, **GISTEMP** (NASA) | monthly | 1880-2025 |
| Global temperature anomalies, **GCAG** (NOAA) | monthly | 1850-2026 |
| Mauna Loa atmospheric CO2 (NOAA) | monthly | 1958-2026 |

## Run
```bash
pip install -r requirements.txt
python climate_pipeline.py
```
Outputs: `outputs/figures/*.png`, `outputs/report.md`, `outputs/results.json`, `data/processed/*.csv`

## Pipeline
1. **Ingest** - cached download, so reruns work offline.
2. **Clean** - date parsing, type coercion, de-duplication; fixed a mislabelled CO2 header
   (6 names for 7 columns); converted NOAA sentinel codes (-1, -9.99, -0.99) to NaN;
   enforced a complete monthly index and only interpolated short gaps (<=3 months).
3. **Reconcile** - GISTEMP and GCAG use different baselines, so both are rebased to 1951-1980
   before comparison (r = 0.987, RMSE = 0.067 C over 1,752 overlapping months).
4. **Validate** - automated checks (missing months, plausible ranges, monotonic index,
   robust MAD-based outlier detection). The only warning is 2 jumps in 1863/1869,
   where early-record coverage is sparse.
5. **Analyse** - warming trends, decadal means, CO2 seasonal cycle, CO2-temperature relationship.
6. **Visualise** - 6 figures (trend with rolling means, warming stripes, month x year heatmap,
   Keeling curve + seasonality, CO2 vs temperature, source reconciliation).

## Headline results
- Warming rate: **~0.09 C/decade since 1880** vs **~0.20 C/decade since 1970**
- Decadal mean anomaly rose from -0.04 C (1960s) to **+1.05 C (2020s)**
- CO2 rise accelerated: **~17 ppm/decade since 1958** vs **~23 ppm/decade since 2000**
- CO2 seasonal swing: **~6.3 ppm**, peaking in May

## Interview talking points
- **Why rebase before comparing sources?** Different baselines shift the whole series; comparing
  raw values would show a false offset.
- **Why report two correlations?** CO2 and temperature both trend upward, so the level
  correlation (r = 0.97) is inflated. Year-on-year changes give a more honest r = 0.29.
- **Limitations:** linear-regression standard errors ignore autocorrelation in monthly data (too
  optimistic); a trend line is descriptive, not causal; early-record data is sparse.
- **Possible extensions:** seasonal decomposition (STL), changepoint detection, Prophet/SARIMA
  forecast of CO2, Tableau dashboard of the processed CSVs.
