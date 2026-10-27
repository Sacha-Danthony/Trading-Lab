import json
import os
import numpy as np
import matplotlib.pyplot as plt
import math
from datetime import datetime, date
from Pricing import prix_call, vega
from data import get_spot_price, get_option_chain, filtrer_options, get_maturites
from config import TICKER


FICHIER_SURFACE = "surface.json"


def calculer_T(date_echeance):
    jours = (datetime.strptime(date_echeance, "%Y-%m-%d").date() - date.today()).days
    return max(jours, 0.5) / 365   # le jour de l'échéance, on compte une demi-journée restante


def vol_implicite_call(prix_marche, S, K, T, r):
    """Newton-Raphson : on corrige sigma jusqu'à ce que le prix BS colle au prix de marché."""
    sigma = 0.20
    for i in range(100):
        prix_theorique = prix_call(S=S, K=K, T=T, r=r, sigma=sigma)
        ecart = prix_theorique - prix_marche
        if abs(ecart) < 0.01:
            return sigma
        v = vega(S=S, K=K, T=T, r=r, sigma=sigma) * 100  # vega() est par point de vol : on remet à l'échelle
        if v < 0.0001:
            return None
        sigma = sigma - ecart / v
        if sigma <= 0:
            return None
    return None


def construire_smile(ticker, date_echeance, r=0.05):
    spot = get_spot_price(ticker)
    calls, puts = get_option_chain(ticker, date_echeance)
    calls = filtrer_options(calls, spot)
    puts = filtrer_options(puts, spot)
    T = calculer_T(date_echeance)

    strikes = []
    vols = []

    # Sous le spot : puts OTM, convertis en call équivalent par la parité call-put
    for index, ligne in puts[puts["strike"] < spot].iterrows():
        prix_put = (ligne["bid"] + ligne["ask"]) / 2
        prix_call_equiv = prix_put + spot - ligne["strike"] * math.exp(-r * T)
        vol = vol_implicite_call(prix_marche=prix_call_equiv, S=spot, K=ligne["strike"], T=T, r=r)
        if vol is not None:
            strikes.append(ligne["strike"])
            vols.append(vol)

    # Au-dessus du spot : calls OTM
    for index, ligne in calls[calls["strike"] >= spot].iterrows():
        prix_mid = (ligne["bid"] + ligne["ask"]) / 2
        vol = vol_implicite_call(prix_marche=prix_mid, S=spot, K=ligne["strike"], T=T, r=r)
        if vol is not None:
            strikes.append(ligne["strike"])
            vols.append(vol)

    paires = sorted(zip(strikes, vols))
    return [k for k, v in paires], [v for k, v in paires]


def lisser_smile(strikes, vols, degre=2):
    coeffs = np.polyfit(strikes, vols, degre)
    return coeffs


def vol_lissee(K, coeffs):
    return np.polyval(coeffs, K)


def nettoyer_outliers(strikes, vols, seuil=0.02):
    coeffs = lisser_smile(strikes, vols, degre=3)
    strikes_propres = []
    vols_propres = []
    for k, v in zip(strikes, vols):
        v_lisse = vol_lissee(k, coeffs)
        if abs(v - v_lisse) < seuil:
            strikes_propres.append(k)
            vols_propres.append(v)
    return strikes_propres, vols_propres


def tracer_smile(ticker, date_echeance):
    strikes, vols = construire_smile(ticker, date_echeance)
    strikes, vols = nettoyer_outliers(strikes, vols)
    coeffs = lisser_smile(strikes, vols, degre=3)
    vols_lissees = [vol_lissee(k, coeffs) for k in strikes]

    plt.figure(figsize=(10, 6))
    plt.scatter(strikes, vols, s=10, label="Vol implicite de marché")
    plt.plot(strikes, vols_lissees, color="red", label="Smile lissé")
    plt.xlabel("Strike")
    plt.ylabel("Volatilité implicite")
    plt.title(f"Smile {ticker} - échéance {date_echeance}")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.show()


def construire_surface(ticker, dates_echeances, r=0.05):
    surface = {}
    for date in dates_echeances:
        strikes, vols = construire_smile(ticker, date, r)
        if len(strikes) < 10:
            continue
        strikes, vols = nettoyer_outliers(strikes, vols)
        coeffs = lisser_smile(strikes, vols, degre=3)
        T = calculer_T(date)
        surface[date] = {"T": T, "coeffs": coeffs}
    return surface


def get_vol(K, T, surface):
    """Vol pour (strike, maturité) : interpolation linéaire en T entre les deux smiles qui encadrent T."""
    dates = list(surface.keys())
    maturites_T = [surface[d]["T"] for d in dates]

    for i in range(len(maturites_T) - 1):
        if maturites_T[i] <= T <= maturites_T[i + 1]:
            T1 = maturites_T[i]
            T2 = maturites_T[i + 1]
            coeffs1 = surface[dates[i]]["coeffs"]
            coeffs2 = surface[dates[i + 1]]["coeffs"]

            vol1 = vol_lissee(K, coeffs1)
            vol2 = vol_lissee(K, coeffs2)

            vol = vol1 + (vol2 - vol1) * (T - T1) / (T2 - T1)
            return vol

    return None


def choisir_maturites_surface(ticker=TICKER):
    maturites = get_maturites(ticker)
    valides = [d for d in maturites if 14 / 365 <= calculer_T(d) <= 180 / 365]
    indices = [0, len(valides) // 2, len(valides) - 1]
    return [valides[i] for i in indices]


def sauvegarder_surface(surface):
    data = {
        "date_calibration": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "surface": {
            date: {"T": info["T"], "coeffs": info["coeffs"].tolist()}
            for date, info in surface.items()
        }
    }
    with open(FICHIER_SURFACE, "w") as f:
        json.dump(data, f, indent=2)


def charger_surface():
    if not os.path.exists(FICHIER_SURFACE):
        return None, None
    with open(FICHIER_SURFACE, "r") as f:
        contenu = f.read()
        if not contenu.strip():
            return None, None
        data = json.loads(contenu)
    surface = {
        date: {"T": info["T"], "coeffs": np.array(info["coeffs"])}
        for date, info in data["surface"].items()
    }
    return surface, data["date_calibration"]


if __name__ == "__main__":
    surface = construire_surface(TICKER, choisir_maturites_surface(TICKER))
    print("Maturités retenues :", list(surface.keys()))
