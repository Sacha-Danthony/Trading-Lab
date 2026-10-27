import json
import os
from datetime import date

from flow import generer_lot_rfq

FICHIER_FLOW = "flow.json"
FICHIER_HISTO_RFQ = "rfq_historique.json"


def charger_lot():
    if not os.path.exists(FICHIER_FLOW):
        return None
    with open(FICHIER_FLOW, "r") as f:
        contenu = f.read()
        if not contenu.strip():
            return None
        return json.loads(contenu)


def sauvegarder_lot(lot_data):
    with open(FICHIER_FLOW, "w") as f:
        json.dump(lot_data, f, indent=2)


def obtenir_lot_du_jour():
    """Un seul lot de RFQ par jour : si déjà généré aujourd'hui, on le recharge."""
    data = charger_lot()
    aujourdhui = str(date.today())

    if data is not None and data["date"] == aujourdhui:
        return data["lot"]

    nouveau_lot = generer_lot_rfq()
    data = {"date": aujourdhui, "lot": nouveau_lot}
    sauvegarder_lot(data)
    return nouveau_lot


def charger_historique_rfq():
    if not os.path.exists(FICHIER_HISTO_RFQ):
        return []
    with open(FICHIER_HISTO_RFQ, "r") as f:
        contenu = f.read()
        if not contenu.strip():
            return []
        return json.loads(contenu)


def enregistrer_rfq_traitee(rfq, cotation, accepte):
    historique = charger_historique_rfq()
    ligne = {
        "date": str(date.today()),
        "id": rfq["id"],
        "client": rfq.get("client", "?"),
        "type": rfq["type"],
        "strike": rfq["strike"],
        "qty": rfq["qty"],
        "sens": rfq["sens"],
        "bid": cotation["bid"],
        "ask": cotation["ask"],
        "mid": cotation["mid"],
        "accepte": accepte,
    }
    historique.append(ligne)
    with open(FICHIER_HISTO_RFQ, "w") as f:
        json.dump(historique, f, indent=2)

def stats_rfq(historique):
    stats = {}
    for ligne in historique:
        client = ligne["client"]
        if client not in stats:
            stats[client] = {"n": 0, "acceptees": 0, "spread_total": 0.0}
        stats[client]["n"] += 1                         
        if ligne["accepte"]:
            stats[client]["acceptees"] += 1              
        spread = (ligne["ask"] - ligne["bid"]) / ligne["mid"]      
        stats[client]["spread_total"] += spread             
    return stats

def marquer_traitee(id_rfq, cotation, accepte):
    data = charger_lot()
    for rfq in data["lot"]:
        if rfq["id"] == id_rfq:
            rfq["traitee"] = True
            rfq["accepte"] = accepte
            rfq["bid"] = cotation["bid"]
            rfq["ask"] = cotation["ask"]
            rfq["mid"] = cotation["mid"]
            enregistrer_rfq_traitee(rfq, cotation, accepte)
    sauvegarder_lot(data)
