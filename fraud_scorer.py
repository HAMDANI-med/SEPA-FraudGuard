"""
Moteur de scoring fraude SEPA.
Compatible import direct (sans package).

Regles metier implementees (9 regles) :
  1. HIGH_AMOUNT        — Montant > 25 000 EUR (surveillance DSP2)
  2. HIGH_RISK_COUNTRY  — Destination pays offshore
  3. TOR_EXIT           — Connexion via reseau TOR (critical → BLOCK auto)
  4. VPN_DETECTED       — IP masquee via VPN
  5. MULTIPLE_AUTH      — >= 3 tentatives d'authentification
  6. VELOCITY_ANOMALY   — >= 3 virements/h + montant > 1 000 EUR
  7. NEW_BENE_HIGH      — Nouveau beneficiaire + montant > 5 000 EUR
  8. FRESH_ACCOUNT      — Compte < 7 jours + montant > 500 EUR
  9. IBAN_NAME_MISMATCH — Discordance IBAN/titulaire (Reglement UE 2024/886)

Conformite DSP2/SCA :
  - Taux de fraude calcule sur la session courante
  - Exemption SCA accordee si taux < 0.01% ET montant < seuil DSP2
  - Seuils DSP2 : 500 EUR (0.01%), 250 EUR (0.06%), 100 EUR (0.13%)
"""

import os, sys, json, importlib.util
import joblib, numpy as np, pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _ensure_fe():
    """S'assure que feature_engineering est charge."""
    if "feature_engineering" not in sys.modules:
        path = os.path.join(BASE_DIR, "models", "feature_engineering.py")
        spec = importlib.util.spec_from_file_location("feature_engineering", path)
        mod  = importlib.util.module_from_spec(spec)
        sys.modules["feature_engineering"] = mod
        sys.modules["models.feature_engineering"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["feature_engineering"]

HIGH_RISK_COUNTRIES = {"CY","MT","BVI","KY","LI","MC","SM","HK","AE","SG"}
MODELS_DIR = os.path.join(BASE_DIR, "models")

# ─── Seuils DSP2 pour l'exemption SCA ────────────────────────────────────────
# Source : Article 18 RTS DSP2 (Reglement delegue UE 2018/389)
# Principe : plus le taux de fraude du PSP est bas, plus le seuil d'exemption est haut
#
#   Taux de fraude PSP   |  Seuil montant exemption SCA
#   ---------------------|------------------------------
#   < 0.13%              |  jusqu'a 100 EUR
#   < 0.06%              |  jusqu'a 250 EUR
#   < 0.01%              |  jusqu'a 500 EUR
#
DSP2_SCA_THRESHOLDS = [
    {"max_fraud_rate": 0.0001, "max_amount": 500},   # taux < 0.01% → exemption jusqu'a 500 EUR
    {"max_fraud_rate": 0.0006, "max_amount": 250},   # taux < 0.06% → exemption jusqu'a 250 EUR
    {"max_fraud_rate": 0.0013, "max_amount": 100},   # taux < 0.13% → exemption jusqu'a 100 EUR
]


class FraudScorer:
    def __init__(self, model_name="ensemble"):
        self.model_name = model_name
        self.model      = None
        self.threshold  = 0.5
        self.metadata   = {}

        # ── Compteurs de session pour le calcul du taux de fraude DSP2 ──────
        # Ces compteurs s'incrementent a chaque appel a score()
        # Ils permettent de calculer le taux de fraude en temps reel
        # et de determiner si une exemption SCA est applicable
        self._session_total_txn   = 0   # nb total de transactions scorees
        self._session_fraud_txn   = 0   # nb de transactions decidees BLOCK

        self._load()

    def _load(self):
        path      = os.path.join(MODELS_DIR, f"{self.model_name}.pkl")
        meta_path = os.path.join(MODELS_DIR, "model_metadata.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Modele '{self.model_name}' introuvable. Lancez: python train.py")
        self.model = joblib.load(path)
        with open(meta_path) as f:
            self.metadata = json.load(f)
        self.threshold = self.metadata["thresholds"].get(self.model_name, 0.5)
        print(f"Modele '{self.model_name}' charge (seuil: {self.threshold:.2f})")

    # ─────────────────────────────────────────────────────────────────────────
    # METHODE PRIVEE : _rules
    # Verifie les 9 regles metier et retourne la liste des regles declenchees.
    # Chaque regle contient :
    #   - code         : identifiant court de la regle
    #   - severity     : "medium" | "high" | "critical"
    #   - score_boost  : points ajoutes au score final (plafonnes a 40 au total)
    #   - description  : explication lisible par un humain (auditabilite DORA)
    # ─────────────────────────────────────────────────────────────────────────
    def _rules(self, data):
        rules = []

        # ── Regle 1 : HIGH_AMOUNT ─────────────────────────────────────────
        # DSP2 Art. 8 : surveillance renforcee obligatoire au-dela de 25 000 EUR
        if data.get("amount_eur", 0) > 25000:
            rules.append({
                "code": "HIGH_AMOUNT",
                "severity": "high",
                "score_boost": 20,
                "description": "Montant > 25000 EUR - surveillance DSP2"
            })

        # ── Regle 2 : HIGH_RISK_COUNTRY ───────────────────────────────────
        # LCB-FT : destinations offshore classees a risque eleve
        # Liste basee sur les recommandations FATF/GAFI et liste noire UE
        if data.get("destination_country") in HIGH_RISK_COUNTRIES:
            rules.append({
                "code": "HIGH_RISK_COUNTRY",
                "severity": "high",
                "score_boost": 25,
                "description": f"Destination pays a risque: {data.get('destination_country')}"
            })

        # ── Regle 3 : TOR_EXIT ────────────────────────────────────────────
        # Severity CRITICAL : force BLOCK independamment du score ML
        # TOR = anonymisation totale, incompatible avec tracabilite KYC
        if data.get("is_tor", 0):
            rules.append({
                "code": "TOR_EXIT",
                "severity": "critical",
                "score_boost": 40,
                "description": "Connexion via noeud TOR exit - anonymisation totale"
            })

        # ── Regle 4 : VPN_DETECTED ────────────────────────────────────────
        # Severity MEDIUM : un VPN peut etre legitime (telework)
        # mais masque la geolocalisation reelle
        if data.get("is_vpn", 0):
            rules.append({
                "code": "VPN_DETECTED",
                "severity": "medium",
                "score_boost": 15,
                "description": "Connexion VPN detectee - localisation masquee"
            })

        # ── Regle 5 : MULTIPLE_AUTH ───────────────────────────────────────
        # Default = 1 (toute transaction necessite au moins 1 auth SCA)
        # >= 3 tentatives = possible force brute ou difficulte a s'authentifier
        if data.get("nb_auth_attempts", 1) >= 3:
            rules.append({
                "code": "MULTIPLE_AUTH",
                "severity": "medium",
                "score_boost": 20,
                "description": f"{data.get('nb_auth_attempts')} tentatives d'authentification"
            })

        # ── Regle 6 : VELOCITY_ANOMALY ────────────────────────────────────
        # Double condition (and) pour eviter les faux positifs :
        # 3 micro-paiements de 5 EUR = normal / 3 virements de 5000 EUR = suspect
        if data.get("nb_transactions_1h", 0) >= 3 and data.get("amount_eur", 0) > 1000:
            rules.append({
                "code": "VELOCITY_ANOMALY",
                "severity": "high",
                "score_boost": 30,
                "description": "Velocite anormale: plusieurs gros virements en 1h"
            })

        # ── Regle 7 : NEW_BENE_HIGH ───────────────────────────────────────
        # Premier virement vers un beneficiaire inconnu + montant eleve
        # Pattern typique du Social Engineering (arnaque au virement)
        if data.get("is_new_beneficiary", 0) and data.get("amount_eur", 0) > 5000:
            rules.append({
                "code": "NEW_BENE_HIGH",
                "severity": "medium",
                "score_boost": 15,
                "description": "Nouveau beneficiaire + montant eleve (>5000 EUR)"
            })

        # ── Regle 8 : FRESH_ACCOUNT ───────────────────────────────────────
        # Default account_age_days = 365 (si absent = compte etabli = pas de penalite)
        # Compte < 7 jours = profil Money Mule ou compte temporaire fraude
        if data.get("account_age_days", 365) < 7 and data.get("amount_eur", 0) > 500:
            rules.append({
                "code": "FRESH_ACCOUNT",
                "severity": "high",
                "score_boost": 25,
                "description": "Compte cree il y a moins de 7 jours"
            })

        # ── Regle 9 : IBAN_NAME_MISMATCH ─────────────────────────────────
        # Reglement UE 2024/886 (SEPA SCT Inst.) applicable depuis octobre 2025 :
        # Les PSP doivent verifier la concordance IBAN / nom du titulaire
        # avant d'executer tout virement instantane.
        # Severity CRITICAL : discordance = quasi-certitude de fraude ou erreur grave
        # Le champ "iban_name_mismatch" = 1 si la banque detecte une discordance
        if data.get("iban_name_mismatch", 0):
            rules.append({
                "code": "IBAN_NAME_MISMATCH",
                "severity": "critical",
                "score_boost": 50,
                "description": (
                    "Discordance IBAN/titulaire detectee - "
                    "non-conforme Reglement UE 2024/886"
                )
            })

        return rules

    # ─────────────────────────────────────────────────────────────────────────
    # METHODE PRIVEE : _dsp2_sca_exemption
    # Calcule si la transaction peut beneficier d'une exemption SCA
    # selon l'Article 18 du RTS DSP2 (Reglement delegue UE 2018/389).
    #
    # Principe : un PSP (Prestataire de Services de Paiement) dont le taux
    # de fraude est suffisamment bas peut emettre des transactions sans
    # demander de second facteur d'authentification (SCA) jusqu'a un certain
    # montant. Cela reduit la friction pour les clients legitimes.
    #
    # Cette methode utilise les compteurs de session (_session_total_txn,
    # _session_fraud_txn) pour calculer le taux de fraude en temps reel.
    #
    # Retourne un dict avec :
    #   - eligible        : bool  — la transaction est-elle exemptable ?
    #   - reason          : str   — explication de la decision
    #   - current_rate    : float — taux de fraude session courant
    #   - applied_threshold : dict | None — seuil DSP2 applicable
    # ─────────────────────────────────────────────────────────────────────────
    def _dsp2_sca_exemption(self, amount_eur, decision):
        # Pas assez de donnees pour calculer un taux fiable (< 100 transactions)
        if self._session_total_txn < 100:
            return {
                "eligible": False,
                "reason": (
                    f"Volume insuffisant pour calcul de taux DSP2 "
                    f"({self._session_total_txn} transactions, minimum 100 requis)"
                ),
                "current_rate": None,
                "applied_threshold": None
            }

        # Calcul du taux de fraude de la session courante
        # taux = nb_fraudes / nb_total (exprime en proportion, ex: 0.0001 = 0.01%)
        current_rate = self._session_fraud_txn / self._session_total_txn

        # Parcours des seuils DSP2 du plus favorable au moins favorable
        # On cherche le premier seuil dont le taux max est superieur au taux actuel
        applicable = None
        for threshold in DSP2_SCA_THRESHOLDS:
            if current_rate < threshold["max_fraud_rate"]:
                applicable = threshold
                break   # on prend le seuil le plus favorable applicable

        # Aucun seuil applicable : taux trop eleve pour toute exemption
        if applicable is None:
            return {
                "eligible": False,
                "reason": (
                    f"Taux de fraude session {current_rate*100:.4f}% "
                    f"superieur au seuil DSP2 minimum (0.13%)"
                ),
                "current_rate": round(current_rate, 6),
                "applied_threshold": None
            }

        # Seuil trouve : verifier si le montant de la transaction est en dessous
        if amount_eur <= applicable["max_amount"]:
            return {
                "eligible": True,
                "reason": (
                    f"Exemption SCA applicable : taux fraude session "
                    f"{current_rate*100:.4f}% < {applicable['max_fraud_rate']*100:.2f}% "
                    f"et montant {amount_eur} EUR <= {applicable['max_amount']} EUR "
                    f"(RTS DSP2 Art. 18)"
                ),
                "current_rate": round(current_rate, 6),
                "applied_threshold": applicable
            }
        else:
            return {
                "eligible": False,
                "reason": (
                    f"Montant {amount_eur} EUR depasse le seuil d'exemption "
                    f"{applicable['max_amount']} EUR pour ce taux de fraude "
                    f"({current_rate*100:.4f}%)"
                ),
                "current_rate": round(current_rate, 6),
                "applied_threshold": applicable
            }

    # ─────────────────────────────────────────────────────────────────────────
    # METHODE PUBLIQUE : score
    # Point d'entree principal. Recoit les donnees brutes d'une transaction,
    # retourne le score de fraude, la decision, et les metadonnees DSP2.
    # ─────────────────────────────────────────────────────────────────────────
    def score(self, data):
        fe       = _ensure_fe()
        X        = fe.preprocess_api_input(data)
        proba    = float(self.model.predict_proba(X)[0, 1])
        ml_score = round(proba * 100, 2)

        # Evaluation des 9 regles metier
        rules = self._rules(data)

        # Le boost total est plafonne a 40 pour eviter qu'une accumulation
        # de regles mineures n'ecrase completement le signal ML
        boost = min(sum(r["score_boost"] for r in rules), 40)

        # Formule hybride : ML pese 70%, regles pesent 30% (via boost * 0.40)
        final = min(round(ml_score * 0.70 + boost * 0.40, 1), 100)

        # Decision finale :
        # - BLOCK si score >= 75 OU si une regle critical est declenchee
        #   (TOR_EXIT ou IBAN_NAME_MISMATCH forcent BLOCK meme avec ML score = 0)
        # - REVIEW si score entre 40 et 74
        # - ALLOW si score < 40
        if final >= 75 or any(r["severity"] == "critical" for r in rules):
            decision, label = "BLOCK", "Transaction bloquee"
        elif final >= 40:
            decision, label = "REVIEW", "Revue manuelle requise"
        else:
            decision, label = "ALLOW", "Transaction autorisee"

        # ── Mise a jour des compteurs de session pour DSP2 ────────────────
        # On incremente AVANT de calculer l'exemption pour que la transaction
        # courante soit prise en compte dans le taux
        self._session_total_txn += 1
        if decision == "BLOCK":
            self._session_fraud_txn += 1

        # ── Calcul de l'exemption SCA DSP2 ────────────────────────────────
        amount_eur   = data.get("amount_eur", 0)
        sca_exemption = self._dsp2_sca_exemption(amount_eur, decision)

        # ── Construction des explications lisibles (auditabilite DORA) ────
        row  = X.iloc[0]
        expl = []
        if row.get("dst_is_high_risk", 0):
            expl.append("Destination pays a risque eleve")
        if row.get("is_night", 0):
            expl.append("Transaction hors heures habituelles")
        if row.get("amount_vs_avg_log", 0) > 1.5:
            expl.append("Montant bien superieur a la moyenne du compte")
        if row.get("nb_transactions_1h", 0) >= 2:
            expl.append(f"Velocite: {int(row['nb_transactions_1h'])} TXN dans la derniere heure")
        if row.get("is_new_beneficiary", 0):
            expl.append("Premier virement vers ce beneficiaire")
        if row.get("device_risk", 0) > 0.7:
            expl.append("Device ou connexion a risque eleve")
        if row.get("account_is_new", 0):
            expl.append("Compte recemment cree (< 30 jours)")
        for r in rules:
            if r["severity"] in ("high", "critical"):
                expl.append(f"Regle {r['code']}: {r['description']}")
        if not expl:
            expl.append("Aucun signal suspect detecte")

        return {
            "transaction_id":  data.get("transaction_id", "N/A"),
            "fraud_score":     final,
            "ml_score":        ml_score,
            "rules_boost":     boost,
            "decision":        decision,
            "decision_label":  label,
            "confidence":      "high" if abs(final - 50) > 25 else "medium",
            "triggered_rules": rules,
            "explanations":    expl[:6],
            "model_used":      self.model_name,
            "latency_ms":      None,

            # ── Bloc DSP2/SCA ─────────────────────────────────────────────
            # Indique si la transaction peut etre exemptee de SCA
            # conformement a l'Article 18 du RTS DSP2
            "dsp2_sca": {
                "sca_required":       not sca_exemption["eligible"],
                "exemption_eligible": sca_exemption["eligible"],
                "exemption_reason":   sca_exemption["reason"],
                "session_fraud_rate": sca_exemption["current_rate"],
                "regulation":         "RTS DSP2 Art. 18 - Reglement delegue UE 2018/389"
            }
        }

    # ─────────────────────────────────────────────────────────────────────────
    # METHODE PUBLIQUE : get_session_stats
    # Retourne les statistiques de session incluant le taux de fraude DSP2.
    # Utile pour le monitoring et l'endpoint GET /stats de l'API.
    # ─────────────────────────────────────────────────────────────────────────
    def get_session_stats(self):
        total = self._session_total_txn
        fraud = self._session_fraud_txn
        rate  = (fraud / total) if total > 0 else 0.0

        # Determine le niveau d'exemption DSP2 actuel
        dsp2_level = "Insufficient data (< 100 txn)"
        if total >= 100:
            dsp2_level = "No exemption (fraud rate too high)"
            for t in DSP2_SCA_THRESHOLDS:
                if rate < t["max_fraud_rate"]:
                    dsp2_level = (
                        f"Exemption up to {t['max_amount']} EUR "
                        f"(fraud rate {rate*100:.4f}% < {t['max_fraud_rate']*100:.2f}%)"
                    )
                    break

        return {
            "session_total_transactions": total,
            "session_fraud_blocks":       fraud,
            "session_fraud_rate":         round(rate, 6),
            "session_fraud_rate_pct":     f"{rate*100:.4f}%",
            "dsp2_exemption_level":       dsp2_level,
        }
