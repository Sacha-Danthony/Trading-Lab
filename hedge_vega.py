from config import TICKER, MULTIPLICATEUR_OPTION 
from data import get_maturites
from vol_surface import calculer_T, get_vol
from book_greeks import vega_position
from datetime import date
from book_store import ajouter_position
from book_greeks import valeur_position
from config import TICKER, MULTIPLICATEUR_OPTION, COUT_HEDGE_VEGA

def choisir_option_hedge_vega(surface, S, r, jours_cible=90):
    """Call ATM, maturité la plus proche de jours_cible dont la vol est connue."""
    strike = round(S)
    T_cible = jours_cible / 365
    candidates = sorted(get_maturites(TICKER), key=lambda m: abs(calculer_T(m) - T_cible))
    for maturite in candidates:
        T = calculer_T(maturite)
        if T > 0 and get_vol(K=strike, T=T, surface=surface) is not None:
            return {"type": "call", "strike": strike, "maturite": maturite, "qty": 1}
    return None


def hedge_vega_suggere(vega_net, surface, S, r, jours_cible=90):
    """Nombre de contrats à acheter (>0) ou vendre (<0) pour ramener le vega vers zéro."""
    option = choisir_option_hedge_vega(surface, S, r, jours_cible)
    if option is None:
        return None
    vega_contrat = float(vega_position(option, surface, r, S) * MULTIPLICATEUR_OPTION)
    nb_contrats = int(round(-vega_net / vega_contrat))
    return {**option, "qty": nb_contrats, "vega_contrat": vega_contrat}

def executer_hedge_vega(hedge, surface, r, S, cout=COUT_HEDGE_VEGA):
    """Achète (qty > 0) ou vend (qty < 0) l'option de hedge au mid, plus un coût de transaction."""
    option = {"type": hedge["type"], "strike": hedge["strike"],
              "maturite": hedge["maturite"], "qty": hedge["qty"]}
    mid = float(valeur_position(option, surface, r, S))
    prix = mid * (1 + cout) if hedge["qty"] > 0 else mid * (1 - cout)
    return ajouter_position(
        type_option=hedge["type"], strike=hedge["strike"], maturite=hedge["maturite"],
        qty=hedge["qty"], prix_entree=prix, date_entree=str(date.today()),
        client=None, mid_entree=mid, spot_entree=S,
    )


