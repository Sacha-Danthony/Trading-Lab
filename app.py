import streamlit as st
from datetime import date
from flow_store import obtenir_lot_du_jour, marquer_traitee
from book_store import charger_book, pnl_non_realise, fermer_position, ajouter_hedge, regler_expirations, pnl_realise_total, charger_fermees
from vol_surface import construire_surface, sauvegarder_surface, charger_surface, calculer_T, get_vol
from quoting import coter, decision_client, executer_rfq, proba_acceptation, explication 
from book_greeks import (delta_net_book, gamma_net_book, vega_net_book, theta_net_book,
                         valeur_position, hedge_delta,delta_position, vega_position, multiplicateur)
from limites import (verifier_limites, risque_apres_trade, trade_bloque, hedge_necessaire, skew_suggere, hedge_vega_necessaire,
                         pire_scenario, LIMITE_STRESS, LIMITE_DELTA, LIMITE_VEGA, grille_stress, SEUIL_HEDGE, SEUIL_HEDGE_VEGA)
from data import get_spot_price
from markout import markout_par_client, spread_suggere
from pnl import pnl_explain
from journal import ajouter_entree, charger_journal
from config import TICKER, MULTIPLICATEUR_OPTION
from historique import enregistrer_snapshot, charger_historique, expliquer_pnl
from clients import spread_base
from hedge_vega import hedge_vega_suggere, executer_hedge_vega
from couts import frais_option
import pandas as pd
import time 

R = 0.05

st.set_page_config(page_title="Options & Volatility Trading Lab", layout="wide")

st.markdown("""
<style>
html { font-size: 17px; }
.stApp { background: #080b10; }
[data-testid="stHeader"] { background: #080b10; }
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stMainBlockContainer"] { padding-top: 2.2rem; }
[data-testid="stColumn"], [data-testid="column"] {
    background: #10151d; border: 1px solid #1f2733; border-radius: 4px; padding: 12px 16px;
}
[data-testid="stColumn"] [data-testid="stColumn"], [data-testid="column"] [data-testid="column"] {
    background: transparent; border: none; padding: 0;
}
[data-testid="stColumn"] h3, [data-testid="column"] h3, [data-testid="stVerticalBlockBorderWrapper"] h3 {
    font-size: 13px; letter-spacing: .1em; text-transform: uppercase; color: #ffb454;
    font-weight: 700; margin: 0 0 10px; padding: 0 0 8px; border-bottom: 1px solid #1f2733;
}
[data-testid="stMetricValue"] { font-size: 1.7rem; }
[data-testid="stMetricValue"] > div { overflow: visible; text-overflow: clip; white-space: nowrap; }
</style>
""", unsafe_allow_html=True)

st.title("Options & Volatility Trading Lab")

lot = obtenir_lot_du_jour()

maturites_besoin = sorted(set(
    [p["maturite"] for p in charger_book() if p["maturite"]] + [r["maturite"] for r in lot]
))

# --- Surface de vol : calibrée en direct, sinon dernière surface sauvegardée ---
if "surface" not in st.session_state or not st.session_state.surface:
    surface = construire_surface(TICKER, maturites_besoin)
    if surface:
        sauvegarder_surface(surface)
        st.session_state.surface = surface
        st.session_state.date_calibration = "en direct"
    else:
        surface, date_calibration = charger_surface()
        if surface:
            st.session_state.surface = surface
            st.session_state.date_calibration = date_calibration
        else:
            st.warning("Aucune surface disponible : premier lancement hors séance. "
                       "Réessaie pendant l'ouverture de Wall Street (15h30-22h, heure de France).")
            st.stop()

if st.session_state.date_calibration == "en direct":
    st.caption("Surface de vol calibrée sur les données Yahoo (retardées).")
else:
    st.warning(f"Marché fermé : valorisation sur les marks calibrés le {st.session_state.date_calibration}.")

surface = st.session_state.surface
spot_actuel = get_spot_price(TICKER)
regler_expirations()
book = charger_book()

total_delta = delta_net_book(book, surface, r=R, S=spot_actuel)
total_gamma = gamma_net_book(book, surface, r=R, S=spot_actuel)
total_vega = vega_net_book(book, surface, r=R, S=spot_actuel)
total_theta = theta_net_book(book, surface, r=R, S=spot_actuel)

mk = markout_par_client(book, surface, R, spot_actuel)

pnl_total = sum(pnl_non_realise(p, surface, S=spot_actuel) for p in book)
pnl_realise = pnl_realise_total()

def fmt_usd(x, decimales=0):
    return f"{x:+,.{decimales}f} $".replace(",", " ")

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric(TICKER, f"{spot_actuel:,.2f} $")
k2.metric("P&L non réalisé", fmt_usd(pnl_total))
k3.metric("P&L réalisé", fmt_usd(pnl_realise))
k4.metric("P&L total", fmt_usd(pnl_total + pnl_realise))
k5.metric("Delta net", f"{total_delta:+,.1f} {TICKER}".replace(",", " "), 
          help="Équivalent en actions : ton gain ou ta perte si le spot bouge de 1 $.")
k6.metric("Vega net", f"{total_vega:+,.1f} $/vol".replace(",", " "), 
          help="Gain ou perte en $ si la volatilité implicite monte d'un point.")

limites_depassees = verifier_limites(total_delta, total_vega)
pire_pnl = pire_scenario(total_delta, total_gamma, total_vega, total_theta, spot_actuel)[0]
if pire_pnl < -LIMITE_STRESS:
    limites_depassees.append(f"Stress {round(pire_pnl):,} $ au-delà de la limite (−{round(LIMITE_STRESS):,} $)")

seuils_hedge = []
if abs(total_delta) > SEUIL_HEDGE:
    seuils_hedge.append(f"Delta {round(total_delta, 1)} au-dessus du seuil de hedge (±{SEUIL_HEDGE})")
if abs(total_vega) > SEUIL_HEDGE_VEGA:
    seuils_hedge.append(f"Vega {round(total_vega, 1)} au-dessus du seuil de hedge (±{round(SEUIL_HEDGE_VEGA)})")

if limites_depassees:
    st.error(" · ".join(limites_depassees))
elif seuils_hedge:
    st.warning(" · ".join(seuils_hedge))
else:
    st.success("Tous les indicateurs sont dans les limites.")

tab_desk, tab_analyse, tab_journal = st.tabs(["Desk", "Analyse", "Journal"])

with tab_desk:
 onglet_risque, onglet_hedge = st.columns([1, 1], gap="small")
 onglet_flux = st.container(height=430, border=True)
 onglet_book = st.container(height=340, border=True)
with tab_analyse:
 onglet_pnl, onglet_scenario, onglet_vol = st.columns(3, gap="small")
with tab_journal:
 onglet_journal = st.container()


# --- Flux client ---
with onglet_flux:
  st.subheader("Flux client du jour")

  st.checkbox("Mode formation : voir le modèle d'acceptation", key="mode_formation")

  if "message_rfq" in st.session_state:
    ok, msg = st.session_state.pop("message_rfq")
    (st.success if ok else st.warning)(msg)

    

  for rfq in lot:
    st.write(f"**{rfq['type']} strike {rfq['strike']}** — {rfq['sens']} — qty {rfq['qty']} — échéance {rfq['maturite']}")

    if rfq.get("traitee"):
        statut = "✅ ACCEPTÉ" if rfq["accepte"] else "❌ REFUSÉ"
        st.write(f"Bid: {round(rfq['bid'], 3)} / Ask: {round(rfq['ask'], 3)} — {statut}")
        cotation_r = {"mid": rfq.get("mid", (rfq["bid"] + rfq["ask"]) / 2), "bid": rfq["bid"], "ask": rfq["ask"]}
        st.caption(explication(rfq, cotation_r, rfq["accepte"], detail=st.session_state.get("mode_formation", False)))
    else:
        base = spread_base(rfq.get("client"))
        suggere = spread_suggere(rfq.get("client"), mk, base)
        spread_defaut = round(suggere * 100 * 2) / 2   # pas de 0,5 comme le slider
        delta_apres, vega_apres = risque_apres_trade(rfq, surface, spot_actuel, total_delta, total_vega, r=R)
        skew_defaut = round(skew_suggere(rfq, total_delta, total_vega, delta_apres, vega_apres) * 100 * 2) / 2
        st.caption(f"Client : {rfq.get('client', '?')} | spread suggéré : {round(suggere * 100, 1)} % | skew suggéré : {skew_defaut} %")
        spread = st.slider(f"Spread #{rfq['id']} (%)", 1.0, 15.0, spread_defaut, step=0.5,
                           key=f"spread_{rfq['id']}") / 100
        skew = st.slider(f"Skew #{rfq['id']} (%)", -5.0, 5.0, skew_defaut, step=0.5,
                         key=f"skew_{rfq['id']}") / 100

        apercu = coter(rfq, surface, spread=spread, skew=skew)
        st.caption(f"Mid {round(apercu['mid'], 3)} | Bid {round(apercu['bid'], 3)} | Ask {round(apercu['ask'], 3)}")

        if rfq["sens"] == "achat":
            edge = (apercu["ask"] - apercu["mid"]) * rfq["qty"] * MULTIPLICATEUR_OPTION
        else:
            edge = (apercu["mid"] - apercu["bid"]) * rfq["qty"] * MULTIPLICATEUR_OPTION
        if edge < 0:
            st.error(f"Edge attendu si accepté : {round(edge, 2)} $ : tu cèdes du spread au client.")
        else:
            st.caption(f"Edge attendu si accepté : +{round(edge, 2)} $ (frais : {round(frais_option(rfq['qty']), 2)} $)")

        # Contrôle pré-trade : que devient mon risque si le client accepte ?
       
        bloquees = trade_bloque(total_delta, total_vega, delta_apres, vega_apres)
        for m in bloquees:
            st.error(f"Trade bloqué : {m}")
        st.table([
            {"Mesure": "Delta", "Avant": round(total_delta, 1), "Après": round(delta_apres, 1), "Limite": f"±{round(LIMITE_DELTA)}"},
            {"Mesure": "Vega", "Avant": round(total_vega, 1), "Après": round(vega_apres, 1), "Limite": f"±{round(LIMITE_VEGA)}"},
        ])

        if st.session_state.get("mode_formation", False):
            cotation_prev = coter(rfq, surface, spread=spread, skew=skew)
            proba, ecart, seuil = proba_acceptation(rfq, cotation_prev)
            st.caption(f"[Mode formation] Acceptation estimée : {round(proba * 100)} % · écart {round(ecart * 100, 1)} % vs seuil {round(seuil * 100, 1)} %")

        if st.button(f"Coter #{rfq['id']}", disabled=bool(bloquees)):
            with st.spinner("Le client réfléchit…"):
                time.sleep(1.5)
            cotation = coter(rfq, surface, spread=spread, skew=skew)
            accepte = decision_client(rfq, cotation)
            if accepte:
                executer_rfq(rfq, cotation, spot=spot_actuel)
            marquer_traitee(rfq["id"], cotation, accepte)
            st.session_state["message_rfq"] = (accepte, explication(rfq, cotation, accepte, detail=st.session_state.get("mode_formation", False)))
            st.rerun()

    st.divider()

def couleur_pnl(v):
    if v is None or pd.isna(v):
        return ""
    if v > 0:
        return "color: #4fd18b"
    if v < 0:
        return "color: #ff7b7b"
    return ""

def jauge(label, valeur, limite):
    ratio = max(-1, min(1, valeur / limite))
    utilisation = abs(ratio)
    couleur = "#5aa9ff" if utilisation < 0.6 else "#ffb454" if utilisation < 0.9 else "#ff7b7b"
    gauche = 50 if ratio >= 0 else 50 + ratio * 50
    largeur = utilisation * 50
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;font-size:13px"><span>{label}</span><span>{valeur:+,.1f} / ±{limite:,.0f}</span></div>'
        f'<div style="position:relative;height:8px;background:#1b2231;margin:4px 0 14px">'
        f'<div style="position:absolute;top:0;height:100%;left:{gauche}%;width:{largeur}%;background:{couleur}"></div>'
        f'<div style="position:absolute;left:50%;top:-2px;width:1px;height:12px;background:#3a4558"></div></div>',
        unsafe_allow_html=True)

def couleur_stress(v):
    intensite = min(abs(v) / LIMITE_STRESS, 1) * 0.45
    if v < 0:
        return f"background-color: rgba(255,123,123,{intensite:.2f}); color: #f3d6d6"
    if v > 0:
        return f"background-color: rgba(79,209,139,{intensite:.2f}); color: #d3f0e1"
    return ""
    
# --- Book ---
with onglet_book:
    st.subheader("Book actuel")
    lignes_book = []
    stocks = [p for p in book if p["type"] == "stock"]
    for p in book:
        if p["type"] == "stock":
            continue
        mult = multiplicateur(p)
        lignes_book.append({
            "#": p["id"],
            "Type": p["type"],
            "Strike": str(p["strike"]) if p["strike"] else "—",
            "Échéance": p["maturite"] or "—",
            "Qté": p["qty"],
            "Entrée": round(p["prix_entree"], 3),
            "Valeur": round(valeur_position(p, surface, R, spot_actuel), 3),
            "P&L ($)": round(pnl_non_realise(p, surface, S=spot_actuel), 2),
            "Delta": round(delta_position(p, surface, R, spot_actuel) * p["qty"] * mult, 1),
            "Vega": round(vega_position(p, surface, R, spot_actuel) * p["qty"] * mult, 1),
        })

    if stocks:
        qty_stock = sum(s["qty"] for s in stocks)
        prix_moyen = sum(s["qty"] * s["prix_entree"] for s in stocks) / qty_stock if qty_stock != 0 else 0
        lignes_book.append({
            "#": "hedge", "Type": "stock", "Strike": "—", "Échéance": "—",
            "Qté": qty_stock,
            "Entrée": round(prix_moyen, 3),
            "Valeur": round(valeur_position(stocks[0], surface, R, spot_actuel), 3),
            "P&L ($)": round(sum(pnl_non_realise(s, surface, S=spot_actuel) for s in stocks), 2),
            "Delta": round(qty_stock, 1),
            "Vega": 0.0,
        })

    tot_pnl = sum(l["P&L ($)"] for l in lignes_book)
    tot_delta = sum(l["Delta"] for l in lignes_book)
    tot_vega = sum(l["Vega"] for l in lignes_book)
    lignes_book.append({
        "#": None, "Type": "TOTAL", "Strike": "", "Échéance": "",
        "Qté": None, "Entrée": None, "Valeur": None,
        "P&L ($)": round(tot_pnl, 2),
        "Delta": round(tot_delta, 1),
        "Vega": round(tot_vega, 1),
    })
    df_book = pd.DataFrame(lignes_book)
    df_book["#"] = df_book["#"].apply(lambda x: "" if x is None or pd.isna(x) else str(x))

    def f_num(fmt):
      def f(x):
        try:
          return "" if (x is None or x == "" or pd.isna(x)) else format(x, fmt)
        except (ValueError, TypeError):
          return str(x)
      return f

    st.dataframe(
      df_book.style.map(couleur_pnl, subset=["P&L ($)"]).format({
        "Strike": f_num(".0f"), "Qté": f_num("+.0f"), "Entrée": f_num(".2f"), "Valeur": f_num(".2f"),
        "P&L ($)": f_num("+,.0f"), "Delta": f_num("+,.0f"), "Vega": f_num("+,.0f")}),
      hide_index=True)

    if book:
        positions_par_id = {p["id"]: p for p in book}
        choix = st.selectbox("Position à fermer", list(positions_par_id), key="choix_fermer")
        position = positions_par_id[choix]
        prix_sortie = valeur_position(position, surface, R, spot_actuel)
        if st.button(f"Fermer #{choix} à {round(prix_sortie, 3)}", key="btn_fermer"):
            pnl_realise = fermer_position(choix, prix_sortie)
            st.success(f"P&L réalisé : {round(pnl_realise, 2)} $")
            st.rerun()
    else:
        st.caption("Book vide.")

# --- Greeks ---
with onglet_risque:
 st.subheader("Greeks du book")

 col1, col2 = st.columns(2)
 col3, col4 = st.columns(2)
 col1.metric("Delta net", f"{total_delta:+,.1f} {TICKER}".replace(",", " "),
             help="Équivalent en actions : ton gain ou ta perte si le spot bouge de 1 $.")
 col2.metric("Gamma net", f"{total_gamma:+,.2f} {TICKER}/$".replace(",", " "),
             help="De combien ton delta (en actions) change quand le spot bouge de 1 $.")
 col3.metric("Vega net", f"{total_vega:+,.1f} $/vol".replace(",", " "),
             help="Gain ou perte en $ si la volatilité implicite monte d'un point.")
 col4.metric("Theta net", f"{total_theta:+,.1f} $/jour".replace(",", " "),
             help="Ce que le temps qui passe te rapporte ou te coûte par jour, en $.")

for a in verifier_limites(total_delta, total_vega):
    st.error(f"Limite dépassée : {a}")
    pire_pnl, pire_spot, pire_vol = pire_scenario(total_delta, total_gamma, total_vega, total_theta, spot_actuel)
    texte_pire = f"Pire scénario de stress : {round(pire_pnl)} $ (SPY {pire_spot * 100:+.0f} %, vol {pire_vol:+.0f} pts)"
    if pire_pnl < -LIMITE_STRESS:
        st.error(f"Limite de stress dépassée : {texte_pire} (limite : -{round(LIMITE_STRESS)} $)")
    else:
        st.caption(f"{texte_pire} | limite : -{round(LIMITE_STRESS)} $")

with onglet_hedge:
 st.subheader("Hedge du vega")
 hedge_v = hedge_vega_suggere(total_vega, surface, spot_actuel, R)
 if hedge_v is None:
    st.caption("Aucune option de référence disponible pour hedger le vega.")
 else:
    st.write(f"Hedge suggéré : {hedge_v['qty']:+d} contrats de {hedge_v['type']} "
             f"strike {hedge_v['strike']} échéance {hedge_v['maturite']} "
             f"(vega par contrat : {round(hedge_v['vega_contrat'], 1)} $)")
    if hedge_vega_necessaire(total_vega):
        st.warning("Vega au-dessus du seuil : un hedge est justifié.")
    else:
        st.success("Vega sous le seuil : pas de hedge nécessaire.")
    qty_vega = st.number_input("Contrats à exécuter", value=int(hedge_v["qty"]), step=1,
                               key=f"qty_hedge_vega_{hedge_v['qty']}")
    if st.button("Hedger le vega", disabled=(qty_vega == 0)):
        executer_hedge_vega({**hedge_v, "qty": int(qty_vega)}, surface, R, spot_actuel)
        st.rerun()
 st.subheader("Hedge du delta")
 hedge_qty = hedge_delta(total_delta)
 st.write(f"Hedge suggéré : {round(hedge_qty, 1)} actions {TICKER}")
 if hedge_necessaire(total_delta):
    st.warning("Delta au-dessus du seuil : un hedge est justifié.")
 else:
    st.success("Delta sous le seuil : pas de hedge nécessaire (tu évites les frais).")
 qty_delta = st.number_input("Actions à exécuter", value=int(round(hedge_qty)), step=10,
                            key=f"qty_hedge_delta_{round(hedge_qty)}")
 if st.button("Hedger le delta", disabled=(qty_delta == 0)):
    ajouter_hedge(qty=int(qty_delta), prix=spot_actuel, date_entree=str(date.today()))
    st.rerun()

# --- Scénario ---
with onglet_scenario:
    st.subheader("Scénario : et si le marché bouge ?")
    dS = st.slider(f"Mouvement du {TICKER} (%)", -5.0, 5.0, 0.0, step=0.5) / 100 * spot_actuel
    dvol = st.slider("Mouvement de vol (points)", -5.0, 5.0, 0.0, step=0.5)
    dt = st.slider("Jours qui passent", 0, 10, 1)

    st.markdown("**Stress test : P&L du book ($)**")
    df_stress = pd.DataFrame(grille_stress(total_delta, total_gamma, total_vega, total_theta, spot_actuel)).T
    st.dataframe(df_stress.style.map(couleur_stress).format("{:,.0f}"))

    p_delta, p_gamma, p_vega, p_theta, p_total = pnl_explain(
    total_delta, total_gamma, total_vega, total_theta, dS, dvol, dt)
    st.table([{"Source": "Delta", "P&L ($)": round(p_delta, 2)},
    {"Source": "Gamma", "P&L ($)": round(p_gamma, 2)},
    {"Source": "Vega", "P&L ($)": round(p_vega, 2)},
    {"Source": "Theta", "P&L ($)": round(p_theta, 2)},
    {"Source": "Total", "P&L ($)": round(p_total, 2)}])


# --- P&L ---
with onglet_pnl:
    st.subheader("P&L du book")

    pnl_total = 0
    for position in book:
        pnl = pnl_non_realise(position, surface, S=spot_actuel)
        pnl_total = pnl_total + pnl
        

    c1, c2, c3 = st.columns(3)
    c1.metric("P&L non réalisé", f"{pnl_total:+,.2f} $".replace(",", " "),
              help="Valeur actuelle des positions ouvertes moins leur prix d'entrée, frais déduits.")
    c2.metric("P&L réalisé", f"{pnl_realise_total():+,.2f} $".replace(",", " "),
              help="Gain ou perte sur les positions déjà fermées.")
    c3.metric("P&L total", f"{pnl_total + pnl_realise_total():+,.2f} $".replace(",", " "),
              help="Non réalisé plus réalisé.")

    st.write("**Positions fermées**")
    fermees = charger_fermees()
    if fermees:
     st.table([{"#": f["id"], "Type": f["type"], "Strike": f["strike"], "Qté": f["qty"],
               "Entrée": round(f["prix_entree"], 3), "Sortie": round(f["prix_sortie"], 3),
               "Date": f["date_sortie"], "P&L réalisé ($)": round(f["pnl_realise"], 2)}
              for f in fermees])
    else:
     st.caption("Aucune position fermée pour l'instant.")

    enregistrer_snapshot(spot_actuel, total_delta, total_gamma, total_vega, total_theta,
                        pnl_total, pnl_realise_total())

    # --- Markout par client ---
    st.subheader("Markout par client")
    if mk:
        lignes = [{"Client": c, "Trades": v["nb"],
                "Spread capté ($)": round(v["spread_capte"], 2),
                "Markout brut ($)": round(v["markout"], 2),
                "Markout après hedge ($)": round(v["markout_hedge"], 2),
                "Net après hedge ($)": round(v["spread_capte"] + v["markout_hedge"], 2)} for c, v in mk.items()]
        st.table(lignes)
        st.caption("Après hedge = markout brut moins l'effet du delta : ce que ton hedge ne couvre pas.")
    else:
        st.caption("Pas encore de trades avec un client identifié.")

# --- Historique ---
with onglet_pnl:
    st.subheader("Historique du desk")
    historique = charger_historique()
    if len(historique) >= 2:
        st.line_chart({e["date"]: e["pnl_total"] for e in historique})
    else:
        st.caption("La courbe apparaîtra dès que tu auras au moins 2 jours d'historique.")

    explication = expliquer_pnl(charger_historique())
    st.subheader("D'où vient le P&L ?")
    if explication:
        st.table([{"Date": l["date"], "Variation ($)": l["variation"], "Delta ($)": l["delta"],
                "Gamma ($)": l["gamma"], "Theta ($)": l["theta"], "Résidu ($)": l["residu"]}
                for l in explication])
        st.caption("Résidu = vega, spread des nouveaux trades, frais et hedges : tout ce que le delta, "
                "le gamma et le theta du snapshot précédent n'expliquent pas.")
    else:
        st.caption("Il faut au moins 2 jours de snapshots pour expliquer le P&L.")

# --- Journal ---
with onglet_journal:
    st.subheader("Journal de trading")

    texte = st.text_area("Qu'as-tu fait aujourd'hui, et pourquoi ?")

    if st.button("Enregistrer dans le journal"):
        if texte.strip():
            greeks = {
                "delta": round(total_delta, 2),
                "gamma": round(total_gamma, 4),
                "vega": round(total_vega, 2),
                "theta": round(total_theta, 2)
            }
            ajouter_entree(texte, greeks)
            st.rerun()

    for entree in reversed(charger_journal()):
        st.write(f"**{entree['date']}** — {entree['texte']}")
        st.caption(f"Delta {entree['greeks']['delta']} | Gamma {entree['greeks']['gamma']} | "
                   f"Vega {entree['greeks']['vega']} | Theta {entree['greeks']['theta']}")

# --- Vol ---
with onglet_vol:
    st.subheader("Surface de volatilité")
    st.caption(f"Calibration : {st.session_state.date_calibration}")
    lignes_vol = []
    for m in sorted(surface.keys()):
        T = calculer_T(m)
        vol_atm = get_vol(K=round(spot_actuel), T=T, surface=surface)
        if vol_atm is not None:
            lignes_vol.append({"Échéance": m, "Jours": round(T * 365), "Vol ATM (%)": round(vol_atm * 100, 2)})
    st.table(lignes_vol)
    dates_smile = sorted(surface.keys())
    pas = max(1, len(dates_smile) // 4)
    dates_smile = dates_smile[::pas][:4]
    strikes_grille = list(range(round(spot_actuel * 0.9), round(spot_actuel * 1.1) + 1, 5))
    courbes = {}
    for m in dates_smile:
        T = calculer_T(m)
        vols = [get_vol(K=k, T=T, surface=surface) for k in strikes_grille]
        courbes[m] = [None if v is None else v * 100 for v in vols]
    st.write("**Smile de volatilité par échéance** (vol implicite en %, selon le strike)")
    st.line_chart(pd.DataFrame(courbes, index=strikes_grille))