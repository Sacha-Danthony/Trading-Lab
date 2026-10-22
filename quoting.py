import random
from datetime import date

from clients import PROFILS, SEUIL_DEFAUT
from Pricing import prix_call, prix_put
from data import get_spot_price, get_prix_marche
from vol_surface import calculer_T, get_vol
from book_store import ajouter_position
from config import TICKER


def prix_mid(rfq, surface, r=0.05):
    """Mid de référence : mid du marché réel si dispo, sinon prix du modèle sur la surface."""
    mid_marche = get_prix_marche(TICKER, rfq["maturite"], rfq["strike"], rfq["type"])
    if mid_marche is not None:
        return mid_marche

    S = get_spot_price(TICKER)
    T = calculer_T(rfq["maturite"])
    sigma = get_vol(K=rfq["strike"], T=T, surface=surface)

    if rfq["type"] == "call":
        mid = prix_call(S=S, K=rfq["strike"], T=T, r=r, sigma=sigma)
    else:
        mid = prix_put(S=S, K=rfq["strike"], T=T, r=r, sigma=sigma)

    return mid


def coter(rfq, surface, r=0.05, spread=0.05, skew=0.0):
    """spread = largeur bid/ask ; skew = décale les deux côtés dans le même sens (selon ton inventaire)."""
    mid = prix_mid(rfq, surface, r)

    bid = mid * (1 - spread / 2) * (1 + skew)
    ask = mid * (1 + spread / 2) * (1 + skew)

    return {"mid": float(mid), "bid": float(bid), "ask": float(ask)}


def proba_acceptation(rfq, cotation, seuil=None):
    """Renvoie (proba, ecart, seuil) : la proba d'acceptation et ce qui l'explique."""
    if seuil is None:
        seuil = PROFILS.get(rfq.get("client"), {}).get("seuil", SEUIL_DEFAUT)
    mid = cotation["mid"]
    if rfq["sens"] == "achat":
        ecart = (cotation["ask"] - mid) / mid
    else:
        ecart = (mid - cotation["bid"]) / mid

    if ecart <= 0:
        proba = 0.95
    elif ecart <= seuil:
        proba = 0.95 - (ecart / seuil) * 0.45
    else:
        proba = 0.10

    return proba, ecart, seuil


def decision_client(rfq, cotation, seuil=None):
    """Le client accepte avec une proba qui chute quand ton prix s'éloigne du mid."""
    proba, _, _ = proba_acceptation(rfq, cotation, seuil)
    return bool(random.random() < proba)

def explication(rfq, cotation, accepte, detail=False, seuil=None):
    proba, ecart, seuil = proba_acceptation(rfq, cotation, seuil)
    if accepte:
        msg = "Exécutée."
    elif ecart > seuil:
        msg = "Refusée : le client juge ton prix trop large."
    else:
        msg = "Refusée : le client est allé voir ailleurs."
    if detail:
        msg += f" [écart {ecart:.1%} du mid, seuil {seuil:.1%}, acceptation estimée {round(proba * 100)} %]"
    return msg


def executer_rfq(rfq, cotation, spot=None):
    if rfq["sens"] == "achat":
        prix_execution = cotation["ask"]
        qty_toi = -rfq["qty"]
    else:
        prix_execution = cotation["bid"]
        qty_toi = rfq["qty"]

    position = ajouter_position(
        type_option=rfq["type"],
        strike=rfq["strike"],
        maturite=rfq["maturite"],
        qty=qty_toi,
        prix_entree=prix_execution,
        date_entree=str(date.today()),
        client=rfq.get("client"),
        mid_entree=cotation["mid"],
        spot_entree=spot,
    )
    return position


def traiter_lot(lot, surface):
    resultats = []

    for rfq in lot:
        cotation = coter(rfq, surface)
        accepte = decision_client(rfq, cotation)

        if accepte:
            position = executer_rfq(rfq, cotation)
        else:
            position = None

        resultats.append({
            "rfq": rfq,
            "cotation": cotation,
            "accepte": accepte,
            "position": position
        })

    return resultats
