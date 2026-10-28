from book_greeks import delta_position, vega_position, valeur_modele, multiplicateur
from config import MULTIPLICATEUR_OPTION
from pnl import pnl_explain


# Limites dérivées d'un budget de perte : limite = budget de perte / taille du choc
BUDGET_PERTE_JOUR = 5000.0   # $ de perte maximale tolérée sur un choc
MOUVEMENT_SPOT = 5.0         # choc de spot de référence, en $ (TICKER)
MOUVEMENT_VOL = 5.0          # choc de vol de référence, en points de vol

LIMITE_DELTA = BUDGET_PERTE_JOUR / MOUVEMENT_SPOT   # nombre d'actions équivalentes max
LIMITE_VEGA = BUDGET_PERTE_JOUR / MOUVEMENT_VOL     # $ par point de vol max
MOUVEMENT_GAMMA = 15.0   # mouvement de spot de référence pour le gamma, en $ (≈ 2 % du SPY)
# perte gamma = ½ × |gamma| × mouvement²  →  on cherche le gamma qui fait perdre tout le budget
LIMITE_GAMMA = 2 * BUDGET_PERTE_JOUR / MOUVEMENT_GAMMA ** 2


def verifier_limites(total_delta, total_vega, total_gamma=0):
    alertes = []
    if abs(total_delta) > LIMITE_DELTA:
        alertes.append(f"Delta {round(total_delta, 1)} hors limite (±{round(LIMITE_DELTA)})")
    if abs(total_vega) > LIMITE_VEGA:
        alertes.append(f"Vega {round(total_vega, 1)} hors limite (±{round(LIMITE_VEGA)})")
    if total_gamma < -LIMITE_GAMMA:   # seul le gamma COURT est limité
        alertes.append(f"Gamma {round(total_gamma, 1)} : court gamma au-delà de la limite (−{round(LIMITE_GAMMA)})")
    return alertes


def risque_apres_trade(rfq, surface, spot, total_delta, total_vega, r=0.05):
    """Greeks du book si on exécute cette RFQ (contrôle pré-trade)."""
    # Si le client achète, tu vends : ta quantité est négative.
    qty_toi = -rfq["qty"] if rfq["sens"] == "achat" else rfq["qty"]
    position = {"type": rfq["type"], "strike": rfq["strike"],
                "maturite": rfq["maturite"], "qty": qty_toi}

    delta_apres = total_delta + delta_position(position, surface, r, spot) * position["qty"] * MULTIPLICATEUR_OPTION
    vega_apres = total_vega + vega_position(position, surface, r, spot) * position["qty"] * MULTIPLICATEUR_OPTION
    return delta_apres, vega_apres


SEUIL_HEDGE = 150  # delta (en actions) au-delà duquel on hedge

SEUIL_HEDGE_VEGA = LIMITE_VEGA / 2   # on commence à justifier un hedge à 50 % de la limite


def hedge_vega_necessaire(total_vega):
    return abs(total_vega) > SEUIL_HEDGE_VEGA


def hedge_necessaire(total_delta, seuil=SEUIL_HEDGE):
    return abs(total_delta) > seuil


def trade_bloque(delta_avant, vega_avant, delta_apres, vega_apres):
    """Bloque seulement si le trade dépasse une limite ET aggrave cette exposition."""
    messages = []
    if abs(delta_apres) > LIMITE_DELTA and abs(delta_apres) > abs(delta_avant):
        messages.append(f"Delta {round(delta_apres, 1)} dépasserait ±{round(LIMITE_DELTA)}")
    if abs(vega_apres) > LIMITE_VEGA and abs(vega_apres) > abs(vega_avant):
        messages.append(f"Vega {round(vega_apres, 1)} dépasserait ±{round(LIMITE_VEGA)}")
    return messages

def exposition_relative(delta, vega):
    return abs(delta) / LIMITE_DELTA + abs(vega) / LIMITE_VEGA

def skew_suggere(rfq, total_delta, total_vega, delta_apres, vega_apres, k=0.03, cap=0.01):
    variation = exposition_relative(delta_apres, vega_apres) - exposition_relative(total_delta, total_vega)
    signe = 1 if rfq["sens"] == "achat" else -1
    return signe * max(-cap, min(cap, k * variation))

CHOC_STRESS_SPOT = 0.05          # choc de spot : ±5 %
CHOC_STRESS_VOL = 5.0            # choc de vol : ±5 points
LIMITE_STRESS = 3 * BUDGET_PERTE_JOUR   # perte maximale tolérée en scénario extrême


def pire_scenario(total_delta, total_gamma, total_vega, total_theta, spot):
    """Teste les 4 combinaisons de choc spot / vol et renvoie la pire : (pnl, choc_spot, choc_vol)."""
    pire = None
    for choc_spot in (-CHOC_STRESS_SPOT, CHOC_STRESS_SPOT):
        for choc_vol in (-CHOC_STRESS_VOL, CHOC_STRESS_VOL):
            pnl = pnl_explain(total_delta, total_gamma, total_vega, total_theta,
                              choc_spot * spot, choc_vol, 0)[4]
            if pire is None or pnl < pire[0]:
                pire = (pnl, choc_spot, choc_vol)
    return pire

def grille_stress(total_delta, total_gamma, total_vega, total_theta, spot,
                  chocs_spot=(-0.10, -0.05, 0.0, 0.05, 0.10), chocs_vol=(-5, 0, 5, 15)):
    """P&L du book pour chaque combinaison de choc spot (en %) et de choc vol (en points)."""
    grille = {}
    for choc_vol in chocs_vol:
        ligne = {}
        for choc_spot in chocs_spot:
            pnl = pnl_explain(total_delta, total_gamma, total_vega, total_theta,
                              choc_spot * spot, choc_vol, 0)[4]
            ligne[f"{choc_spot:+.0%}"] = pnl
        grille[f"vol {choc_vol:+d} pts"] = ligne
    return grille

def grille_stress_complete(book, surface, spot, r,
                           chocs_spot=(-0.10, -0.05, 0.0, 0.05, 0.10), chocs_vol=(-5, 0, 5, 15)):
    """P&L du book par revalorisation complète : chaque option est repricée avec le spot et la vol choqués."""
    valeur_actuelle = sum(valeur_modele(p, surface, r, spot) * p["qty"] * multiplicateur(p) for p in book)
    grille = {}
    for choc_vol in chocs_vol:
        ligne = {}
        for choc_spot in chocs_spot:
            spot_choque = spot * (1 + choc_spot)
            valeur_choquee = sum(valeur_modele(p, surface, r, spot_choque, choc_vol=choc_vol) * p["qty"] * multiplicateur(p) for p in book)
            ligne[f"{choc_spot:+.0%}"] = valeur_choquee - valeur_actuelle
        grille[f"vol {choc_vol:+d} pts"] = ligne
    return grille