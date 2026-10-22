# seuil : écart max au mid avant que le client refuse en bloc (plus petit = plus sensible au prix)
# qty : fourchette de taille typique
# p_achat : probabilité que le client achète (sinon il vend)
# p_put : probabilité que l'option demandée soit un put (sinon un call)
# info : probabilité que le client trade dans le bon sens avant le mouvement du lendemain
PROFILS = {
    "Corporate":     {"seuil": 0.045, "qty": (1, 5),  "p_achat": 0.70, "p_put": 0.70, "info": 0.00},
    "Asset manager": {"seuil": 0.035, "qty": (2, 8),  "p_achat": 0.40, "p_put": 0.40, "info": 0.05},
    "Hedge fund":    {"seuil": 0.025, "qty": (2, 8),  "p_achat": 0.50, "p_put": 0.50, "info": 0.15},
    "Fonds de vol":  {"seuil": 0.020, "qty": (2, 10), "p_achat": 0.70, "p_put": 0.50, "info": 0.35},
}

SEUIL_DEFAUT = 0.03

FACTEUR_SPREAD_BASE = 1.0   # demi-spread = 50 % du seuil du client


def spread_base(client):
    seuil = PROFILS.get(client, {}).get("seuil", SEUIL_DEFAUT)
    return round(FACTEUR_SPREAD_BASE * seuil, 3)