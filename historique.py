import json
import os
from datetime import date
from pnl import pnl_explain

FICHIER_HISTORIQUE = "historique.json"


def charger_historique():
    if not os.path.exists(FICHIER_HISTORIQUE):
        return []
    with open(FICHIER_HISTORIQUE, "r") as f:
        contenu = f.read()
        if not contenu.strip():
            return []
        return json.loads(contenu)


def sauvegarder_historique(historique):
    with open(FICHIER_HISTORIQUE, "w") as f:
        json.dump(historique, f, indent=2)


def enregistrer_snapshot(spot, delta, gamma, vega, theta, pnl_latent, pnl_realise):
    jour = str(date.today())
    entree = {
        "date": jour,
        "spot": float(spot),
        "delta": float(delta),
        "gamma": float(gamma),
        "vega": float(vega),
        "theta": float(theta),
        "pnl_latent": float(pnl_latent),
        "pnl_realise": float(pnl_realise),
        "pnl_total": float(pnl_latent) + float(pnl_realise),
    }
    historique = [e for e in charger_historique() if e["date"] != jour]
    historique.append(entree)
    sauvegarder_historique(historique)
    return entree

def expliquer_pnl(historique):
    """Pour chaque paire de snapshots consécutifs, explique la variation du P&L total."""
    historique = sorted(historique, key=lambda e: e["date"])
    lignes = []
    for avant, apres in zip(historique[:-1], historique[1:]):
        dS = apres["spot"] - avant["spot"]
        jours = (date.fromisoformat(apres["date"]) - date.fromisoformat(avant["date"])).days
        p_delta, p_gamma, _, p_theta, _ = pnl_explain(
            avant["delta"], avant["gamma"], avant["vega"], avant["theta"], dS, 0, jours)
        variation = apres["pnl_total"] - avant["pnl_total"]
        residu = variation - p_delta - p_gamma - p_theta
        lignes.append({
            "date": apres["date"],
            "variation": round(variation, 2),
            "delta": round(p_delta, 2),
            "gamma": round(p_gamma, 2),
            "theta": round(p_theta, 2),
            "residu": round(residu, 2),
        })
    return lignes