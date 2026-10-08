"""Part 2: pandas wrangling and EDA over the raw CSVs in data/ (independent of the SQL database).

Run `python analysis/clean_and_eda.py` for the full printed walkthrough. visualize.py calls run(quiet=True)
to rebuild the same frames from the raw CSVs without printing.
"""
import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NATURAL_KEY = ["customer_id", "product_id", "order_date", "quantity",
               "discount_pct", "payment_method", "rating", "returned"]


def order_value(df):
    return df["quantity"] * df["price"] * (1 - df["discount_pct"] / 100)


def band(r):
    """Taught correlation-strength bands on |r|."""
    r = abs(r)
    if r < 0.2:
        return "negligible"
    if r < 0.4:
        return "weak"
    if r < 0.7:
        return "moderate"
    return "strong"


def run(quiet=False):
    def out(*args, **kwargs):
        if not quiet:
            print(*args, **kwargs)

    def section(title):
        out(f"\n{'=' * 8} {title} {'=' * 8}")

    # ------------------------------------------------------------ Task 1: load and inspect
    section("Task 1: Load and inspect")
    orders = pd.read_csv(DATA_DIR / "orders.csv")
    customers = pd.read_csv(DATA_DIR / "customers.csv")
    products = pd.read_csv(DATA_DIR / "products.csv")

    out("orders.shape (before any cleaning):", orders.shape)
    out("customers.shape:", customers.shape)
    out("products.shape:", products.shape)
    for name, df in [("orders", orders), ("customers", customers), ("products", products)]:
        out(f"\n{name}.head():")
        out(df.head().to_string())
        out(f"\n{name}.dtypes:")
        out(df.dtypes.to_string())
        out(f"\n{name} missing values per column:")
        out(df.isna().sum().to_string())

    # Raw total kept for the Task 5 reconciliation (NULL discount = 0%, same rule as Part 1 Report a).
    raw_total = order_value(
        orders.assign(discount_pct=orders["discount_pct"].fillna(0))
        .merge(products, on="product_id")).sum()

    # ------------------------------------------------ Task 2: standardize payment_method
    section("Task 2: Standardize payment_method casing")
    out("Distinct raw values:", orders["payment_method"].unique())
    out("Number of distinct raw values:", orders["payment_method"].nunique())
    orders["payment_method"] = orders["payment_method"].str.strip().str.upper()
    out("\nAfter .str.strip().str.upper():")
    out(orders["payment_method"].value_counts().to_string())

    # ------------------------------------------------------ Task 3: remove duplicates
    section("Task 3: Remove duplicate orders")
    dup_mask = orders.duplicated(subset=NATURAL_KEY, keep="first")
    dropped = orders[dup_mask]
    out(f"Rows flagged as duplicates: {dup_mask.sum()}")
    out("Dropped order_id values:", dropped["order_id"].tolist())
    orders_clean = orders[~dup_mask].copy()
    out("orders_clean.shape:", orders_clean.shape)

    # ------------------------------------------------------ Task 4: impute missing values
    section("Task 4: Impute missing values")
    n_disc = orders_clean["discount_pct"].isna().sum()
    n_rate = orders_clean["rating"].isna().sum()
    median_rating = orders_clean["rating"].median()
    out(f"discount_pct NaN rows (deduplicated frame): {n_disc} -> fill with 0")
    out(f"rating NaN rows (deduplicated frame): {n_rate}")
    out(f"Median of non-null ratings (before imputing): {median_rating}")
    orders_clean["discount_pct"] = orders_clean["discount_pct"].fillna(0)
    orders_clean["rating"] = orders_clean["rating"].fillna(median_rating)
    out("\nNulls after imputing:")
    out(orders_clean[["discount_pct", "rating"]].isnull().sum().to_dict())

    # --------------------------------------------- Task 5: merge and reconcile with Part 1
    section("Task 5: Merge and reconcile against Part 1")
    merged = (orders_clean
              .merge(products, on="product_id", how="left")
              .merge(customers, on="customer_id", how="left"))
    merged["order_value"] = order_value(merged)
    clean_total = merged["order_value"].sum()
    out("merged.shape:", merged.shape)
    out(f"Total order_value across {len(merged)} cleaned rows: {clean_total:,.2f}")

    dropped_value = order_value(
        dropped.assign(discount_pct=dropped["discount_pct"].fillna(0))
        .merge(products, on="product_id")).sum()
    delta = raw_total - clean_total
    out(f"\nPart 1 Report (a) raw total (180 rows): {raw_total:,.2f}")
    out(f"Cleaned total (175 rows):               {clean_total:,.2f}")
    out(f"Delta (raw - cleaned):                  {delta:,.2f}")
    out(f"Independent sum of the {len(dropped)} dropped rows' order_value: {dropped_value:,.2f}")
    out(f"Delta equals dropped-row value: {round(delta, 2) == round(dropped_value, 2)}")
    out("\nReconciliation note:")
    out(f"The cleaned total of INR {clean_total:,.2f} is INR {delta:,.2f} lower than Part 1 Report (a)'s raw "
        f"total of INR {raw_total:,.2f}. That whole gap comes from the {len(dropped)} duplicate orders removed "
        f"in Task 3 ({', '.join(dropped['order_id'])}): their combined order_value, summed independently, is "
        f"INR {dropped_value:,.2f}, which matches the delta exactly. It is not caused by the discount or "
        f"rating imputation in Task 4: filling a NULL discount_pct with 0 is the same 0% treatment Part 1 "
        f"already applied through COALESCE, and rating is not part of order_value, so neither imputation "
        f"changes any order_value total.")

    # ------------------------------------------------------------ Task 6: IQR outliers
    section("Task 6: IQR outlier detection on quantity")
    q1 = merged["quantity"].quantile(0.25)
    q3 = merged["quantity"].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    out(f"Q1 = {q1}, Q3 = {q3}, IQR = {iqr}, lower = {lower}, upper = {upper}")
    merged["is_outlier"] = (merged["quantity"] < lower) | (merged["quantity"] > upper)
    out(f"Rows outside [{lower}, {upper}]: {merged['is_outlier'].sum()}")
    out(merged.loc[merged["is_outlier"], ["order_id", "order_date", "quantity", "order_value"]].to_string(index=False))
    out("Outliers are flagged in is_outlier, not dropped.")

    # ------------------------------------------- Task 7: COD return-rate hypothesis
    section("Task 7: Does COD have a higher return rate?")
    out("Hypothesis: Cash-on-delivery (COD) orders have a higher return rate than prepaid (CARD/UPI) orders.")
    by_pay = merged.groupby("payment_method")["returned"].agg(["count", "mean"])
    by_pay["return_rate_pct"] = (by_pay["mean"] * 100).round(1)
    out(by_pay.to_string())
    prepaid_max = by_pay.drop("COD")["mean"].max()
    verdict = "Confirmed" if by_pay.loc["COD", "mean"] > prepaid_max else "Busted"
    out(f"Hypothesis: {verdict} (COD {by_pay.loc['COD', 'return_rate_pct']}% vs best prepaid "
        f"{round(prepaid_max * 100, 1)}%)")

    # ------------------------------------------------------ Task 8: segmentation
    section("Task 8: Multi-level segmentation (payment_method x city_tier)")
    seg = merged.groupby(["payment_method", "city_tier"])["returned"].agg(orders="count", return_rate="mean")
    seg["return_rate_pct"] = (seg["return_rate"] * 100).round(1)
    out(seg[["orders", "return_rate_pct"]].to_string())
    top = seg["return_rate"].idxmax()
    out(f"\nHighest-risk segment: {top[0]} + Tier-{top[1]} cities at {seg.loc[top, 'return_rate_pct']}% "
        f"({int(seg.loc[top, 'orders'])} orders)")
    cod = seg.loc["COD"]
    out("COD risk is not uniform across tiers: "
        + " vs ".join(f"{int(r.orders)} Tier-{t} COD orders at {r.return_rate_pct}%" for t, r in cod.iterrows()))

    # ----------------------------------------------------- Task 9: correlation
    section("Task 9: Correlation analysis")
    cols = ["rating", "returned", "discount_pct", "quantity"]
    corr = merged[cols].corr()
    out(corr.round(3).to_string())
    out("\nPairwise strength (bands on |r|: <0.2 negligible, 0.2-0.39 weak, 0.4-0.69 moderate, >=0.7 strong):")
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            out(f"  {a} vs {b}: r = {corr.loc[a, b]:+.3f} -> {band(corr.loc[a, b])}")
    r_dr = corr.loc["discount_pct", "returned"]
    out(f"\nHypothesis: 'higher discounts reduce returns' -> discount_pct vs returned r = {r_dr:+.3f} "
        f"({band(r_dr)}): {'Busted' if band(r_dr) == 'negligible' else 'Not busted'}")

    # ------------------------------------------ Task 10: outlier-corrected time series
    section("Task 10: Outlier-corrected monthly revenue")
    merged["order_date"] = pd.to_datetime(merged["order_date"])
    merged["year_month"] = merged["order_date"].dt.to_period("M").astype(str)
    monthly_all = merged.groupby("year_month")["order_value"].sum().round(2)
    monthly_clean = merged[~merged["is_outlier"]].groupby("year_month")["order_value"].sum().round(2)
    out("(1) Monthly revenue INCLUDING the outlier orders:")
    out(monthly_all.to_string())
    out("\n(2) Monthly revenue EXCLUDING the outlier orders (outlier-corrected):")
    out(monthly_clean.to_string())
    outliers = merged[merged["is_outlier"]]
    peak_all, peak_clean = monthly_all.idxmax(), monthly_clean.idxmax()
    where = " and ".join(f"{r.order_id} on {r.order_date.date()}" for r in outliers.itertuples())
    out(f"\nHighest month with outliers: {peak_all}. Highest month once outliers are excluded: {peak_clean}.")
    out(f"{peak_all}'s apparent lead is an artifact of the two bulk orders landing in that month ({where}); "
        f"{peak_clean} is the genuine peak month once they are excluded. This is why outliers are flagged "
        f"in Task 6 before the time series is built in Task 10.")

    return {"orders_clean": orders_clean, "merged": merged,
            "monthly_all": monthly_all, "monthly_clean": monthly_clean, "by_pay": by_pay,
            "seg": seg, "raw_total": raw_total, "clean_total": clean_total, "dropped_value": dropped_value}


def export_findings(result):
    """Write narrator/findings.json from the computed results, so it cannot drift from Part 2."""
    seg, monthly_all, monthly_clean = result["seg"], result["monthly_all"], result["monthly_clean"]
    risk_pay, risk_tier = seg["return_rate"].idxmax()
    peak, inflated = monthly_clean.idxmax(), monthly_all.idxmax()
    findings = {
        "cleaned_total_revenue_inr": round(float(result["clean_total"]), 2),
        "raw_total_revenue_inr": round(float(result["raw_total"]), 2),
        "duplicate_reconciliation_delta_inr": round(float(result["raw_total"] - result["clean_total"]), 2),
        "return_rate_by_payment": {m: round(float(r) * 100, 1) for m, r in result["by_pay"]["mean"].items()},
        "highest_risk_segment": {
            "payment_method": risk_pay,
            "city_tier": int(risk_tier),
            "return_rate_pct": round(float(seg.loc[(risk_pay, risk_tier), "return_rate"]) * 100, 1),
        },
        "true_peak_month": {"month": peak, "revenue_inr": round(float(monthly_clean[peak]), 2)},
        "outlier_inflated_month": {
            "month": inflated,
            "apparent_revenue_inr": round(float(monthly_all[inflated]), 2),
            "corrected_revenue_inr": round(float(monthly_clean[inflated]), 2),
        },
    }
    path = DATA_DIR.parent / "narrator" / "findings.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(findings, indent=2) + "\n")
    print(f"\nWrote {path.relative_to(DATA_DIR.parent)}")


if __name__ == "__main__":
    export_findings(run())
