"""Детерминированный генератор демо-данных PredictorLab. Сид фиксирован — данные воспроизводимы."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def make_flat(seed: int = 42, n: int = 24000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    customer_id = [f"C{100000 + i}" for i in range(1, n + 1)]
    segment = rng.choice(["SMB", "Mid", "Enterprise"], size=n, p=[0.55, 0.33, 0.12])
    region = rng.choice(["Москва", "СПб", "Екатеринбург", "Другой"], size=n, p=[0.4, 0.25, 0.15, 0.2])
    age_years = rng.integers(1, 12, size=n)
    discount_pct = np.clip(rng.normal(6, 4, size=n), 0, 25).round(1)
    manager_rating = rng.integers(1, 6, size=n)
    complaints_90d = rng.poisson(0.4, size=n)
    satisfaction = np.clip(rng.normal(3.6, 0.9, size=n), 1, 5).round(1)
    orders_count_90d = rng.poisson(np.where(segment == "Enterprise", 4.2, np.where(segment == "Mid", 2.4, 1.1)), size=n)
    orders_sum_90d = (orders_count_90d * rng.lognormal(5.4, 0.5, size=n)).round(0)
    orders_sum_30d = (orders_count_90d * rng.uniform(0.1, 0.5, size=n) * rng.lognormal(5.4, 0.5, size=n)).round(0)
    days_since_last_order = np.clip(rng.gamma(2.0, 22, size=n), 0, 240).astype(int)
    tickets_90d = rng.poisson(0.7, size=n)

    logit = (
        -2.05
        + 0.048 * (days_since_last_order - 30)
        - 0.09 * discount_pct
        + 0.55 * (segment == "SMB")
        - 0.28 * manager_rating
        + 0.33 * complaints_90d
        - 0.45 * satisfaction
        - 0.02 * orders_count_90d
        + rng.normal(0, 0.55, size=n)
    )
    p = sigmoid(logit)
    churn = (rng.random(n) < p).astype(int)

    months = pd.date_range("2024-01-15", "2025-06-15", freq="ME")
    event_date = rng.choice(months, size=n)
    support_email = [f"client{i}@company{i % 977}.ru" for i in range(1, n + 1)]

    df = pd.DataFrame({
        "customer_id": customer_id,
        "segment": segment,
        "region": region,
        "age_years": age_years,
        "discount_pct": discount_pct,
        "manager_rating": manager_rating,
        "complaints_90d": complaints_90d,
        "satisfaction": satisfaction,
        "orders_count_90d": orders_count_90d,
        "orders_sum_90d": orders_sum_90d,
        "orders_sum_30d": orders_sum_30d,
        "days_since_last_order": days_since_last_order,
        "tickets_90d": tickets_90d,
        "event_date": event_date,
        "support_email": support_email,
        "churn": churn,
    })
    return df


def make_leaky(flat: pd.DataFrame, seed: int = 43) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = flat.copy()
    cancel_offsets = rng.integers(2, 30, size=len(df))
    cancel_dates = pd.to_datetime(df["event_date"]) + pd.to_timedelta(cancel_offsets, unit="D")
    df["cancel_date"] = np.where(df["churn"] == 1, cancel_dates.astype(str), None)
    df["final_status"] = np.where(df["churn"] == 1, "расторжение", "активен")
    return df


def make_relational(seed: int = 44, n_customers: int = 9000) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    customer_id = [f"C{200000 + i}" for i in range(1, n_customers + 1)]
    segment = rng.choice(["SMB", "Mid", "Enterprise"], size=n_customers, p=[0.55, 0.33, 0.12])
    region = rng.choice(["Москва", "СПб", "Екатеринбург", "Другой"], size=n_customers, p=[0.4, 0.25, 0.15, 0.2])
    signup = pd.date_range("2022-01-01", "2023-06-30").to_series().sample(n_customers, replace=True, random_state=seed).reset_index(drop=True)
    discount_pct = np.clip(rng.normal(6, 4, size=n_customers), 0, 25).round(1)
    customers = pd.DataFrame({
        "customer_id": customer_id, "segment": segment, "region": region,
        "signup_date": signup.astype(str), "discount_pct": discount_pct,
    })

    orders_rows = []
    tickets_rows = []
    order_seq = 500000
    ticket_seq = 900000
    for i, cid in enumerate(customer_id):
        churniness = 0.9 if segment[i] == "SMB" else 0.6
        n_orders = rng.poisson(6 * (0.5 + churniness))
        base = pd.Timestamp(signup.iloc[i])
        for _ in range(int(n_orders)):
            order_seq += 1
            days = int(rng.exponential(60)) + int(rng.integers(0, 400))
            order_date = base + pd.Timedelta(days=min(days, 900))
            if order_date > pd.Timestamp("2025-08-31"):
                continue
            amount = float(np.round(rng.lognormal(5.4, 0.5), 0))
            orders_rows.append({"order_id": f"O{order_seq}", "customer_id": cid,
                                "order_date": str(order_date.date()), "amount": amount})
        n_tickets = int(rng.poisson(1.2))
        for _ in range(n_tickets):
            ticket_seq += 1
            days = int(rng.integers(0, 900))
            created = base + pd.Timedelta(days=days)
            if created > pd.Timestamp("2025-08-31"):
                continue
            tickets_rows.append({"ticket_id": f"T{ticket_seq}", "customer_id": cid,
                                 "created_at": str(created.date()),
                                 "priority": str(rng.choice(["low", "normal", "high"], p=[0.5, 0.4, 0.1]))})
    orders = pd.DataFrame(orders_rows)
    tickets = pd.DataFrame(tickets_rows)
    return {"customers": customers, "orders": orders, "tickets": tickets}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rows", type=int, default=24000)
    parser.add_argument("--outdir", type=str, default=str(Path(__file__).parent))
    args = parser.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    flat = make_flat(args.seed, args.rows)
    flat.to_csv(out / "b2b_flat.csv", index=False, encoding="utf-8")
    leaky = make_leaky(flat)
    leaky.to_csv(out / "b2b_leaky.csv", index=False, encoding="utf-8")
    rel = make_relational(args.seed + 2)
    for name, df in rel.items():
        df.to_csv(out / f"rel_{name}.csv", index=False, encoding="utf-8")
    print(f"flat={len(flat)} leaky={len(leaky)} customers={len(rel['customers'])} "
          f"orders={len(rel['orders'])} tickets={len(rel['tickets'])} churn_rate={flat['churn'].mean():.3f}")


if __name__ == "__main__":
    main()
