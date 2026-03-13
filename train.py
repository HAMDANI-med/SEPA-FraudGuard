#!/usr/bin/env python3
"""
Pipeline SEPA Fraud Detection - Windows compatible
Usage:
  python train.py        -> Dataset + entrainement
  python train.py --api  -> + demarre l'API
  python train.py --test -> + lance les tests
"""

import sys, os, importlib.util

# === Fix absolu : on se place TOUJOURS dans le dossier du script ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

def import_from_file(module_name, filepath):
    """Importe un module Python directement depuis son chemin — bypass les problemes de packages."""
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

def step(msg):
    print(f"\n{'─'*60}\n  {msg}\n{'─'*60}")

def run_pipeline(with_tests=False, start_api=False):
    print("\n" + "="*60)
    print("  SEPA Fraud Detection - Pipeline ML")
    print("  Module Cyber Finance")
    print("="*60)

    # ETAPE 1 : Dataset
    step("ETAPE 1/2 : Generation du dataset synthetique SEPA")
    gen = import_from_file("generate_dataset", os.path.join(BASE_DIR, "data", "generate_dataset.py"))
    gen.build_dataset()

    # ETAPE 2 : Entrainement
    step("ETAPE 2/2 : Entrainement des modeles ML")

    # Pre-charger feature_engineering avant train_model
    import_from_file("feature_engineering",
                     os.path.join(BASE_DIR, "models", "feature_engineering.py"))
    # Rendre disponible sous models.feature_engineering aussi
    sys.modules["models.feature_engineering"] = sys.modules["feature_engineering"]

    train_mod = import_from_file("train_model",
                                  os.path.join(BASE_DIR, "models", "train_model.py"))
    meta = train_mod.train()

    c = meta["metrics"]["ensemble"]
    print(f"""
  Modele champion (Ensemble) :
    AUC-ROC       : {c['auc_roc']:.4f}
    Precision     : {c['precision']*100:.2f}%
    Rappel        : {c['recall']*100:.2f}%
    F1-Score      : {c['f1']:.4f}
    Faux Positifs : {c['false_positive_rate']*100:.2f}%
    Seuil optimal : {c['threshold']:.2f}
    """)

    if with_tests:
        step("Tests")
        import subprocess
        subprocess.run([sys.executable,
                        os.path.join(BASE_DIR, "tests", "test_fraud_api.py")])

    if start_api:
        step("Demarrage API REST sur http://localhost:8000")
        api_mod = import_from_file("api", os.path.join(BASE_DIR, "api.py"))
        api_mod.run()
    else:
        print(f"""
{'='*60}
  Pipeline termine !

  Prochaines etapes :
    python demo_client.py           -> Demo scoring
    python api.py                   -> API sur localhost:8000
    python tests/test_fraud_api.py  -> Tests
{'='*60}
        """)

if __name__ == "__main__":
    args = sys.argv[1:]
    run_pipeline(
        with_tests="--test" in args or "--all" in args,
        start_api="--api"  in args or "--all" in args,
    )
