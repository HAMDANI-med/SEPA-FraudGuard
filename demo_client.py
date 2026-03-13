#!/usr/bin/env python3
"""Demo scoring - fonctionne sans serveur."""

import sys, os, time, importlib.util

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path: sys.path.insert(0, BASE_DIR)

def _load(name, path):
    if name in sys.modules: return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_load("feature_engineering", os.path.join(BASE_DIR,"models","feature_engineering.py"))
sys.modules["models.feature_engineering"] = sys.modules["feature_engineering"]
fs_mod = _load("fraud_scorer", os.path.join(BASE_DIR,"fraud_scorer.py"))
FraudScorer = fs_mod.FraudScorer

DEMOS = [
    ("OK  - Virement ordinaire Paris->Lyon", {
        "transaction_id":"DEMO-001","amount_eur":480,"source_country":"FR",
        "destination_country":"FR","hour_of_day":10,"day_of_week":1,"is_weekend":0,
        "is_night":0,"account_age_days":1200,"avg_monthly_transactions":18,
        "avg_monthly_amount":900,"nb_beneficiaries_30d":6,"is_new_beneficiary":0,
        "nb_transactions_1h":0,"nb_transactions_24h":1,"amount_ratio_to_avg":0.7,
        "device_type":"mobile_ios","device_age_days":400,"session_duration_sec":210,
        "nb_auth_attempts":1,"ip_country_match":1,"is_vpn":0,"is_tor":0,
        "distance_km_from_usual":8}),
    ("WARN- Nouveau beneficiaire weekend soir", {
        "transaction_id":"DEMO-002","amount_eur":3500,"source_country":"FR",
        "destination_country":"ES","hour_of_day":22,"day_of_week":5,"is_weekend":1,
        "is_night":0,"account_age_days":120,"avg_monthly_transactions":10,
        "avg_monthly_amount":600,"nb_beneficiaries_30d":2,"is_new_beneficiary":1,
        "nb_transactions_1h":1,"nb_transactions_24h":3,"amount_ratio_to_avg":4.2,
        "device_type":"desktop_windows","device_age_days":20,"session_duration_sec":65,
        "nb_auth_attempts":2,"ip_country_match":1,"is_vpn":0,"is_tor":0,
        "distance_km_from_usual":180}),
    ("FRAU- Account Takeover (Chypre, nuit, VPN)", {
        "transaction_id":"DEMO-003","amount_eur":18500,"source_country":"FR",
        "destination_country":"CY","hour_of_day":3,"day_of_week":6,"is_weekend":1,
        "is_night":1,"account_age_days":30,"avg_monthly_transactions":5,
        "avg_monthly_amount":400,"nb_beneficiaries_30d":1,"is_new_beneficiary":1,
        "nb_transactions_1h":3,"nb_transactions_24h":5,"amount_ratio_to_avg":14.8,
        "device_type":"vpn_detected","device_age_days":1,"session_duration_sec":18,
        "nb_auth_attempts":4,"ip_country_match":0,"is_vpn":1,"is_tor":0,
        "distance_km_from_usual":2200}),
    ("FRAU- BEC (Iles Vierges, TOR, 42k EUR)", {
        "transaction_id":"DEMO-004","amount_eur":42000,"source_country":"FR",
        "destination_country":"BVI","hour_of_day":11,"day_of_week":2,"is_weekend":0,
        "is_night":0,"account_age_days":8,"avg_monthly_transactions":3,
        "avg_monthly_amount":500,"nb_beneficiaries_30d":1,"is_new_beneficiary":1,
        "nb_transactions_1h":1,"nb_transactions_24h":2,"amount_ratio_to_avg":28,
        "device_type":"tor_exit","device_age_days":0,"session_duration_sec":40,
        "nb_auth_attempts":1,"ip_country_match":0,"is_vpn":0,"is_tor":1,
        "distance_km_from_usual":9000}),
]

def bar(score):
    f = int(score/5)
    return f"{'#'*f}{'.'*(20-f)} {score:.1f}/100"

def run():
    print("\n" + "="*60)
    print("  SEPA FraudGuard - Demo Scoring Temps Reel")
    print("="*60 + "\n")

    try:
        scorer = FraudScorer("ensemble")
    except FileNotFoundError:
        print("ERREUR: Modele introuvable. Lancez d'abord: python train.py")
        sys.exit(1)

    results = []
    for label, txn in DEMOS:
        print(f"  Transaction : {label}")
        print(f"  {'-'*55}")
        t0 = time.perf_counter()
        r = scorer.score(txn)
        lat = (time.perf_counter()-t0)*1000
        print(f"  Score       : [{bar(r['fraud_score'])}]")
        print(f"  Decision    : {r['decision']} - {r['decision_label']}")
        print(f"  Confiance   : {r['confidence']}  |  Latence: {lat:.1f}ms")
        if r["triggered_rules"]:
            print(f"  Regles      : {', '.join(x['code'] for x in r['triggered_rules'])}")
        print(f"  Explications:")
        for e in r["explanations"][:3]:
            print(f"    > {e}")
        results.append(r)
        print()

    bl = sum(1 for r in results if r["decision"]=="BLOCK")
    rv = sum(1 for r in results if r["decision"]=="REVIEW")
    al = sum(1 for r in results if r["decision"]=="ALLOW")
    print("="*60)
    print(f"  Bilan: {len(results)} transactions | BLOCK:{bl}  REVIEW:{rv}  ALLOW:{al}")
    print("="*60 + "\n")

if __name__ == "__main__":
    run()
