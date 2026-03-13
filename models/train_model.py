"""
Entraînement du modèle de détection de fraude SEPA.
Ensemble : Random Forest + Gradient Boosting (simulant XGBoost)
Stratégie anti-faux-positifs : optimisation du seuil par F-beta score (beta < 1)
"""

import os
import sys
import json
import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score,
    precision_recall_curve, f1_score, fbeta_score, average_precision_score
)
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.utils.class_weight import compute_class_weight

import importlib.util as _ilu
def _load_fe():
    if "feature_engineering" in sys.modules:
        return sys.modules["feature_engineering"]
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feature_engineering.py")
    _s = _ilu.spec_from_file_location("feature_engineering", _p)
    _m = _ilu.module_from_spec(_s)
    sys.modules["feature_engineering"] = _m
    sys.modules["models.feature_engineering"] = _m
    _s.loader.exec_module(_m)
    return _m
_fe = _load_fe()
engineer_features = _fe.engineer_features
get_feature_columns = _fe.get_feature_columns

MODELS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(os.path.dirname(MODELS_DIR), "data", "sepa_transactions.csv")


def load_and_prepare():
    print("📂 Chargement du dataset...")
    df = pd.read_csv(DATA_PATH)
    print(f"   ✓ {len(df)} transactions chargées")

    df = engineer_features(df)
    features = get_feature_columns()
    X = df[features]
    y = df["is_fraud"]

    print(f"   ✓ {len(features)} features utilisées")
    print(f"   ✓ Fraudes : {y.sum()} ({y.mean()*100:.2f}%)")
    return X, y, features


def find_optimal_threshold(model, X_val, y_val, beta=0.5):
    """
    Trouve le seuil optimal en maximisant F-beta score.
    beta < 1 : pénalise davantage les faux positifs (priorité précision).
    beta > 1 : pénalise davantage les faux négatifs (priorité rappel).
    Pour une banque : beta=0.5 (minimiser faux positifs = meilleure UX).
    """
    proba = model.predict_proba(X_val)[:, 1]
    thresholds = np.arange(0.1, 0.9, 0.01)
    best_thresh, best_score = 0.5, 0

    for t in thresholds:
        preds = (proba >= t).astype(int)
        score = fbeta_score(y_val, preds, beta=beta, zero_division=0)
        if score > best_score:
            best_score = score
            best_thresh = t

    return best_thresh, best_score


def evaluate_model(model, X_test, y_test, threshold, name="Modèle"):
    proba = model.predict_proba(X_test)[:, 1]
    preds = (proba >= threshold).astype(int)

    cm = confusion_matrix(y_test, preds)
    tn, fp, fn, tp = cm.ravel()
    auc = roc_auc_score(y_test, proba)
    ap = average_precision_score(y_test, proba)

    print(f"\n{'='*55}")
    print(f"📊 {name}")
    print(f"{'='*55}")
    print(f"  Seuil optimal (F-beta 0.5)  : {threshold:.2f}")
    print(f"  AUC-ROC                      : {auc:.4f}")
    print(f"  AUC-PR (Avg Precision)       : {ap:.4f}")
    print(f"  {'─'*40}")
    print(f"  Vrais Positifs  (TP)         : {tp}")
    print(f"  Faux Positifs   (FP)         : {fp}  ← minimiser")
    print(f"  Vrais Négatifs  (TN)         : {tn}")
    print(f"  Faux Négatifs   (FN)         : {fn}")
    print(f"  {'─'*40}")
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec  = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    fpr  = fp / (fp + tn) if (fp + tn) > 0 else 0
    print(f"  Précision                    : {prec*100:.2f}%")
    print(f"  Rappel (Recall)              : {rec*100:.2f}%")
    print(f"  F1-Score                     : {f1:.4f}")
    print(f"  Taux Faux Positifs           : {fpr*100:.2f}%")

    return {
        "auc_roc": round(auc, 4),
        "auc_pr": round(ap, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(fpr, 4),
        "threshold": round(threshold, 3),
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
    }


def train():
    X, y, features = load_and_prepare()

    # Split stratifié
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.15, random_state=42, stratify=y_train
    )

    print(f"\n📦 Split dataset :")
    print(f"   Train : {len(X_train)} | Val : {len(X_val)} | Test : {len(X_test)}")

    # Poids de classe pour gérer le déséquilibre
    classes = np.array([0, 1])
    weights = compute_class_weight("balanced", classes=classes, y=y_train)
    class_weight = {0: weights[0], 1: weights[1]}
    print(f"   Poids classe fraude : {weights[1]:.2f}x (SMOTE-like balancing)")

    # ─────────────────────────────────────────────────────────────
    # Modèle 1 : Random Forest
    # ─────────────────────────────────────────────────────────────
    print("\n🌲 Entraînement Random Forest...")
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=5,
        max_features="sqrt",
        class_weight=class_weight,
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    rf_thresh, _ = find_optimal_threshold(rf, X_val, y_val, beta=0.5)
    rf_metrics = evaluate_model(rf, X_test, y_test, rf_thresh, "Random Forest")

    # ─────────────────────────────────────────────────────────────
    # Modèle 2 : Gradient Boosting (≈ XGBoost behavior)
    # ─────────────────────────────────────────────────────────────
    print("\n🚀 Entraînement Gradient Boosting (XGBoost-like)...")
    gb = GradientBoostingClassifier(
        n_estimators=200,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        min_samples_leaf=10,
        random_state=42,
    )
    gb.fit(X_train, y_train)
    gb_thresh, _ = find_optimal_threshold(gb, X_val, y_val, beta=0.5)
    gb_metrics = evaluate_model(gb, X_test, y_test, gb_thresh, "Gradient Boosting")

    # ─────────────────────────────────────────────────────────────
    # Modèle 3 : Logistic Regression (baseline)
    # ─────────────────────────────────────────────────────────────
    print("\n📈 Entraînement Logistic Regression (baseline)...")
    lr_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(class_weight=class_weight, max_iter=1000, C=0.1, random_state=42))
    ])
    lr_pipe.fit(X_train, y_train)
    lr_thresh, _ = find_optimal_threshold(lr_pipe, X_val, y_val, beta=0.5)
    lr_metrics = evaluate_model(lr_pipe, X_test, y_test, lr_thresh, "Logistic Regression")

    # ─────────────────────────────────────────────────────────────
    # Ensemble soft voting (RF + GB) — meilleur des deux mondes
    # ─────────────────────────────────────────────────────────────
    print("\n⚡ Entraînement Ensemble (RF + GB + LR soft voting)...")
    ensemble = VotingClassifier(
        estimators=[("rf", rf), ("gb", gb), ("lr", lr_pipe)],
        voting="soft",
        weights=[2, 2, 1],
    )
    ensemble.fit(X_train, y_train)
    ens_thresh, _ = find_optimal_threshold(ensemble, X_val, y_val, beta=0.5)
    ens_metrics = evaluate_model(ensemble, X_test, y_test, ens_thresh, "Ensemble (RF+GB+LR)")

    # ─────────────────────────────────────────────────────────────
    # Feature importance (Random Forest)
    # ─────────────────────────────────────────────────────────────
    print("\n🔍 Top 15 features (Random Forest importance) :")
    fi = pd.Series(rf.feature_importances_, index=features).sort_values(ascending=False)
    for feat, imp in fi.head(15).items():
        bar = "█" * int(imp * 100)
        print(f"   {feat:<35} {bar} {imp:.4f}")

    # ─────────────────────────────────────────────────────────────
    # Sauvegarde
    # ─────────────────────────────────────────────────────────────
    print("\n💾 Sauvegarde des modèles...")
    joblib.dump(rf, os.path.join(MODELS_DIR, "random_forest.pkl"))
    joblib.dump(gb, os.path.join(MODELS_DIR, "gradient_boosting.pkl"))
    joblib.dump(lr_pipe, os.path.join(MODELS_DIR, "logistic_regression.pkl"))
    joblib.dump(ensemble, os.path.join(MODELS_DIR, "ensemble.pkl"))

    meta = {
        "features": features,
        "thresholds": {
            "random_forest": rf_thresh,
            "gradient_boosting": gb_thresh,
            "logistic_regression": lr_thresh,
            "ensemble": ens_thresh,
        },
        "metrics": {
            "random_forest": rf_metrics,
            "gradient_boosting": gb_metrics,
            "logistic_regression": lr_metrics,
            "ensemble": ens_metrics,
        },
        "feature_importance": fi.to_dict(),
        "training_samples": len(X_train),
        "test_samples": len(X_test),
    }
    with open(os.path.join(MODELS_DIR, "model_metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print("\n✅ Entraînement terminé !")
    print(f"   └─ Modèle champion : Ensemble | AUC-ROC: {ens_metrics['auc_roc']} | FP rate: {ens_metrics['false_positive_rate']*100:.1f}%")
    print(f"   └─ Fichiers sauvegardés dans : {MODELS_DIR}")
    return meta


if __name__ == "__main__":
    train()
