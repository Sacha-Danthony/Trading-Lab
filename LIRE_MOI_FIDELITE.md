# Note sur cette reconstruction

Ce dossier a été reconstruit depuis nos conversations, pas copié depuis ton PC.

Certain (code retrouvé tel quel) : Black-Scholes et Greeks, vol implicite Newton-Raphson, smile, nettoyage des outliers,
interpolation de surface, Greeks du book, cotation bid/ask, décision du client, limites (fonctions), journal, stockage JSON.

Déduit / réécrit (à comparer avec tes fichiers dès que tu récupères l'autre PC) :
- app.py : retrouvé dans une ancienne version, puis remis à jour (contrôle pré-trade, alertes de limites, imports nettoyés).
- limites.py : valeurs des constantes (budget 5 000 $, chocs de 5 $ et 5 pts de vol) choisies par défaut.
- fermer_position / pnl_non_realise : frais d'entrée et de sortie soustraits.
- vega divisé par 100 et theta par 365 dans Pricing.py.

Dès que tu retrouves ton PC : compare, puis pousse la version qui te convient sur GitHub.
