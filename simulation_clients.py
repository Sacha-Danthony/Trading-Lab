import random

from Pricing import prix_call, prix_put, delta_call, delta_put
from clients import PROFILS, spread_base
from quoting import decision_client
from config import TICKER



def charger_rendements(ticker=TICKER, periode="2y"):
    import yfinance as yf
    data = yf.download(ticker, period=periode, progress=False)
    closes = data["Close"].squeeze().dropna()
    return [float(x) for x in closes.pct_change().dropna()]

def prix_option(type_option, S, K, T, r, vol):
    if type_option == "call":
        return float(prix_call(S, K, T, r, vol))
    return float(prix_put(S, K, T, r, vol))


def choisir_sens(type_option, rendement, informe, p_achat):
    if not informe:
        return "achat" if random.random() < p_achat else "vente"
    monte = rendement > 0
    if type_option == "call":
        return "achat" if monte else "vente"
    return "vente" if monte else "achat"

def simuler_un_trade(client, profil, rendements, spread, vol, r, T, hedge=False, cout_hedge=0.0001):
    ret = random.choice(rendements)
    S0, S1 = 100.0, 100.0 * (1 + ret)
    K = round(100 * random.uniform(0.95, 1.05))
    type_option = "put" if random.random() < profil["p_put"] else "call"
    informe = random.random() < profil["info"]
    sens = choisir_sens(type_option, ret, informe, profil["p_achat"])

    mid0 = prix_option(type_option, S0, K, T, r, vol)
    mid1 = prix_option(type_option, S1, K, T - 1 / 365, r, vol)
    cotation = {"mid": mid0, "bid": mid0 * (1 - spread / 2), "ask": mid0 * (1 + spread / 2)}

    if not decision_client({"sens": sens, "client": client}, cotation):
        return None

    if sens == "achat":
        prix_exec, qty_toi = cotation["ask"], -1
    else:
        prix_exec, qty_toi = cotation["bid"], 1

        

    markout = (mid1 - mid0) * qty_toi / mid0
    
    if hedge:
        d = delta_call(S0, K, T, r, vol) if type_option == "call" else delta_put(S0, K, T, r, vol)
        actions = -qty_toi * d
        gain_hedge = actions * (S1 - S0)
        frais_hedge = abs(actions) * S0 * cout_hedge
        markout += (gain_hedge - frais_hedge) / mid0

    return {"spread_capte": (mid0 - prix_exec) * qty_toi / mid0,
            "markout": markout}

def simuler(rendements, n_par_client=2000, spread=None, vol=0.18, r=0.05, T_jours=30, seed=0, hedge=False):   
    random.seed(seed)
    T = T_jours / 365
    resultats = {}

    for client, profil in PROFILS.items():
        n_acceptes = 0
        spread_capte = markout = 0.0

        for _ in range(n_par_client):
            trade = simuler_un_trade(client, profil, rendements, spread_base(client) if spread is None else spread, vol, r, T, hedge)
            if trade is None:
                continue
            n_acceptes += 1
            spread_capte += trade["spread_capte"]
            markout += trade["markout"]

        if n_acceptes:
            resultats[client] = {
                "acceptation": n_acceptes / n_par_client,
                "spread_capte": spread_capte / n_acceptes,
                "markout": markout / n_acceptes,
                "net": (spread_capte + markout) / n_acceptes,
            }
    return resultats


def afficher(resultats):
    print(f"{'Client':<15}{'Accept.':>9}{'Spread capté':>14}{'Markout J+1':>13}{'Net':>8}")
    for client, v in resultats.items():
        print(f"{client:<15}{v['acceptation']*100:>8.0f}%{v['spread_capte']*100:>13.2f}%"
              f"{v['markout']*100:>12.2f}%{v['net']*100:>7.2f}%")


if __name__ == "__main__":
    rendements = charger_rendements()
    print(f"{len(rendements)} rendements journaliers réels du {TICKER}\n")
    print("Sans hedge")
    afficher(simuler(rendements))
    print("\nAvec hedge du delta")
    afficher(simuler(rendements, hedge=True))