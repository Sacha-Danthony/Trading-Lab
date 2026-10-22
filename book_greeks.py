from Pricing import delta_call, delta_put, gamma, vega, theta_call, theta_put, prix_call, prix_put
from data import get_prix_marche
from vol_surface import calculer_T, get_vol
from config import TICKER
from config import MULTIPLICATEUR_OPTION


def multiplicateur(position):
    return 1 if position["type"] == "stock" else MULTIPLICATEUR_OPTION

def delta_position(position, surface, r, S):
    if position["type"] == "call":
        T = calculer_T(position["maturite"])
        sigma = get_vol(K=position["strike"], T=T, surface=surface)
        d = delta_call(S=S, K=position["strike"], T=T, r=r, sigma=sigma)
    elif position["type"] == "put":
        T = calculer_T(position["maturite"])
        sigma = get_vol(K=position["strike"], T=T, surface=surface)
        d = delta_put(S=S, K=position["strike"], T=T, r=r, sigma=sigma)
    else:
        d = 1
    return d


def gamma_position(position, surface, r, S):
    if position["type"] == "stock":
        g = 0
    else:
        T = calculer_T(position["maturite"])
        sigma = get_vol(K=position["strike"], T=T, surface=surface)
        g = gamma(S=S, K=position["strike"], T=T, r=r, sigma=sigma)
    return g


def vega_position(position, surface, r, S):
    if position["type"] == "stock":
        v = 0
    else:
        T = calculer_T(position["maturite"])
        sigma = get_vol(K=position["strike"], T=T, surface=surface)
        v = vega(S=S, K=position["strike"], T=T, r=r, sigma=sigma)
    return v


def theta_position(position, surface, r, S):
    if position["type"] == "call":
        T = calculer_T(position["maturite"])
        sigma = get_vol(K=position["strike"], T=T, surface=surface)
        t = theta_call(S=S, K=position["strike"], T=T, r=r, sigma=sigma)
    elif position["type"] == "put":
        T = calculer_T(position["maturite"])
        sigma = get_vol(K=position["strike"], T=T, surface=surface)
        t = theta_put(S=S, K=position["strike"], T=T, r=r, sigma=sigma)
    else:
        t = 0
    return t


def valeur_position(position, surface, r, S):
    # D'abord le mid du marché ; sinon le modèle (Black-Scholes + vol de la surface)
    if position["type"] in ("call", "put"):
        mid_marche = get_prix_marche(TICKER, position["maturite"], position["strike"], position["type"])
        if mid_marche is not None:
            return mid_marche

    if position["type"] == "call":
        T = calculer_T(position["maturite"])
        sigma = get_vol(K=position["strike"], T=T, surface=surface)
        v = prix_call(S=S, K=position["strike"], T=T, r=r, sigma=sigma)
    elif position["type"] == "put":
        T = calculer_T(position["maturite"])
        sigma = get_vol(K=position["strike"], T=T, surface=surface)
        v = prix_put(S=S, K=position["strike"], T=T, r=r, sigma=sigma)
    else:
        v = S
    return v


def delta_net_book(book, surface, r, S):
    total = 0
    for position in book:
       total = total + delta_position(position, surface, r, S) * position["qty"] * multiplicateur(position)
    return total


def gamma_net_book(book, surface, r, S):
    total = 0
    for position in book:
       total = total + gamma_position(position, surface, r, S) * position["qty"] * multiplicateur(position)
    return total


def vega_net_book(book, surface, r, S):
    total = 0
    for position in book:
        total = total + vega_position(position, surface, r, S) * position["qty"] * multiplicateur(position)
    return total


def theta_net_book(book, surface, r, S):
    total = 0
    for position in book:
        total = total + theta_position(position, surface, r, S) * position["qty"] * multiplicateur(position)
    return total


def valeur_net_book(book, surface, r, S):
    total = 0
    for position in book:
        total = total + valeur_position(position, surface, r, S) * position["qty"] * multiplicateur(position)
    return total


def hedge_delta(delta_net):
    """Nombre d'actions à acheter (+) ou vendre (-) pour ramener le delta à zéro."""
    return -delta_net
