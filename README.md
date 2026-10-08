# MEAnalysis

Order, customer and product analysis for a Mamaearth-style D2C dataset, in three parts that share the same
raw CSVs in `data/`:

1. **SQL** (MySQL): schema, seed data and report queries.
2. **Python/pandas**: cleaning, EDA and two charts, run directly on the CSVs (it does not read the database).
3. **GenAI narrator**: turns the verified numbers into a Situation-Complication-Resolution narrative.

Follow the steps below in order to reproduce every number.

## Setup

Python 3.10+ and MySQL 8+ (tested with the server on `localhost`).

```
pip install pandas matplotlib google-genai
```

## 1. SQL: schema, seed data, reports

From the repo root, using your own MySQL user (you will be prompted for the password):

```
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS meanalysis;"
mysql -u root -p meanalysis < sql/schema.sql
mysql -u root -p meanalysis < sql/seed_data.sql
mysql -u root -p -t meanalysis < sql/reports.sql
```

- `schema.sql` creates `customers`, `products` and `orders`. Run it once on a fresh database.
- `seed_data.sql` loads `data/*.csv` as INSERT statements. It clears the three tables first, so it is
  re-runnable. Expected counts: 45 customers, 16 products, 180 orders.
- `reports.sql` holds reports (a)-(i) with the actual output pasted above each query. Its last section runs
  `ALTER TABLE customers ADD COLUMN loyalty_tier`, which fails if the column already exists (MySQL has no
  `ADD COLUMN IF NOT EXISTS`). To re-run the whole file, recreate the database first with
  `DROP DATABASE meanalysis;` and repeat the steps above.

## 2. Python: cleaning, EDA, charts

```
python analysis/clean_and_eda.py
python analysis/visualize.py
```

- `clean_and_eda.py` prints every intermediate result: raw shape (180, 9), payment-method standardizing, the 5
  duplicates dropped, imputation, the reconciliation to Part 1 (cleaned total 97,358.30 vs raw 99,860.20),
  IQR outliers, the COD hypothesis, segmentation, correlations and the monthly revenue series.
- Its final step, `export_findings()`, writes `narrator/findings.json` from the computed values (nothing in
  that file is typed by hand). Run this script before the narrator.
- `visualize.py` rebuilds the cleaned data from the raw CSVs and saves `visualizations/return_rate_by_payment.png`
  and `visualizations/monthly_revenue_trend.png`. It can be run on its own, and re-running it gives
  identical files.

## 3. Narrator: SCR narrative

```
python narrator/generate_narrative.py
```

The script reads `narrator/findings.json`, produces a Situation / Complication / Resolution narrative, and
then checks that all five required figures (97,358.30; 44.4; 54.5; 2,501.90; March with 20,318.90) appear in it.

**With no API key (offline path).** Run the command above with nothing configured. The script falls back to a
deterministic template built from `findings.json`: no network, no key. Use `--offline` to force this path
even when a key is set.

**With a Gemini API key (online path).** Get a free key from Google AI Studio (https://aistudio.google.com/apikey;
the free usage tier is enough) and set it as an environment variable:

```
# macOS / Linux / Git Bash
export GEMINI_API_KEY="your-key"

# Windows PowerShell
$env:GEMINI_API_KEY = "your-key"
```

Then run `python narrator/generate_narrative.py`. It calls Gemini with `temperature=0.0`, an explicit
`max_output_tokens`, and a 30-second timeout. If the call fails for any reason (bad key, quota, network), it
falls back to the offline template and prints the reason. The model defaults to `gemini-3.8-flash`; override it
with `GEMINI_MODEL`.

To save a real Gemini run as the graded sample, run
`python narrator/generate_narrative.py --save-sample`. It writes `narrator/sample_output.txt` only when the
text really came from Gemini, and the numeric checker runs on that same text.

## Layout

```
sql/            schema.sql, seed_data.sql, reports.sql
data/           customers.csv, products.csv, orders.csv (raw)
analysis/       clean_and_eda.py, visualize.py
visualizations/ return_rate_by_payment.png, monthly_revenue_trend.png
narrator/       findings.json, generate_narrative.py, sample_output.txt
```
