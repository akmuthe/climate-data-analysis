# Data quality & results summary

## Quality checks

| Check | Result | Detail |
|---|---|---|
| GCAG: no missing months | PASS | 0 missing |
| GCAG: anomalies in plausible range (-5, 5) C | PASS | range -1.04 to 1.35 |
| GCAG: no extreme month-to-month jumps | WARN | 2 flagged: ['1863-01', '1869-03'] |
| GISTEMP: no missing months | PASS | 0 missing |
| GISTEMP: anomalies in plausible range (-5, 5) C | PASS | range -0.82 to 1.48 |
| GISTEMP: no extreme month-to-month jumps | PASS | 0 flagged: [] |
| CO2: monotonic, unique monthly index | PASS |  |
| CO2: no remaining missing values | PASS | 0 NaN |
| CO2: values in plausible range (280-500 ppm) | PASS | range 312.4 to 432.3 |
| CO2: deseasonalised series has no extreme jumps | PASS | 0 flagged |

## Source reconciliation (GISTEMP vs GCAG)

```
{
  "overlap_months": 1752,
  "overlap_period": "1880-01 to 2025-12",
  "pearson_r": 0.9873,
  "rmse_c": 0.0674,
  "max_abs_diff_c": 0.314,
  "baseline_offset_c": {
    "GCAG": -0.075,
    "GISTEMP": -0.0
  }
}
```

## Key results

```
{
  "temperature_trends_c_per_decade": {
    "GCAG_since_1880": {
      "from": "1880",
      "slope_per_decade": 0.087,
      "r2": 0.75
    },
    "GCAG_since_1970": {
      "from": "1970",
      "slope_per_decade": 0.205,
      "r2": 0.846
    },
    "GISTEMP_since_1970": {
      "from": "1970",
      "slope_per_decade": 0.202,
      "r2": 0.824
    }
  },
  "co2_trend_ppm_per_decade": {
    "since_1958": {
      "from": "1958",
      "slope_per_decade": 16.7,
      "r2": 0.979
    },
    "since_2000": {
      "from": "2000",
      "slope_per_decade": 22.949,
      "r2": 0.997
    }
  },
  "co2_seasonal_amplitude_ppm": 6.34,
  "co2_seasonal_peak_month": 5,
  "decadal_mean_anomaly_c": {
    "1850s": -0.249,
    "1860s": -0.342,
    "1870s": -0.208,
    "1880s": -0.281,
    "1890s": -0.342,
    "1900s": -0.359,
    "1910s": -0.342,
    "1920s": -0.198,
    "1930s": -0.063,
    "1940s": 0.055,
    "1950s": -0.015,
    "1960s": -0.042,
    "1970s": 0.014,
    "1980s": 0.232,
    "1990s": 0.39,
    "2000s": 0.59,
    "2010s": 0.804,
    "2020s": 1.051
  },
  "co2_vs_temp_annual": {
    "years": "1959-2025",
    "pearson_r_levels": 0.966,
    "pearson_r_year_on_year_changes": 0.288,
    "warming_c_per_100ppm": 1.09
  }
}
```