"""
=============================================================================
DEMO — Nouveautes fraud_scorer.py
=============================================================================
Ce script demontre les 2 ajouts :
  1. Regle IBAN_NAME_MISMATCH  (Reglement UE 2024/886)
  2. Exemption SCA DSP2        (RTS DSP2 Art. 18)

Lancement :
    python demo_nouveautes.py

Prerequis : l'API doit tourner sur localhost:8000
    → ouvrir un terminal et lancer : python api.py
=============================================================================
"""

import json
import urllib.request
import urllib.error
import time

API_URL = "http://localhost:8000"

# ─── Couleurs terminal ────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    GREY   = "\033[90m"

# ─── Helpers affichage ────────────────────────────────────────────────────────
def titre(text):
    print()
    print(C.BOLD + C.BLUE + "=" * 70 + C.RESET)
    print(C.BOLD + C.WHITE + f"  {text}" + C.RESET)
    print(C.BOLD + C.BLUE + "=" * 70 + C.RESET)

def sous_titre(text):
    print()
    print(C.BOLD + C.CYAN + f"── {text}" + C.RESET)
    print(C.GREY + "─" * 50 + C.RESET)

def ok(text):   print(C.GREEN  + "  ✓ " + C.RESET + text)
def err(text):  print(C.RED    + "  ✗ " + C.RESET + text)
def info(text): print(C.YELLOW + "  → " + C.RESET + text)
def gris(text): print(C.GREY   + "    " + text + C.RESET)

def decision_badge(dec):
    if dec == "BLOCK":  return C.RED    + C.BOLD + "[ BLOCK  ]" + C.RESET
    if dec == "REVIEW": return C.YELLOW + C.BOLD + "[ REVIEW ]" + C.RESET
    return                      C.GREEN + C.BOLD + "[ ALLOW  ]" + C.RESET

def call_api(endpoint, payload=None, method="POST"):
    """Appelle l'API et retourne le JSON de reponse."""
    url = API_URL + endpoint
    if payload:
        body = json.dumps(payload).encode("utf-8")
        req  = urllib.request.Request(
            url, data=body, method=method,
            headers={"Content-Type": "application/json"}
        )
    else:
        req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}

def afficher_resultat(r):
    """Affiche le resultat d'un appel /score de facon lisible."""
    if "error" in r:
        err(f"Erreur API : {r['error']}")
        return

    print()
    print(f"  {'Décision':<22} {decision_badge(r.get('decision','?'))}")
    print(f"  {'Fraud score':<22} {C.BOLD}{r.get('fraud_score','?')}{C.RESET} / 100")
    print(f"  {'ML score':<22} {r.get('ml_score','?')}")
    print(f"  {'Rules boost':<22} +{r.get('rules_boost','?')} pts")
    print(f"  {'Confiance':<22} {r.get('confidence','?')}")
    print(f"  {'Latence':<22} {r.get('latency_ms','?')} ms")

    # Regles declenchees
    rules = r.get("triggered_rules", [])
    if rules:
        print()
        print(f"  {C.BOLD}Règles déclenchées :{C.RESET}")
        for rule in rules:
            sev = rule.get("severity","")
            col = C.RED if sev == "critical" else (C.YELLOW if sev == "high" else C.CYAN)
            print(f"    {col}[{sev.upper():8}]{C.RESET}  {rule['code']:<22}  +{rule['score_boost']} pts")
            gris(f"             {rule['description']}")

    # Bloc DSP2/SCA
    dsp2 = r.get("dsp2_sca")
    if dsp2:
        print()
        print(f"  {C.BOLD}DSP2 / SCA :{C.RESET}")
        eligible = dsp2.get("exemption_eligible", False)
        badge = C.GREEN + "EXEMPTÉE" + C.RESET if eligible else C.YELLOW + "SCA REQUISE" + C.RESET
        print(f"    Authentification forte : {badge}")
        rate = dsp2.get("session_fraud_rate")
        if rate is not None:
            print(f"    Taux fraude session     : {rate*100:.4f}%")
        gris(f"    {dsp2.get('exemption_reason','')}")

    # Explications
    expl = r.get("explanations", [])
    if expl:
        print()
        print(f"  {C.BOLD}Explications :{C.RESET}")
        for e in expl:
            gris(f"  • {e}")

def attendre(msg="Appuyez sur Entrée pour continuer..."):
    print()
    input(C.GREY + f"  {msg}" + C.RESET)


# =============================================================================
# VERIFICATION API
# =============================================================================
def check_api():
    titre("Vérification de l'API")
    r = call_api("/health", method="GET")
    if "error" in r:
        err("L'API ne répond pas !")
        err(f"Détail : {r['error']}")
        print()
        print(C.RED + "  → Lance d'abord : python api.py" + C.RESET)
        return False
    ok(f"API active — version {r.get('version','?')}")
    ok(f"Modèle chargé : {r.get('models_loaded', ['?'])[0]}")
    ok(f"Uptime : {r.get('uptime_seconds','?'):.1f} secondes")
    return True


# =============================================================================
# PARTIE 1 — REGLE IBAN_NAME_MISMATCH
# =============================================================================
def demo_iban_mismatch():
    titre("PARTIE 1 — Règle IBAN_NAME_MISMATCH")
    print(C.GREY + """
  Règlement UE 2024/886 (SEPA SCT Inst.) applicable depuis octobre 2025 :
  Les banques doivent vérifier que le nom du titulaire correspond à l'IBAN
  de destination avant d'exécuter un virement instantané.

  → Severity CRITICAL : force BLOCK même si le score ML est 0
  → Score boost : +50 points
  → Champ à envoyer dans la requête : "iban_name_mismatch": 1
    """ + C.RESET)

    attendre("Appuyez sur Entrée pour le scénario 1A — Sans discordance IBAN...")

    # ── Scénario 1A : transaction normale, pas de discordance ──────────────
    sous_titre("Scénario 1A — Virement normal (iban_name_mismatch: 0)")
    info("250 € · FR→DE · 10h · aucun signal suspect · iban_name_mismatch = 0")

    txn_normale = {
        "transaction_id":        "DEMO-IBAN-OK",
        "amount_eur":            250,
        "source_country":        "FR",
        "destination_country":   "DE",
        "hour_of_day":           10,
        "day_of_week":           2,
        "is_weekend":            0,
        "is_night":              0,
        "account_age_days":      730,
        "avg_monthly_transactions": 15,
        "avg_monthly_amount":    1200,
        "nb_beneficiaries_30d":  6,
        "is_new_beneficiary":    0,
        "nb_transactions_1h":    0,
        "nb_transactions_24h":   1,
        "amount_ratio_to_avg":   0.9,
        "device_type":           "mobile_ios",
        "device_age_days":       400,
        "session_duration_sec":  120,
        "nb_auth_attempts":      1,
        "ip_country_match":      1,
        "is_vpn":                0,
        "is_tor":                0,
        "distance_km_from_usual": 10,
        "iban_name_mismatch":    0,   # ← PAS de discordance
    }

    r = call_api("/score", txn_normale)
    afficher_resultat(r)

    attendre("Appuyez sur Entrée pour le scénario 1B — Avec discordance IBAN...")

    # ── Scénario 1B : même transaction, mais IBAN/nom ne correspond pas ────
    sous_titre("Scénario 1B — Même transaction avec iban_name_mismatch: 1")
    info("250 € · FR→DE · 10h · MÊME transaction mais iban_name_mismatch = 1")
    print(C.YELLOW + "  → Attendu : BLOCK automatique (severity CRITICAL)" + C.RESET)

    txn_mismatch = dict(txn_normale)
    txn_mismatch["transaction_id"]   = "DEMO-IBAN-MISMATCH"
    txn_mismatch["iban_name_mismatch"] = 1   # ← discordance activée

    r = call_api("/score", txn_mismatch)
    afficher_resultat(r)

    attendre("Appuyez sur Entrée pour le scénario 1C — IBAN mismatch + fraude cumulée...")

    # ── Scénario 1C : IBAN mismatch + autres signaux suspects ──────────────
    sous_titre("Scénario 1C — IBAN mismatch + signaux suspects cumulés")
    info("18 000 € · FR→CY · 2h du matin · VPN · nouveau bénéficiaire · iban_name_mismatch = 1")
    print(C.RED + "  → Attendu : BLOCK · score proche de 100 · plusieurs règles critiques" + C.RESET)

    txn_cumul = {
        "transaction_id":        "DEMO-IBAN-CUMUL",
        "amount_eur":            18000,
        "source_country":        "FR",
        "destination_country":   "CY",          # Chypre = high risk
        "hour_of_day":           2,
        "day_of_week":           6,
        "is_weekend":            1,
        "is_night":              1,
        "account_age_days":      45,
        "avg_monthly_transactions": 8,
        "avg_monthly_amount":    600,
        "nb_beneficiaries_30d":  2,
        "is_new_beneficiary":    1,
        "nb_transactions_1h":    2,
        "nb_transactions_24h":   3,
        "amount_ratio_to_avg":   12.5,
        "device_type":           "vpn_detected",
        "device_age_days":       2,
        "session_duration_sec":  22,
        "nb_auth_attempts":      3,
        "ip_country_match":      0,
        "is_vpn":                1,
        "is_tor":                0,
        "distance_km_from_usual": 1800,
        "iban_name_mismatch":    1,             # ← discordance activée
    }

    r = call_api("/score", txn_cumul)
    afficher_resultat(r)


# =============================================================================
# PARTIE 2 — EXEMPTION SCA DSP2
# =============================================================================
def demo_dsp2_sca():
    titre("PARTIE 2 — Exemption SCA DSP2 (RTS DSP2 Art. 18)")
    print(C.GREY + """
  Principe DSP2 Article 18 :
  Un PSP dont le taux de fraude est suffisamment bas peut exempter
  certaines transactions de l'authentification forte (SCA).

  Paliers réglementaires :
    Taux < 0.01%  →  Exemption jusqu'à 500 EUR
    Taux < 0.06%  →  Exemption jusqu'à 250 EUR
    Taux < 0.13%  →  Exemption jusqu'à 100 EUR

  Le scorer calcule le taux en temps réel sur la session courante.
  Il faut au minimum 100 transactions pour activer le calcul.
    """ + C.RESET)

    attendre("Appuyez sur Entrée pour démarrer — on va envoyer 105 transactions légitimes...")

    # ── Étape 1 : envoyer 105 transactions légitimes pour monter le volume ──
    sous_titre("Étape 1 — Envoi de 105 transactions légitimes (remplissage volume)")
    info("Envoi en cours... (quelques secondes)")

    txn_base = {
        "amount_eur":            80,
        "source_country":        "FR",
        "destination_country":   "FR",
        "hour_of_day":           14,
        "day_of_week":           2,
        "is_weekend":            0,
        "is_night":              0,
        "account_age_days":      900,
        "avg_monthly_transactions": 20,
        "avg_monthly_amount":    500,
        "nb_beneficiaries_30d":  10,
        "is_new_beneficiary":    0,
        "nb_transactions_1h":    0,
        "nb_transactions_24h":   1,
        "amount_ratio_to_avg":   0.7,
        "device_type":           "mobile_ios",
        "device_age_days":       500,
        "session_duration_sec":  200,
        "nb_auth_attempts":      1,
        "ip_country_match":      1,
        "is_vpn":                0,
        "is_tor":                0,
        "distance_km_from_usual": 5,
        "iban_name_mismatch":    0,
    }

    nb_allow = 0
    nb_block = 0
    for i in range(105):
        txn = dict(txn_base)
        txn["transaction_id"] = f"VOLUME-{i+1:03d}"
        r = call_api("/score", txn)
        dec = r.get("decision", "?")
        if dec == "ALLOW": nb_allow += 1
        if dec == "BLOCK": nb_block += 1
        # Affichage progression tous les 25
        if (i + 1) % 25 == 0 or i == 104:
            print(f"    {C.GREY}{i+1:3d}/105 transactions envoyées"
                  f"  ALLOW={nb_allow}  BLOCK={nb_block}{C.RESET}")

    ok(f"Volume atteint : {nb_allow + nb_block} transactions")
    ok(f"Taux de fraude session : ~0.00% ({nb_block} BLOCK sur {nb_allow+nb_block})")

    attendre("Appuyez sur Entrée pour tester l'exemption SCA sur un petit montant...")

    # ── Étape 2 : transaction éligible à l'exemption SCA ───────────────────
    sous_titre("Étape 2 — Transaction éligible à l'exemption SCA")
    info("75 € · FR→FR · profil normal · taux fraude 0.00% → exemption jusqu'à 500 EUR")
    print(C.GREEN + "  → Attendu : ALLOW + exemption_eligible = true" + C.RESET)

    txn_petit = dict(txn_base)
    txn_petit["transaction_id"] = "DEMO-DSP2-EXEMPT"
    txn_petit["amount_eur"]     = 75   # < 500 EUR → éligible

    r = call_api("/score", txn_petit)
    afficher_resultat(r)

    attendre("Appuyez sur Entrée pour tester un montant qui dépasse le seuil d'exemption...")

    # ── Étape 3 : montant trop élevé pour l'exemption ───────────────────────
    sous_titre("Étape 3 — Montant au-dessus du seuil d'exemption")
    info("750 € · FR→FR · profil normal · taux fraude 0.00% mais montant > 500 EUR")
    print(C.YELLOW + "  → Attendu : ALLOW mais exemption_eligible = false (montant > 500 EUR)" + C.RESET)

    txn_moyen = dict(txn_base)
    txn_moyen["transaction_id"]   = "DEMO-DSP2-OVER-SEUIL"
    txn_moyen["amount_eur"]       = 750   # > 500 EUR → pas d'exemption
    txn_moyen["amount_ratio_to_avg"] = 1.5

    r = call_api("/score", txn_moyen)
    afficher_resultat(r)

    attendre("Appuyez sur Entrée pour injecter quelques fraudes et voir l'impact sur le taux...")

    # ── Étape 4 : injecter des fraudes pour faire monter le taux ────────────
    sous_titre("Étape 4 — Injection de fraudes (dégradation du taux DSP2)")
    info("Envoi de 5 transactions frauduleuses...")

    txn_fraude = {
        "transaction_id":        "FRAUDE-DSP2",
        "amount_eur":            15000,
        "source_country":        "FR",
        "destination_country":   "CY",
        "hour_of_day":           3,
        "day_of_week":           6,
        "is_weekend":            1,
        "is_night":              1,
        "account_age_days":      3,
        "avg_monthly_transactions": 5,
        "avg_monthly_amount":    200,
        "nb_beneficiaries_30d":  1,
        "is_new_beneficiary":    1,
        "nb_transactions_1h":    4,
        "nb_transactions_24h":   5,
        "amount_ratio_to_avg":   30.0,
        "device_type":           "tor_exit",
        "device_age_days":       0,
        "session_duration_sec":  8,
        "nb_auth_attempts":      5,
        "ip_country_match":      0,
        "is_vpn":                1,
        "is_tor":                1,
        "distance_km_from_usual": 3000,
        "iban_name_mismatch":    0,
    }

    for i in range(5):
        txn_f = dict(txn_fraude)
        txn_f["transaction_id"] = f"FRAUDE-DSP2-{i+1}"
        r = call_api("/score", txn_f)
        dec = r.get("decision", "?")
        rate = r.get("dsp2_sca", {}).get("session_fraud_rate")
        rate_str = f"{rate*100:.4f}%" if rate is not None else "N/A"
        print(f"    Fraude {i+1}/5 → {decision_badge(dec)}  "
              f"taux session : {C.RED}{rate_str}{C.RESET}")

    attendre("Appuyez sur Entrée pour re-tester la transaction de 75 € après les fraudes...")

    # ── Étape 5 : re-tester le petit montant — l'exemption a changé ─────────
    sous_titre("Étape 5 — Re-test 75 € après dégradation du taux")
    info("75 € · même profil qu'avant · mais le taux de fraude a augmenté")
    print(C.YELLOW + "  → Le niveau d'exemption DSP2 peut avoir changé" + C.RESET)

    txn_retest = dict(txn_base)
    txn_retest["transaction_id"] = "DEMO-DSP2-RETEST"
    txn_retest["amount_eur"]     = 75

    r = call_api("/score", txn_retest)
    afficher_resultat(r)


# =============================================================================
# PARTIE 3 — STATS SESSION (vue DSP2 globale)
# =============================================================================
def demo_stats():
    titre("PARTIE 3 — Stats session & bilan DSP2")

    sous_titre("GET /stats — état de la session")
    r = call_api("/stats", method="GET")

    if "error" in r:
        err(f"Erreur : {r['error']}")
        return

    print()
    # Stats générales
    for k, v in r.items():
        if k != "decisions":
            print(f"  {k:<35} {C.BOLD}{v}{C.RESET}")

    # Répartition décisions
    decisions = r.get("decisions", {})
    if decisions:
        print()
        print(f"  {C.BOLD}Répartition des décisions :{C.RESET}")
        total = sum(decisions.values())
        for dec, count in decisions.items():
            pct = (count / total * 100) if total > 0 else 0
            col = C.RED if dec=="BLOCK" else (C.YELLOW if dec=="REVIEW" else C.GREEN)
            bar = "█" * int(pct / 3)
            print(f"    {col}{dec:<8}{C.RESET}  {count:4d}  {col}{bar}{C.RESET}  {pct:.1f}%")


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print()
    print(C.BOLD + C.BLUE)
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║          SEPA FraudGuard — Demo Nouveautes                  ║")
    print("  ║   Regle IBAN_NAME_MISMATCH + Exemption SCA DSP2             ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print(C.RESET)

    # Vérification API
    if not check_api():
        exit(1)

    attendre("API OK. Appuyez sur Entrée pour démarrer la démonstration...")

    # Partie 1 — IBAN_NAME_MISMATCH
    demo_iban_mismatch()

    # Partie 2 — DSP2 SCA Exemption
    demo_dsp2_sca()

    # Partie 3 — Stats globales
    demo_stats()

    # ── Bilan final ──────────────────────────────────────────────────────────
    titre("BILAN")
    ok("Règle 9 IBAN_NAME_MISMATCH → Sévérité CRITICAL, +50 pts, BLOCK automatique")
    ok("Règlement UE 2024/886 → vérification IBAN/titulaire implémentée")
    ok("Exemption SCA DSP2 → calcul taux fraude session en temps réel")
    ok("3 paliers DSP2 → 100 EUR / 250 EUR / 500 EUR selon taux fraude")
    ok("Bloc dsp2_sca dans chaque réponse API → auditabilité DORA")
    print()
