"""
Générateur de dataset SEPA frauduleux synthétique.
Reproduit les patterns réels de fraude aux virements instantanés.
Inspiré du dataset Kaggle Credit Card Fraud + spécificités SEPA.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
import os

np.random.seed(42)
random.seed(42)

N_LEGIT = 50000
N_FRAUD = 1500  # ~3% fraud rate (réaliste pour SEPA instantané)

HIGH_RISK_COUNTRIES = ["CY", "MT", "BVI", "KY", "LI", "MC", "SM"]
SEPA_COUNTRIES = ["FR", "DE", "ES", "IT", "BE", "NL", "PT", "AT", "IE", "FI", "LU", "SK", "SI", "EE", "LV", "LT", "GR"]
FRAUD_DEVICE_TYPES = ["unknown", "vpn_detected", "tor_exit", "emulator"]
LEGIT_DEVICE_TYPES = ["mobile_ios", "mobile_android", "desktop_windows", "desktop_mac", "tablet"]

def random_iban(country="FR"):
    return f"{country}{random.randint(10,99)} {random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(100000000000,999999999999)}"

def generate_legit_transactions(n):
    records = []
    for _ in range(n):
        p_legit = [0.005,0.003,0.002,0.002,0.003,0.008,0.02,0.05,0.08,0.09,0.09,0.08,
                   0.07,0.08,0.08,0.07,0.06,0.05,0.04,0.03,0.025,0.02,0.015,0.012]
        p_legit = [x/sum(p_legit) for x in p_legit]
        hour = int(np.random.choice(range(24), p=p_legit))
        day_of_week = random.randint(0, 6)
        amount = np.random.lognormal(mean=5.5, sigma=1.2)
        amount = min(max(amount, 1), 15000)

        src_country = random.choice(["FR"] * 8 + SEPA_COUNTRIES)
        dst_country = random.choice(["FR"] * 7 + SEPA_COUNTRIES)

        rec = {
            "transaction_id": f"TXN{random.randint(100000000, 999999999)}",
            "timestamp": (datetime(2024, 1, 1) + timedelta(
                days=random.randint(0, 364),
                hours=hour,
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59)
            )).isoformat(),
            "amount_eur": round(amount, 2),
            "source_country": src_country,
            "destination_country": dst_country,
            "hour_of_day": hour,
            "day_of_week": day_of_week,
            "is_weekend": int(day_of_week >= 5),
            "is_night": int(hour < 6 or hour >= 23),

            # Compte features
            "account_age_days": random.randint(60, 3650),
            "avg_monthly_transactions": random.randint(5, 80),
            "avg_monthly_amount": round(np.random.lognormal(6.5, 0.8), 2),
            "nb_beneficiaries_30d": random.randint(1, 15),
            "is_new_beneficiary": int(random.random() < 0.15),

            # Vélocité
            "nb_transactions_1h": random.randint(0, 3),
            "nb_transactions_24h": random.randint(1, 12),
            "amount_ratio_to_avg": round(np.random.lognormal(0, 0.4), 3),

            # Device / Session
            "device_type": random.choice(LEGIT_DEVICE_TYPES),
            "device_age_days": random.randint(1, 1000),
            "session_duration_sec": random.randint(30, 600),
            "nb_auth_attempts": random.randint(1, 2),
            "ip_country_match": int(random.random() < 0.92),
            "is_vpn": 0,
            "is_tor": 0,

            # Géo
            "distance_km_from_usual": round(np.random.exponential(50), 1),

            # Label
            "is_fraud": 0
        }
        records.append(rec)
    return records


def generate_fraud_transactions(n):
    records = []
    fraud_patterns = {
        "account_takeover": 0.35,
        "social_engineering": 0.30,
        "money_mule": 0.20,
        "bec": 0.15,
    }

    for _ in range(n):
        pattern = np.random.choice(list(fraud_patterns.keys()), p=list(fraud_patterns.values()))

        # Les fraudes arrivent surtout la nuit/weekend
        p_fraud = [0.06,0.07,0.08,0.07,0.06,0.04,0.03,0.03,0.04,0.04,0.04,0.04,
                   0.04,0.04,0.04,0.04,0.04,0.04,0.05,0.05,0.05,0.05,0.06,0.06]
        p_fraud = [x/sum(p_fraud) for x in p_fraud]
        hour = int(np.random.choice(range(24), p=p_fraud))
        day_of_week = np.random.choice([5, 6, 0, 1, 2, 3, 4], p=[0.22, 0.22, 0.1, 0.1, 0.1, 0.13, 0.13])

        if pattern == "account_takeover":
            amount = round(random.uniform(2000, 24999), 2)
            dst_country = random.choice(HIGH_RISK_COUNTRIES + ["CY", "CY", "MT"])
            new_bene = 1
            velocity_1h = random.randint(1, 5)
            amount_ratio = round(random.uniform(3, 15), 3)
            device = random.choice(FRAUD_DEVICE_TYPES)
            vpn = int(random.random() < 0.7)
            session_dur = random.randint(5, 90)
            auth_attempts = random.randint(1, 5)
            distance = round(random.uniform(500, 5000), 1)

        elif pattern == "social_engineering":
            amount = round(random.uniform(500, 8000), 2)
            dst_country = random.choice(SEPA_COUNTRIES + HIGH_RISK_COUNTRIES[:2])
            new_bene = 1
            velocity_1h = random.randint(0, 2)
            amount_ratio = round(random.uniform(1.5, 8), 3)
            device = random.choice(LEGIT_DEVICE_TYPES)  # victime utilise son vrai device
            vpn = 0
            session_dur = random.randint(60, 300)
            auth_attempts = 1
            distance = round(random.uniform(0, 200), 1)

        elif pattern == "money_mule":
            amount = round(random.uniform(500, 4999), 2)
            dst_country = random.choice(SEPA_COUNTRIES)
            new_bene = 1
            velocity_1h = random.randint(2, 8)
            amount_ratio = round(random.uniform(2, 10), 3)
            device = random.choice(LEGIT_DEVICE_TYPES + FRAUD_DEVICE_TYPES[:1])
            vpn = int(random.random() < 0.3)
            session_dur = random.randint(10, 120)
            auth_attempts = random.randint(1, 3)
            distance = round(random.uniform(100, 2000), 1)

        else:  # BEC
            amount = round(random.uniform(5000, 50000), 2)
            dst_country = random.choice(HIGH_RISK_COUNTRIES + ["HK", "SG", "AE"])
            new_bene = 1
            velocity_1h = random.randint(0, 1)
            amount_ratio = round(random.uniform(5, 30), 3)
            device = random.choice(LEGIT_DEVICE_TYPES)
            vpn = int(random.random() < 0.4)
            session_dur = random.randint(120, 600)
            auth_attempts = 1
            distance = round(random.uniform(200, 8000), 1)

        rec = {
            "transaction_id": f"TXN{random.randint(100000000, 999999999)}",
            "timestamp": (datetime(2024, 1, 1) + timedelta(
                days=random.randint(0, 364),
                hours=hour,
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59)
            )).isoformat(),
            "amount_eur": amount,
            "source_country": "FR",
            "destination_country": dst_country,
            "hour_of_day": hour,
            "day_of_week": day_of_week,
            "is_weekend": int(day_of_week >= 5),
            "is_night": int(hour < 6 or hour >= 23),

            "account_age_days": random.randint(1, 400),
            "avg_monthly_transactions": random.randint(2, 30),
            "avg_monthly_amount": round(np.random.lognormal(5.5, 1), 2),
            "nb_beneficiaries_30d": random.randint(1, 5),
            "is_new_beneficiary": new_bene,

            "nb_transactions_1h": velocity_1h,
            "nb_transactions_24h": random.randint(velocity_1h, velocity_1h + 10),
            "amount_ratio_to_avg": amount_ratio,

            "device_type": device,
            "device_age_days": random.randint(0, 30),
            "session_duration_sec": session_dur,
            "nb_auth_attempts": auth_attempts,
            "ip_country_match": int(random.random() < 0.4),
            "is_vpn": vpn,
            "is_tor": int(random.random() < 0.15),

            "distance_km_from_usual": distance,

            "is_fraud": 1
        }
        records.append(rec)
    return records


def build_dataset():
    print("🔄 Génération du dataset SEPA synthétique...")
    legit = generate_legit_transactions(N_LEGIT)
    fraud = generate_fraud_transactions(N_FRAUD)

    df = pd.DataFrame(legit + fraud).sample(frac=1, random_state=42).reset_index(drop=True)

    os.makedirs(os.path.dirname(os.path.abspath(__file__)), exist_ok=True)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sepa_transactions.csv")
    df.to_csv(out, index=False)

    print(f"✅ Dataset généré : {len(df)} transactions")
    print(f"   └─ Légitimes : {df['is_fraud'].eq(0).sum()} ({df['is_fraud'].eq(0).mean()*100:.1f}%)")
    print(f"   └─ Frauduleuses : {df['is_fraud'].eq(1).sum()} ({df['is_fraud'].eq(1).mean()*100:.1f}%)")
    print(f"   └─ Fichier : {out}")
    return df


if __name__ == "__main__":
    build_dataset()
