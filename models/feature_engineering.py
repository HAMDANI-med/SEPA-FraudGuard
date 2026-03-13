"""
Feature Engineering pour la détection de fraude SEPA.
Transforme les métadonnées brutes en features ML-ready.
"""

import numpy as np
import pandas as pd


HIGH_RISK_COUNTRIES = {"CY", "MT", "BVI", "KY", "LI", "MC", "SM", "HK", "AE", "SG"}
SEPA_COUNTRIES = {
    "FR","DE","ES","IT","BE","NL","PT","AT","IE","FI",
    "LU","SK","SI","EE","LV","LT","GR","HR","CZ","HU",
    "PL","RO","BG","DK","SE","NO","IS","LI","CH"
}

DEVICE_RISK = {
    "mobile_ios": 0.1,
    "mobile_android": 0.15,
    "desktop_windows": 0.2,
    "desktop_mac": 0.1,
    "tablet": 0.15,
    "unknown": 0.8,
    "vpn_detected": 0.85,
    "tor_exit": 0.95,
    "emulator": 0.9,
}


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applique tout le feature engineering sur un DataFrame brut.
    Retourne un DataFrame prêt pour l'entraînement ou l'inférence.
    """
    df = df.copy()

    # --- Features temporelles ---
    df["is_business_hours"] = ((df["hour_of_day"] >= 8) & (df["hour_of_day"] <= 18) & (df["is_weekend"] == 0)).astype(int)
    df["time_risk_score"] = (
        df["is_night"].astype(float) * 0.5
        + df["is_weekend"].astype(float) * 0.3
        + (1 - df["is_business_hours"].astype(float)) * 0.2
    )

    # --- Features montant ---
    df["amount_log"] = np.log1p(df["amount_eur"])
    df["is_round_amount"] = (df["amount_eur"] % 100 == 0).astype(int)
    df["is_high_amount"] = (df["amount_eur"] > 10000).astype(int)
    df["is_threshold_amount"] = ((df["amount_eur"] >= 9000) & (df["amount_eur"] < 10000)).astype(int)  # "structuring"
    df["amount_vs_avg_log"] = np.log1p(df["amount_ratio_to_avg"])

    # --- Features géographiques ---
    df["dst_is_high_risk"] = df["destination_country"].isin(HIGH_RISK_COUNTRIES).astype(int)
    df["dst_is_sepa"] = df["destination_country"].isin(SEPA_COUNTRIES).astype(int)
    df["is_cross_border"] = (df["source_country"] != df["destination_country"]).astype(int)
    df["geo_risk_score"] = (
        df["dst_is_high_risk"] * 0.6
        + df["is_cross_border"] * 0.2
        + (1 - df["ip_country_match"]) * 0.2
    )
    df["distance_log"] = np.log1p(df["distance_km_from_usual"])

    # --- Features device / session ---
    df["device_risk"] = df["device_type"].map(DEVICE_RISK).fillna(0.5)
    df["device_is_new"] = (df["device_age_days"] < 7).astype(int)
    df["session_is_short"] = (df["session_duration_sec"] < 30).astype(int)
    df["multi_auth"] = (df["nb_auth_attempts"] > 2).astype(int)
    df["device_session_risk"] = (
        df["device_risk"] * 0.4
        + df["is_vpn"] * 0.25
        + df["is_tor"] * 0.35
    )

    # --- Features vélocité ---
    df["velocity_risk"] = (
        np.log1p(df["nb_transactions_1h"]) * 0.5
        + np.log1p(df["nb_transactions_24h"]) * 0.3
        + df["amount_ratio_to_avg"].clip(0, 20) / 20 * 0.2
    )

    # --- Features compte ---
    df["account_is_new"] = (df["account_age_days"] < 30).astype(int)
    df["account_age_log"] = np.log1p(df["account_age_days"])
    df["low_activity"] = (df["avg_monthly_transactions"] < 5).astype(int)

    # --- Score de risque composite (pour analyse, pas pour le modèle) ---
    df["composite_risk"] = (
        df["time_risk_score"] * 0.15
        + df["geo_risk_score"] * 0.25
        + df["device_session_risk"] * 0.25
        + df["velocity_risk"] * 0.20
        + df["is_new_beneficiary"] * 0.10
        + df["account_is_new"] * 0.05
    ).clip(0, 1)

    return df


def get_feature_columns():
    """Retourne la liste des features utilisées par le modèle ML."""
    return [
        # Temporel
        "hour_of_day", "is_weekend", "is_night", "is_business_hours", "time_risk_score",
        # Montant
        "amount_log", "is_round_amount", "is_high_amount", "is_threshold_amount",
        "amount_vs_avg_log", "amount_ratio_to_avg",
        # Géo
        "dst_is_high_risk", "dst_is_sepa", "is_cross_border", "geo_risk_score",
        "ip_country_match", "distance_log",
        # Device
        "device_risk", "device_is_new", "session_is_short", "multi_auth",
        "device_session_risk", "is_vpn", "is_tor",
        # Vélocité
        "nb_transactions_1h", "nb_transactions_24h", "velocity_risk",
        # Compte
        "account_age_log", "account_is_new", "low_activity",
        "nb_beneficiaries_30d", "is_new_beneficiary",
        # Composite
        "composite_risk",
    ]


def preprocess_api_input(data: dict) -> pd.DataFrame:
    """
    Transforme un JSON d'entrée API en DataFrame feature-engineered.
    Gère les valeurs manquantes avec des valeurs par défaut prudentes.
    """
    defaults = {
        "amount_eur": 100.0,
        "source_country": "FR",
        "destination_country": "FR",
        "hour_of_day": 12,
        "day_of_week": 1,
        "is_weekend": 0,
        "is_night": 0,
        "account_age_days": 365,
        "avg_monthly_transactions": 20,
        "avg_monthly_amount": 1000.0,
        "nb_beneficiaries_30d": 5,
        "is_new_beneficiary": 0,
        "nb_transactions_1h": 0,
        "nb_transactions_24h": 1,
        "amount_ratio_to_avg": 1.0,
        "device_type": "unknown",
        "device_age_days": 30,
        "session_duration_sec": 120,
        "nb_auth_attempts": 1,
        "ip_country_match": 1,
        "is_vpn": 0,
        "is_tor": 0,
        "distance_km_from_usual": 0.0,
    }
    row = {**defaults, **data}
    df = pd.DataFrame([row])
    df = engineer_features(df)
    return df[get_feature_columns()]
