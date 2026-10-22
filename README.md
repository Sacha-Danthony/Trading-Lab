# Options & Volatility Trading Lab

Simulateur de desk flow : des RFQ clients simulées remplissent ton book, tu cotes (spread + skew),
le client accepte ou refuse, tu suis tes Greeks, tes limites, ton hedge delta et ton P&L.
Données de marché réelles (SPY, chaînes d'options Yahoo Finance) ; flux et décisions des clients simulés.

## Lancer sur Mac

```bash
cd trading_lab
pip3 install numpy scipy pandas yfinance matplotlib streamlit
python3 -m streamlit run app.py
```

Toujours lancer depuis le dossier du projet : `book.json`, `flow.json`, `journal.json`
et `surface.json` sont créés dans le dossier courant.

- Marché US fermé (hors 15h30-22h, heure de France) : la surface ne peut être calibrée que si
  Yahoo renvoie des cotations ; au tout premier lancement il vaut mieux démarrer pendant la séance.
- `python3 reset.py` remet le book, le flux du jour et le journal à zéro.
- `python3 Pricing.py` : test rapide du pricing (call ATM 100/100, 1 an, vol 20 %, r 5 % : ≈ 10,45).

## Fichiers
| Fichier | Rôle |
|---|---|
| Pricing.py | Black-Scholes et Greeks |
| data.py | Spot et chaînes d'options (yfinance), filtre de liquidité |
| vol_surface.py | Vol implicite (Newton-Raphson), smile, nettoyage, surface, interpolation |
| book_greeks.py | Greeks et valeur du book, hedge delta |
| book_store.py | Book persistant, P&L réalisé / non réalisé, frais |
| flow.py, flow_store.py | Génération et stockage des RFQ du jour |
| quoting.py | Mid, cotation bid/ask, décision du client, exécution |
| couts.py | Frais de transaction |
| limites.py | Limites delta/vega et contrôle pré-trade |
| markout.py | Spread capté et markout par client, spread suggéré |
| clients.py | Profils de clients (sensibilité au prix, taille, sens) |
| journal.py | Journal de décisions avec snapshot des Greeks |
| pnl.py | Explication du P&L par les Greeks |
| app.py | Interface Streamlit (flux, book, Greeks, limites bloquantes, scénario, markout, P&L, journal) |
