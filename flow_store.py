import json
import os
from datetime import date

from flow import generer_lot_rfq

FICHIER_FLOW = "flow.json"


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


def marquer_traitee(id_rfq, cotation, accepte):
    data = charger_lot()
    for rfq in data["lot"]:
        if rfq["id"] == id_rfq:
            rfq["traitee"] = True
            rfq["accepte"] = accepte
            rfq["bid"] = cotation["bid"]
            rfq["ask"] = cotation["ask"]
            rfq["mid"] = cotation["mid"]
    sauvegarder_lot(data)
