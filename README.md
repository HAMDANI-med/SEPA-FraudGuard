# 🛡️ SEPA FraudGuard

> Système de détection de fraude aux virements SEPA instantanés par Machine Learning — temps réel, < 100 ms

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-1.3+-orange?logo=scikit-learn&logoColor=white)
![AUC-ROC](https://img.shields.io/badge/AUC--ROC-1.000-brightgreen)
![Faux Positifs](https://img.shields.io/badge/Faux%20Positifs-0%25-brightgreen)
![Latence](https://img.shields.io/badge/Latence-88ms-blue)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## 📋 Table des matières

- [Problématique](#-problématique)
- [Présentation du projet](#-présentation-du-projet)
- [Architecture](#-architecture)
- [Dataset](#-dataset)
- [Features Engineering](#-features-engineering)
- [Modèles ML](#-modèles-ml)
- [Moteur de Scoring Hybride](#-moteur-de-scoring-hybride)
- [API REST](#-api-rest)
- [Conformité Réglementaire](#-conformité-réglementaire)
- [Installation](#-installation)
- [Lancement](#-lancement)
- [Démonstration](#-démonstration)
- [Structure du projet](#-structure-du-projet)


---

## ❓ Problématique

> **Comment détecter les fraudes SEPA instantanées en temps réel grâce au ML, tout en minimisant les faux positifs ?**

Les virements **SEPA SCT Inst.** s'exécutent en **moins de 10 secondes**, 24h/24, 7j/7. Une fois exécuté, un virement est quasi impossible à annuler. Les systèmes de règles fixes classiques ont deux problèmes :

- ❌ Trop lents pour le temps réel
- ❌ Trop de faux positifs — des clients légitimes bloqués

**L'enjeu est double : détecter la fraude ET ne pas gêner les clients honnêtes.**

---

## 🎯 Présentation du projet

SEPA FraudGuard est un système complet de détection de fraude bancaire. Il combine :

- Un pipeline **Machine Learning** (Random Forest + Gradient Boosting + Logistic Regression → Ensemble)
- Un moteur de **règles métier réglementaires** (DSP2, SEPA 2024/886, LCB-FT)
- Une **API REST** Python pure, opérationnelle en production

### Résultats obtenus

| Métrique | Valeur |
|----------|--------|
| AUC-ROC | **1.000** |
| Précision | **100%** |
| Rappel | **100%** |
| Faux Positifs | **0%** |
| Latence API | **~88 ms** |
| Transactions analysées | **51 500** |

---

## 🏗️ Architecture

Le système est organisé en **5 couches indépendantes** :

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   [1] Données          generate_dataset.py                  │
│        │                                                    │
│        ▼                                                    │
│   [2] Features         feature_engineering.py              │
│        │                                                    │
│        ▼                                                    │
│   [3] Modèles ML       train_model.py                      │
│        │                                                    │
│        ▼                                                    │
│   [4] Scoring Hybride  fraud_scorer.py                     │
│        │               ML (70%) + Règles (30%)             │
│        ▼                                                    │
│   [5] API REST         api.py  →  localhost:8000           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Chaque couche est indépendante — on peut améliorer le modèle ML sans toucher à l'API, et vice versa.

---

## 📊 Dataset

Dataset synthétique de **51 500 transactions SEPA** :

| Catégorie | Nombre | Pourcentage |
|-----------|--------|-------------|
| Transactions légitimes | 50 000 | 97.1% |
| Transactions frauduleuses | 1 500 | 2.9% |
| **Total** | **51 500** | **100%** |

### 4 patterns de fraude ciblés

| Pattern | Part |
|---------|------|
| Account Takeover — prise de contrôle de compte | 35% |
| Social Engineering — victime manipulée | 30% |
| Money Mule — blanchiment via intermédiaires | 20% |
| BEC — usurpation fournisseur | 15% |

> **Défi ML :** déséquilibre 97/3% → résolu avec `class_weight=balanced` (pénalise 17× plus les erreurs sur fraudes)

---

## ⚙️ Features Engineering

**33 variables construites** à partir des métadonnées brutes de chaque transaction :

| Catégorie | Features |
|-----------|----------|
| **Temporelles** | `is_night` · `is_weekend` · `time_risk_score` · `is_business_hours` |
| **Montant** | `amount_log` · `is_threshold_amount` · `amount_vs_avg_log` · `is_round_amount` |
| **Géographique** | `dst_is_high_risk` · `ip_country_match` · `is_cross_border` · `geo_risk_score` |
| **Device** | `device_risk` · `is_vpn` · `is_tor` · `device_is_new` · `session_is_short` |
| **Vélocité** | `nb_transactions_1h` · `nb_transactions_24h` · `velocity_risk` |
| **Compte** | `account_age_log` · `account_is_new` · `nb_beneficiaries_30d` · `is_new_beneficiary` |
| **Composite** | `composite_risk` (agrégation pondérée de tous les signaux) |

### Top features par importance (Random Forest)

```
amount_vs_avg_log       ████████████████████  19.9%
amount_ratio_to_avg     ███████████████████   18.4%
account_age_log         ██████████████        13.9%
is_new_beneficiary      ██████████            10.5%
amount_log              █████████              9.6%
composite_risk          █████████              9.5%
```

---

## 🤖 Modèles ML

### Comparaison des 4 modèles

| Modèle | AUC-ROC | Précision | Rappel | Faux Positifs | Faux Négatifs |
|--------|---------|-----------|--------|---------------|---------------|
| Logistic Regression | 1.000 | 100% | 100% | 0 | 0 |
| Random Forest | 1.000 | 100% | 99.3% | 0 | 2 |
| Gradient Boosting | 1.000 | 100% | 99.0% | 0 | 3 |
| **Ensemble (Champion)** | **1.000** | **100%** | **100%** | **0** | **0** |

### Pourquoi l'Ensemble est le Champion

L'Ensemble combine les 3 modèles par **soft voting pondéré** :

```
Random Forest       × 2  (poids double — robustesse)
Gradient Boosting   × 2  (poids double — performance)
Logistic Regression × 1  (poids simple — référence)
```

Seul l'Ensemble atteint **0 faux négatif ET 0 faux positif** simultanément.

### Optimisation du seuil — F-beta score (β=0.5)

> **Contribution méthodologique principale**

Le seuil de décision est optimisé par **F-beta score avec β=0.5**, qui pénalise **2× plus les faux positifs** que les faux négatifs. Choix délibéré : bloquer un client innocent est considéré deux fois plus grave que laisser passer une fraude.

```python
# Seuils optimisés par modèle
random_forest        → 0.34
gradient_boosting    → 0.10
logistic_regression  → 0.74
ensemble             → 0.28
```

---

## 🔢 Moteur de Scoring Hybride

### Formule

```
Score_final = min( Score_ML × 0.70  +  Boost_règles × 0.40 , 100 )
```

### Table de décision

| Score | Décision | Signification |
|-------|----------|---------------|
| 0 — 39 | ✅ **ALLOW** | Transaction autorisée automatiquement |
| 40 — 74 | ⚠️ **REVIEW** | Revue manuelle par un analyste |
| 75 — 100 | 🚫 **BLOCK** | Blocage immédiat |

> Une règle de sévérité `CRITICAL` force le **BLOCK** quel que soit le score ML.

### 9 règles métier

| # | Code | Boost | Sévérité | Déclencheur |
|---|------|-------|----------|-------------|
| 1 | `HIGH_AMOUNT` | +20 | high | Montant > 25 000 € (DSP2) |
| 2 | `HIGH_RISK_COUNTRY` | +25 | high | CY · BVI · MT · KY · HK... |
| 3 | `TOR_EXIT` | +40 | **critical** | Connexion réseau TOR |
| 4 | `VPN_DETECTED` | +15 | medium | IP masquée via VPN |
| 5 | `MULTIPLE_AUTH` | +20 | medium | ≥ 3 tentatives d'authentification |
| 6 | `VELOCITY_ANOMALY` | +30 | high | ≥ 3 virements/h + montant > 1 000 € |
| 7 | `NEW_BENE_HIGH` | +15 | medium | Nouveau bénéficiaire + montant > 5 000 € |
| 8 | `FRESH_ACCOUNT` | +25 | high | Compte < 7 jours + montant > 500 € |
| 9 | `IBAN_NAME_MISMATCH` | +50 | **critical** | Discordance IBAN/titulaire (Règl. UE 2024/886) |

> Le boost total est **plafonné à 40** pour éviter qu'une accumulation de règles mineures n'écrase le signal ML.

---

## 🌐 API REST

Serveur HTTP Python pur — aucun framework externe requis.

**Base URL :** `http://localhost:8000`

### Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/score` | Score une transaction → 0-100 + décision + règles + explications |
| `POST` | `/score/batch` | Batch jusqu'à 100 transactions |
| `GET` | `/health` | Status API + modèle chargé + uptime |
| `GET` | `/models` | Métriques AUC-ROC de chaque modèle |
| `GET` | `/stats` | Stats session + taux fraude DSP2 en temps réel |
| `GET` | `/` | Documentation + exemple de requête |

### Exemple de requête

```powershell
$body = '{"transaction_id":"TEST-001","amount_eur":14500,"source_country":"FR","destination_country":"CY","hour_of_day":3,"is_weekend":1,"is_night":1,"account_age_days":45,"is_new_beneficiary":1,"nb_transactions_1h":3,"nb_auth_attempts":4,"is_vpn":1,"is_tor":0,"iban_name_mismatch":0}'

Invoke-RestMethod -Uri "http://localhost:8000/score" -Method POST -ContentType "application/json" -Body $body
```

### Exemple de réponse

```json
{
  "transaction_id": "TEST-001",
  "fraud_score": 86.0,
  "ml_score": 100.0,
  "rules_boost": 40,
  "decision": "BLOCK",
  "decision_label": "Transaction bloquee",
  "confidence": "high",
  "triggered_rules": [
    {"code": "HIGH_RISK_COUNTRY", "severity": "high",   "score_boost": 25},
    {"code": "VPN_DETECTED",      "severity": "medium", "score_boost": 15},
    {"code": "MULTIPLE_AUTH",     "severity": "medium", "score_boost": 20},
    {"code": "VELOCITY_ANOMALY",  "severity": "high",   "score_boost": 30},
    {"code": "NEW_BENE_HIGH",     "severity": "medium", "score_boost": 15}
  ],
  "explanations": [
    "Destination pays a risque eleve",
    "Transaction hors heures habituelles",
    "Montant bien superieur a la moyenne du compte"
  ],
  "dsp2_sca": {
    "sca_required": true,
    "exemption_eligible": false,
    "session_fraud_rate": 0.0023,
    "regulation": "RTS DSP2 Art. 18 - Reglement delegue UE 2018/389"
  },
  "latency_ms": 88.03
}
```

---

## ⚖️ Conformité Réglementaire

| Règlement | Implémentation |
|-----------|----------------|
| **DSP2 / PSD2** | Surveillance renforcée > 25 000 € · Calcul taux fraude session · Exemption SCA (Art. 18 RTS) |
| **SEPA SCT Inst. — Règl. UE 2024/886** | Règle `IBAN_NAME_MISMATCH` (+50 pts, CRITICAL) — vérification IBAN/titulaire |
| **LCB-FT / TRACFIN** | Détection structuring (seuil 10 000 €) · Destinations offshore |
| **DORA** | Explications lisibles en langage naturel pour chaque décision |

---

## 💻 Installation

### Prérequis

- Python 3.10+
- pip

### Installation des dépendances

```powershell
pip install scikit-learn joblib numpy pandas
```

---

## 🚀 Lancement

### Étape 1 — Entraînement des modèles

```powershell
python train.py
```

Génère le dataset, entraîne les 4 modèles, sauvegarde les `.pkl` et `model_metadata.json`.

### Étape 2 — Lancement de l'API

```powershell
python api.py
```

```
=======================================================
  SEPA Fraud Detection API
  Serveur : http://localhost:8000
  Health  : http://localhost:8000/health
  Modele 'ensemble' charge (seuil: 0.28)
  Pret a scorer !
=======================================================
```

### Étape 3 — Démonstration sans API (optionnel)

```powershell
python demo_client.py
```

---

## 🎬 Démonstration

### Scénario 1 — Health Check
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health"
```

### Scénario 2 — Transaction légitime → ALLOW
```powershell
$body = '{"transaction_id":"DEMO-2","amount_eur":250,"source_country":"FR","destination_country":"FR","hour_of_day":14,"day_of_week":2,"is_weekend":0,"is_night":0,"account_age_days":730,"avg_monthly_transactions":15,"avg_monthly_amount":1200,"nb_beneficiaries_30d":6,"is_new_beneficiary":0,"nb_transactions_1h":0,"nb_transactions_24h":1,"amount_ratio_to_avg":0.9,"device_type":"mobile_ios","device_age_days":300,"session_duration_sec":180,"nb_auth_attempts":1,"ip_country_match":1,"is_vpn":0,"is_tor":0,"distance_km_from_usual":5,"iban_name_mismatch":0}'
Invoke-RestMethod -Uri "http://localhost:8000/score" -Method POST -ContentType "application/json" -Body $body
```

### Scénario 3 — Account Takeover → BLOCK
```powershell
$body = '{"transaction_id":"DEMO-3","amount_eur":14500,"source_country":"FR","destination_country":"CY","hour_of_day":3,"day_of_week":6,"is_weekend":1,"is_night":1,"account_age_days":45,"avg_monthly_transactions":8,"avg_monthly_amount":600,"nb_beneficiaries_30d":2,"is_new_beneficiary":1,"nb_transactions_1h":3,"nb_transactions_24h":4,"amount_ratio_to_avg":12.5,"device_type":"vpn_detected","device_age_days":2,"session_duration_sec":20,"nb_auth_attempts":4,"ip_country_match":0,"is_vpn":1,"is_tor":0,"distance_km_from_usual":2500,"iban_name_mismatch":0}'
Invoke-RestMethod -Uri "http://localhost:8000/score" -Method POST -ContentType "application/json" -Body $body
```

### Scénario 4 — TOR Exit → BLOCK critique
```powershell
$body = '{"transaction_id":"DEMO-4","amount_eur":14500,"source_country":"FR","destination_country":"CY","hour_of_day":3,"day_of_week":6,"is_weekend":1,"is_night":1,"account_age_days":45,"avg_monthly_transactions":8,"avg_monthly_amount":600,"nb_beneficiaries_30d":2,"is_new_beneficiary":1,"nb_transactions_1h":3,"nb_transactions_24h":4,"amount_ratio_to_avg":12.5,"device_type":"tor_exit","device_age_days":0,"session_duration_sec":8,"nb_auth_attempts":4,"ip_country_match":0,"is_vpn":0,"is_tor":1,"distance_km_from_usual":2500,"iban_name_mismatch":0}'
Invoke-RestMethod -Uri "http://localhost:8000/score" -Method POST -ContentType "application/json" -Body $body
```

### Scénario 5 — Cas borderline → REVIEW
```powershell
$body = '{"transaction_id":"DEMO-5","amount_eur":3200,"source_country":"FR","destination_country":"ES","hour_of_day":20,"day_of_week":4,"is_weekend":0,"is_night":0,"account_age_days":180,"avg_monthly_transactions":10,"avg_monthly_amount":800,"nb_beneficiaries_30d":3,"is_new_beneficiary":1,"nb_transactions_1h":0,"nb_transactions_24h":2,"amount_ratio_to_avg":2.5,"device_type":"mobile_android","device_age_days":90,"session_duration_sec":95,"nb_auth_attempts":2,"ip_country_match":1,"is_vpn":0,"is_tor":0,"distance_km_from_usual":350,"iban_name_mismatch":0}'
Invoke-RestMethod -Uri "http://localhost:8000/score" -Method POST -ContentType "application/json" -Body $body
```

### Scénario 6 — Métriques live
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/stats"
Invoke-RestMethod -Uri "http://localhost:8000/models"
```

### Bonus — IBAN_NAME_MISMATCH (Règl. UE 2024/886)
```powershell
$body = '{"transaction_id":"DEMO-IBAN","amount_eur":8500,"source_country":"FR","destination_country":"DE","hour_of_day":10,"day_of_week":2,"is_weekend":0,"is_night":0,"account_age_days":730,"avg_monthly_transactions":15,"avg_monthly_amount":1200,"nb_beneficiaries_30d":6,"is_new_beneficiary":0,"nb_transactions_1h":0,"nb_transactions_24h":1,"amount_ratio_to_avg":1.2,"device_type":"mobile_ios","device_age_days":300,"session_duration_sec":180,"nb_auth_attempts":1,"ip_country_match":1,"is_vpn":0,"is_tor":0,"distance_km_from_usual":5,"iban_name_mismatch":1}'
Invoke-RestMethod -Uri "http://localhost:8000/score" -Method POST -ContentType "application/json" -Body $body
```

---

## 📁 Structure du projet

```
projet cyber-finance/
│
├── train.py                  # Pipeline principal — dataset + entraînement
├── api.py                    # Serveur REST HTTP — port 8000
├── fraud_scorer.py           # Moteur de scoring hybride ML + règles
├── feature_engineering.py    # Construction des 33 features
├── train_model.py            # Entraînement des 4 modèles
├── generate_dataset.py       # Générateur dataset SEPA synthétique
├── demo_client.py            # Démonstration sans serveur
├── demo_nouveautes.py        # Démonstration IBAN_MISMATCH + DSP2
│
├── models/
│   ├── ensemble.pkl
│   ├── random_forest.pkl
│   ├── gradient_boosting.pkl
│   ├── logistic_regression.pkl
│   └── model_metadata.json
│
├── data/
│   └── (dataset généré par train.py)
│
└── README.md
```

---

## ⚡ Installation rapide (Windows)
double-cliquer sur INSTALL_WINDOWS.bat
# ou
powershell -ExecutionPolicy Bypass -File setup.ps1
