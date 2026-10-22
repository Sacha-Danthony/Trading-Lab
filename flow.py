import random

from clients import PROFILS
from config import TICKER
from config import TICKER, ECART_STRIKE_MAX

CLIENTS = list(PROFILS.keys())

from data import get_spot_price, get_maturites
from vol_surface import calculer_T


def filtrer_maturites(maturites, T_min=14 / 365, T_max=180 / 365):
    maturites_ok = []
    for date in maturites:
        T = calculer_T(date)
        if T_min <= T <= T_max:
            maturites_ok.append(date)
    return maturites_ok


def generer_rfq(ticker=TICKER):
    spot = get_spot_price(ticker)
    maturites = filtrer_maturites(get_maturites(ticker))

    rfq = {
        "type": random.choice(["call", "put"]),
        "strike": round(spot * random.uniform(0.9, 1.1), 0),
        "maturite": random.choice(maturites),
        "qty": random.randint(10, 300),
        "sens": random.choice(["achat", "vente"]),
    }
    return rfq


def generer_lot_rfq(ticker=TICKER, nb_min=3, nb_max=8):
    spot = get_spot_price(ticker)
    maturites_brutes = get_maturites(ticker)
    maturites = filtrer_maturites(maturites_brutes)

    nb_rfq = random.randint(nb_min, nb_max)
    lot = []

    for i in range(nb_rfq):
        client = random.choice(CLIENTS)
        profil = PROFILS[client]

        type_option = "put" if random.random() < profil["p_put"] else "call"
        sens = "achat" if random.random() < profil["p_achat"] else "vente"
        qty = random.randint(*profil["qty"])
        facteur_strike = random.uniform(1 - ECART_STRIKE_MAX, 1 + ECART_STRIKE_MAX)
        strike = round(spot * facteur_strike, 0)
        maturite = random.choice(maturites)

        rfq = {
            "id": i + 1,
            "type": type_option,
            "strike": strike,
            "maturite": maturite,
            "qty": qty,
            "sens": sens,
            "client": client
        }
        lot.append(rfq)

    return lot
