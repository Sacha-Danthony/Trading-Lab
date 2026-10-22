from book_greeks import valeur_position, multiplicateur, delta_position


def markout_par_client(book, surface, r, S):
    """Par client : spread capté à l'exécution (vs mid) et markout (évolution du mid depuis le trade).
    qty > 0 = tu as acheté, qty < 0 = tu as vendu."""
    resultats = {}
    for p in book:
        if p["type"] == "stock" or p.get("client") is None or p.get("mid_entree") is None:
            continue
        mid_maintenant = valeur_position(p, surface, r, S)
        spread_capte = (p["mid_entree"] - p["prix_entree"]) * p["qty"] * multiplicateur(p)
        markout = (mid_maintenant - p["mid_entree"]) * p["qty"] * multiplicateur(p)
        spot_e = p.get("spot_entree")
        if spot_e is None:
            markout_h = None
        else:
            delta_entree = delta_position(p, surface, r, spot_e)
            markout_h = markout - delta_entree * p["qty"] * multiplicateur(p) * (S - spot_e)

        c = resultats.setdefault(p["client"], {"nb": 0, "spread_capte": 0.0, "markout": 0.0, "markout_hedge": 0.0})
        c["nb"] += 1
        c["spread_capte"] += spread_capte
        c["markout"] += markout
        if markout_h is not None:
            c["markout_hedge"] += markout_h
    return resultats


def spread_suggere(client, mk, base):
    """Spread de départ pour ce client, ajusté selon son historique (mk = résultat de markout_par_client)."""
    v = mk.get(client)
    if v is None or v["nb"] < 2:
        return base                      # pas assez d'historique : spread normal
    net = v["spread_capte"] + v["markout"]
    if net < 0:
        return base + 0.02               # ce client te fait perdre de l'argent
    if v["markout"] < 0:
        return base + 0.01               # il mange une partie de ta marge
    return base
