#!/usr/bin/env python3
"""
API REST SEPA Fraud Detection - Port 8000
Endpoints: POST /score  POST /score/batch  GET /health  GET /models  GET /stats  GET /
"""

import json, time, os, sys, traceback, importlib.util
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

def _load(name, path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# Pre-charger les dependances dans le bon ordre
_load("feature_engineering", os.path.join(BASE_DIR, "models", "feature_engineering.py"))
sys.modules["models.feature_engineering"] = sys.modules["feature_engineering"]
fraud_scorer_mod = _load("fraud_scorer", os.path.join(BASE_DIR, "fraud_scorer.py"))
FraudScorer = fraud_scorer_mod.FraudScorer

PORT = 8000
scorer_cache = {}
session_stats = {"requests":0,"blocked":0,"reviewed":0,"allowed":0,
                 "total_latency_ms":0,"start_time":time.time()}

def get_scorer(model="ensemble"):
    if model not in scorer_cache:
        scorer_cache[model] = FraudScorer(model)
    return scorer_cache[model]

def json_resp(h, data, status=200):
    body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type","application/json; charset=utf-8")
    h.send_header("Content-Length", len(body))
    h.send_header("Access-Control-Allow-Origin","*")
    h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
    h.send_header("Access-Control-Allow-Headers","Content-Type")
    h.end_headers()
    h.wfile.write(body)

def read_body(h):
    try:
        n = int(h.headers.get("Content-Length", 0))
        return json.loads(h.rfile.read(n)) if n else {}
    except:
        return None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        print(f"  [{time.strftime('%H:%M:%S')}] {fmt % a}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if   p == "/health": self._health()
        elif p == "/models": self._models()
        elif p == "/stats":  self._stats()
        elif p in ("/","/docs"): self._docs()
        else: json_resp(self, {"error":"Not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        if   p == "/score":       self._score()
        elif p == "/score/batch": self._batch()
        else: json_resp(self, {"error":"Not found"}, 404)

    def _health(self):
        json_resp(self, {"status":"ok","service":"SEPA Fraud API","version":"2.4",
                         "models_loaded":list(scorer_cache.keys()),
                         "uptime_seconds":round(time.time()-session_stats["start_time"],1)})

    def _models(self):
        meta_path = os.path.join(BASE_DIR,"models","model_metadata.json")
        if not os.path.exists(meta_path):
            json_resp(self,{"error":"Modeles non entraines. Lancez train.py"},503); return
        with open(meta_path) as f: meta=json.load(f)
        json_resp(self,{"available_models":["ensemble","random_forest","gradient_boosting",
                         "logistic_regression"],"default":"ensemble",
                        "metrics":meta.get("metrics",{}),"thresholds":meta.get("thresholds",{})})

    def _stats(self):
        up = time.time()-session_stats["start_time"]
        avg = session_stats["total_latency_ms"]/max(session_stats["requests"],1)
        json_resp(self,{"session_requests":session_stats["requests"],
                        "decisions":{"BLOCK":session_stats["blocked"],
                                     "REVIEW":session_stats["reviewed"],
                                     "ALLOW":session_stats["allowed"]},
                        "avg_latency_ms":round(avg,2),"uptime_seconds":round(up,1)})

    def _score(self):
        data = read_body(self)
        if data is None: json_resp(self,{"error":"JSON invalide"},400); return
        model = data.pop("model","ensemble")
        try: sc = get_scorer(model)
        except FileNotFoundError as e: json_resp(self,{"error":str(e)},503); return
        t0 = time.perf_counter()
        try: result = sc.score(data)
        except Exception as e: json_resp(self,{"error":str(e)},500); traceback.print_exc(); return
        lat = round((time.perf_counter()-t0)*1000,2)
        result["latency_ms"] = lat
        session_stats["requests"] += 1
        session_stats["total_latency_ms"] += lat
        session_stats[{"BLOCK":"blocked","REVIEW":"reviewed","ALLOW":"allowed"}[result["decision"]]] += 1
        json_resp(self, result)

    def _batch(self):
        data = read_body(self)
        if not isinstance(data,list): json_resp(self,{"error":"Array JSON requis"},400); return
        if len(data)>100: json_resp(self,{"error":"Max 100 par batch"},400); return
        try: sc = get_scorer("ensemble")
        except FileNotFoundError as e: json_resp(self,{"error":str(e)},503); return
        t0=time.perf_counter(); results=[]
        for txn in data:
            if isinstance(txn,dict):
                txn.pop("model",None)
                try: results.append(sc.score(txn))
                except Exception as e: results.append({"error":str(e)})
        lat=round((time.perf_counter()-t0)*1000,2)
        bl=sum(1 for r in results if r.get("decision")=="BLOCK")
        rv=sum(1 for r in results if r.get("decision")=="REVIEW")
        session_stats["requests"]+=len(results); session_stats["blocked"]+=bl
        session_stats["reviewed"]+=rv; session_stats["allowed"]+=len(results)-bl-rv
        session_stats["total_latency_ms"]+=lat
        json_resp(self,{"count":len(results),"total_latency_ms":lat,
                        "summary":{"BLOCK":bl,"REVIEW":rv,"ALLOW":len(results)-bl-rv},
                        "results":results})

    def _docs(self):
        json_resp(self,{"service":"SEPA Fraud Detection API","version":"2.4",
            "endpoints":{"POST /score":"Score une transaction",
                         "POST /score/batch":"Batch max 100 TXN",
                         "GET /health":"Health check","GET /models":"Metriques modeles",
                         "GET /stats":"Stats session"},
            "example_input":{"transaction_id":"TXN-001","amount_eur":14500,
                "source_country":"FR","destination_country":"CY",
                "hour_of_day":3,"day_of_week":6,"is_weekend":1,"is_night":1,
                "account_age_days":30,"avg_monthly_transactions":5,"avg_monthly_amount":400,
                "nb_beneficiaries_30d":1,"is_new_beneficiary":1,"nb_transactions_1h":3,
                "nb_transactions_24h":5,"amount_ratio_to_avg":14.8,"device_type":"vpn_detected",
                "device_age_days":1,"session_duration_sec":18,"nb_auth_attempts":4,
                "ip_country_match":0,"is_vpn":1,"is_tor":0,"distance_km_from_usual":2200}})

def run(port=PORT):
    print("\n"+"="*55)
    print("  SEPA Fraud Detection API")
    print(f"  Serveur : http://localhost:{port}")
    print(f"  Docs    : http://localhost:{port}/")
    print(f"  Health  : http://localhost:{port}/health")
    print("  Chargement du modele...")
    try:
        get_scorer("ensemble")
        print("  Modele charge - pret a scorer !")
    except FileNotFoundError:
        print("  ATTENTION: lancez d'abord train.py")
    print("="*55+"\n")
    srv = HTTPServer(("0.0.0.0", port), Handler)
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nServeur arrete."); srv.server_close()

if __name__ == "__main__":
    run()
