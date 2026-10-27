import streamlit as st
from datetime import date, datetime
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
import numbers

R = 0.05

st.set_page_config(page_title="Options & Volatility Trading Lab", layout="wide")

st.markdown("""
<style>
html { font-size: 17px; }
.stApp { background: #000; }
[data-testid="stHeader"] { display: none; }
[data-testid="stAppDeployButton"] { display: none; }
[data-testid="stMainBlockContainer"] { padding-top: 0.5rem; }
[data-testid="stColumn"], [data-testid="column"] {
    background: #050505; border: 1px solid #2a2a2a; border-radius: 0; padding: 12px 16px;
}
[data-testid="stColumn"] [data-testid="stColumn"], [data-testid="column"] [data-testid="column"] {
    background: transparent; border: none; padding: 0;
}
[data-testid="stMainBlockContainer"] h3 {
    font-size: 13px; letter-spacing: .1em; text-transform: uppercase; color: #ff9f1a;
    font-weight: 700; margin: 0 0 10px; padding: 0 0 8px; border-bottom: 1px solid #2a2a2a;
}
[data-testid="stMetricValue"] { font-size: 1.7rem; }
[data-testid="stMetricValue"] > div { overflow: visible; text-overflow: clip; white-space: nowrap; }
.bar { display:flex; align-items:center; gap:14px; background:#111; border-bottom:1px solid #333; height:32px; padding:0 8px; font-size:13px; }
.cmd { background:#ffb000; color:#000; font-weight:700; padding:3px 10px; }
.tape { display:flex; gap:24px; background:#0a0a0a; border-bottom:1px solid #222; height:28px; align-items:center; padding:0 10px; font-size:13px; white-space:nowrap; overflow:hidden; color:#ddd; }
.g{color:#2ee66b !important} .r{color:#ff4d4d !important} .w{color:#fff !important} .d{color:#777 !important} .a{color:#ff9f1a !important}
.rw { display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px dotted #222; font-size:14px; }
.lim { height:7px; background:#1a1a1a; margin:2px 0 8px; } .lim i { display:block; height:7px; }
table.t { border-collapse:collapse; width:100%; font-size:14px; }
table.t th { color:#ff9f1a; font-weight:400; text-align:right; padding:4px 8px; border-bottom:1px solid #333; background:#0d0d0d; }
table.t td { text-align:right; padding:3px 8px; color:#e8e8e8; border-bottom:1px solid #151515; }
table.t th:nth-child(-n+2), table.t td:nth-child(-n+2) { text-align:left; }
table.t tr.tot td { color:#fff; font-weight:700; border-top:1px solid #555; }
.tk { background:#2a1c00; color:#ffcf70; padding:5px 8px; margin:8px 0 4px; font-size:13px; font-weight:700; }
[data-testid="stButtonGroup"] button { border-radius:0 !important; min-height:26px; padding:0 12px; background:#111; border-color:#333; }
[data-testid="stButtonGroup"] button[kind*="Active"] { background:#ff9f1a !important; color:#000 !important; }
.stButton > button { background:#ff9f1a; color:#000; border:none; border-radius:0; font-weight:700; }
.stButton > button:hover { background:#ffb84d; color:#000; }
.stButton > button:disabled { background:#333; color:#777; }
table.t th, table.t td { white-space: nowrap; }
</style>
""", unsafe_allow_html=True)


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

if st.session_state.date_calibration != "en direct":
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

def couleur(x):
    return "g" if x > 0 else "r" if x < 0 else "w"

def spark(valeurs, coul, w=70, h=16):
    if len(valeurs) < 2:
        return ""
    mn, mx = min(valeurs), max(valeurs)
    ecart = (mx - mn) or 1
    points = " ".join(
        f"{i * w / (len(valeurs) - 1):.1f},{h - 2 - (v - mn) / ecart * (h - 4):.1f}"
        for i, v in enumerate(valeurs))
    return f'<svg width="{w}" height="{h}" style="vertical-align:middle"><polyline points="{points}" fill="none" stroke="{coul}" stroke-width="1.5"/></svg>'

hist = charger_historique()

def serie(cle):
    return [snap[cle] for snap in hist]

def html_table(df, formats, colonnes_couleur=()):
    def cellule(col, v):
        if v is None or (not isinstance(v, str) and pd.isna(v)) or v == "":
            return "<td></td>"
        if col in formats and isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                pass
        if col in formats and isinstance(v, numbers.Number):
            txt = format(v, formats[col])
        else:
            txt = str(v)
        cls = couleur(v) if col in colonnes_couleur and isinstance(v, numbers.Number) else ""
        return f'<td class="{cls}">{txt}</td>'
    entete = "".join(f"<th>{c}</th>" for c in df.columns)
    lignes = ""
    for _, row in df.iterrows():
        cls_tr = ' class="tot"' if "TOTAL" in row.values else ""
        lignes += f"<tr{cls_tr}>" + "".join(cellule(c, row[c]) for c in df.columns) + "</tr>"
    return f'<table class="t"><tr>{entete}</tr>{lignes}</table>'

def heatmap_html(df, limite):
    entete = "<tr><th></th>" + "".join(f"<th>{c}</th>" for c in df.columns) + "</tr>"
    lignes = ""
    for idx, row in df.iterrows():
        cases = ""
        for v in row:
            a = min(abs(v) / limite, 1) * 0.8 + 0.1
            if v < 0:
                fond = f"rgba(255,77,77,{a:.2f})"
            elif v > 0:
                fond = f"rgba(46,230,107,{a:.2f})"
            else:
                fond = "#1a1a1a"
            cases += f'<td style="background:{fond};color:#fff;text-align:center">{v:,.0f}</td>'
        lignes += f'<tr><td class="d">{idx}</td>{cases}</tr>'
    return f'<table class="t">{entete}{lignes}</table>'


# --- Limites (calculées AVANT le bandeau pour le voyant) ---
limites_depassees = verifier_limites(total_delta, total_vega)
df_stress = pd.DataFrame(grille_stress(total_delta, total_gamma, total_vega, total_theta, spot_actuel)).T
pire_pnl = df_stress.min().min()
pire_vol_lbl, pire_spot_lbl = df_stress.stack().idxmin()
if pire_pnl < -LIMITE_STRESS:
    limites_depassees.append(f"Stress {round(pire_pnl):,} $ au-delà de la limite (−{round(LIMITE_STRESS):,} $)")

seuils_hedge = []
if abs(total_delta) > SEUIL_HEDGE:
    seuils_hedge.append(f"Delta {round(total_delta, 1)} au-dessus du seuil de hedge (±{SEUIL_HEDGE})")
if abs(total_vega) > SEUIL_HEDGE_VEGA:
    seuils_hedge.append(f"Vega {round(total_vega, 1)} au-dessus du seuil de hedge (±{round(SEUIL_HEDGE_VEGA)})")

if limites_depassees:
    statut = '<span class="r">● LIMITE DÉPASSÉE</span>'
elif seuils_hedge:
    statut = '<span class="a">● HEDGE À FAIRE</span>'
else:
    statut = '<span class="g">● ALL LIMITS OK</span>'

# --- Barre du haut + bandeau ---
maintenant = datetime.now().strftime("%d/%m/%Y · %H:%M")
st.markdown(f"""
<div class="bar"><span class="cmd">{TICKER} ▸ OPTIONS DESK</span>
<span class="w">Options &amp; Volatility Trading Lab</span>
<span class="d" style="margin-left:auto">{maintenant}</span></div>
<div class="tape">
<span class="w">{TICKER}</span><span class="w">{spot_actuel:,.2f}</span>{spark(serie("spot"), "#4c8dff")}
<span>P&amp;L NON RÉAL. <span class="{couleur(pnl_total)}">{pnl_total:+,.0f} $</span></span>
<span>P&amp;L RÉAL. <span class="{couleur(pnl_realise)}">{pnl_realise:+,.0f} $</span></span>
<span>P&amp;L TOTAL <span class="{couleur(pnl_total + pnl_realise)}">{pnl_total + pnl_realise:+,.0f} $</span></span>{spark(serie("pnl_total"), "#ff9f1a")}
<span>DELTA <span class="w">{total_delta:+,.1f}</span></span>{spark(serie("delta"), "#ff9f1a")}
<span>VEGA <span class="w">{total_vega:+,.1f} $/vol</span></span>{spark(serie("vega"), "#ff9f1a")}
{statut}
<span class="d">DATA: YAHOO · DELAYED</span>
<span class="d">MODE SIMULATION · CLIENTS FICTIFS</span>
</div>
""", unsafe_allow_html=True)

tab_desk, tab_analyse, tab_journal = st.tabs(["Desk", "Analyse", "Journal"])

with tab_desk:
 c_flux, c_book, c_risque = st.columns([1.3, 2.3, 1.1], gap="small")
 onglet_flux = c_flux.container(height=600, border=False)
 onglet_book = c_book.container(height=600, border=False)
 onglet_risque = c_risque.container(border=False)
 onglet_hedge = c_risque.container(border=False)
with tab_analyse:
 onglet_pnl, onglet_scenario, onglet_vol = st.columns(3, gap="small")
with tab_journal:
 onglet_journal = st.container()


# --- Flux client ---
with onglet_flux:
  st.subheader("Flux client du jour")
  st.checkbox("Mode formation : voir le modèle d'acceptation", key="mode_formation")
  formation = st.session_state.get("mode_formation", False)

  if "message_rfq" in st.session_state:
    ok, msg = st.session_state.pop("message_rfq")
    (st.success if ok else st.warning)(msg)

  # 1) Blotter : une ligne par RFQ
  lignes_rfq = []
  court = {"Asset manager": "AM", "Corporate": "CORP", "Hedge fund": "HF", "Fonds de vol": "VOL"}
  for r in lot:
    if r.get("traitee"):
      statut = '<span class="g">ACCEPTÉ</span>' if r["accepte"] else '<span class="r">REFUSÉ</span>'
    else:
      statut = '<span class="a">À COTER</span>'
    sens = '<span class="g">ACHAT</span>' if r["sens"] == "achat" else '<span class="r">VENTE</span>'
    lignes_rfq.append({"#": r["id"], "Client": court.get(r.get("client"), r.get("client", "?")),
                       "Type": r["type"].upper(), "K": r["strike"], "Qté": r["qty"],
                       "Sens": sens, "Statut": statut})
  st.markdown(html_table(pd.DataFrame(lignes_rfq), {"K": ".0f"}), unsafe_allow_html=True)

  # 2) Choix de la RFQ
  ids = [r["id"] for r in lot]
  a_coter = [r["id"] for r in lot if not r.get("traitee")]
  defaut = a_coter[0] if a_coter else ids[0]
  if st.session_state.get("rfq_choisie") not in ids:
    st.session_state.pop("rfq_choisie", None)
  choix = st.segmented_control("RFQ", ids, default=defaut, format_func=lambda i: f"#{i}",
                               key="rfq_choisie", label_visibility="collapsed")
  if choix is None:
    choix = defaut
  rfq = next(r for r in lot if r["id"] == choix)

  # 3) Ticket de la RFQ choisie
  st.markdown(f'<div class="tk">TICKET #{rfq["id"]} · {rfq["type"].upper()} {rfq["strike"]} · {rfq["maturite"]} · '
              f'client {rfq["sens"]} ×{rfq["qty"]} · {rfq.get("client", "?")}</div>', unsafe_allow_html=True)

  if rfq.get("traitee"):
    statut = "✅ ACCEPTÉ" if rfq["accepte"] else "❌ REFUSÉ"
    st.write(f"Bid {rfq['bid']:.3f} / Ask {rfq['ask']:.3f} — {statut}")
    cotation_r = {"mid": rfq.get("mid", (rfq["bid"] + rfq["ask"]) / 2), "bid": rfq["bid"], "ask": rfq["ask"]}
    st.caption(explication(rfq, cotation_r, rfq["accepte"], detail=formation))
  else:
    base = spread_base(rfq.get("client"))
    suggere = spread_suggere(rfq.get("client"), mk, base)
    spread_defaut = round(suggere * 100 * 2) / 2   # pas de 0,5 comme le slider
    delta_apres, vega_apres = risque_apres_trade(rfq, surface, spot_actuel, total_delta, total_vega, r=R)
    skew_defaut = round(skew_suggere(rfq, total_delta, total_vega, delta_apres, vega_apres) * 100 * 2) / 2
    st.caption(f"Spread suggéré : {suggere * 100:.1f} % · skew suggéré : {skew_defaut} %")

    s1, s2 = st.columns(2)
    spread = s1.slider("Spread %", 1.0, 15.0, spread_defaut, step=0.5, key=f"spread_{rfq['id']}") / 100
    skew = s2.slider("Skew %", -5.0, 5.0, skew_defaut, step=0.5, key=f"skew_{rfq['id']}") / 100

    apercu = coter(rfq, surface, spread=spread, skew=skew)
    if rfq["sens"] == "achat":
      edge = (apercu["ask"] - apercu["mid"]) * rfq["qty"] * MULTIPLICATEUR_OPTION
    else:
      edge = (apercu["mid"] - apercu["bid"]) * rfq["qty"] * MULTIPLICATEUR_OPTION
    bloquees = trade_bloque(total_delta, total_vega, delta_apres, vega_apres)
    cls_d = "r" if abs(delta_apres) > LIMITE_DELTA else "w"
    cls_v = "r" if abs(vega_apres) > LIMITE_VEGA else "w"

    st.markdown(
      f'<div class="rw"><span class="d">MID / BID / ASK</span><span class="w">{apercu["mid"]:.3f} / {apercu["bid"]:.3f} / {apercu["ask"]:.3f}</span></div>'
      f'<div class="rw"><span class="d">EDGE SI ACCEPTÉ</span><span class="{couleur(edge)}">{edge:+,.2f} $</span></div>'
      f'<div class="rw"><span class="d">FRAIS</span><span class="w">{frais_option(rfq["qty"]):.2f} $</span></div>'
      f'<div class="rw"><span class="d">DELTA AVANT → APRÈS</span><span class="{cls_d}">{total_delta:+,.1f} → {delta_apres:+,.1f} (±{LIMITE_DELTA:.0f})</span></div>'
      f'<div class="rw"><span class="d">VEGA AVANT → APRÈS</span><span class="{cls_v}">{total_vega:+,.1f} → {vega_apres:+,.1f} (±{LIMITE_VEGA:.0f})</span></div>',
      unsafe_allow_html=True)

    if edge < 0:
      st.error("Edge négatif : tu cèdes du spread au client.")
    for m in bloquees:
      st.error(f"Trade bloqué : {m}")
    if formation:
      proba, ecart, seuil = proba_acceptation(rfq, apercu)
      st.caption(f"[Mode formation] Acceptation estimée : {round(proba * 100)} % · écart {round(ecart * 100, 1)} % vs seuil {round(seuil * 100, 1)} %")

    if st.button(f"QUOTE #{rfq['id']}", disabled=bool(bloquees)):
      with st.spinner("Le client réfléchit…"):
        time.sleep(1.5)
      cotation = coter(rfq, surface, spread=spread, skew=skew)
      accepte = decision_client(rfq, cotation)
      if accepte:
        executer_rfq(rfq, cotation, spot=spot_actuel)
      marquer_traitee(rfq["id"], cotation, accepte)
      st.session_state["message_rfq"] = (accepte, explication(rfq, cotation, accepte, detail=formation))
      st.rerun()

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

    formats_book = {"Strike": ".0f", "Qté": "+.0f", "Entrée": ".2f", "Valeur": ".2f",
                    "P&L ($)": "+,.0f", "Delta": "+,.0f", "Vega": "+,.0f"}
    st.markdown(html_table(df_book, formats_book, colonnes_couleur=("P&L ($)",)), unsafe_allow_html=True)

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

# --- Greeks + limites ---
with onglet_risque:
 st.subheader("Greeks du book")

 def ligne(label, valeur, pct=None, cls="w"):
     barre = ""
     if pct is not None:
         coul = "#2ee66b" if pct < 60 else "#ff9f1a" if pct < 100 else "#ff4d4d"
         barre = f'<div class="lim"><i style="width:{max(min(pct, 100), 1):.0f}%;background:{coul}"></i></div>'
     return f'<div class="rw"><span class="a">{label}</span><span class="{cls}">{valeur}</span></div>{barre}'

 html = (
     ligne("DELTA", f"{total_delta:+,.1f} {TICKER}", abs(total_delta) / LIMITE_DELTA * 100)
     + ligne("GAMMA", f"{total_gamma:+,.2f} {TICKER}/$")
     + ligne("VEGA", f"{total_vega:+,.1f} $/vol", abs(total_vega) / LIMITE_VEGA * 100)
     + ligne("THETA", f"{total_theta:+,.1f} $/jour", cls=couleur(total_theta))
     + ligne("PIRE STRESS (GRILLE)", f"{pire_pnl:+,.0f} / {LIMITE_STRESS:,.0f} $",
             abs(min(pire_pnl, 0)) / LIMITE_STRESS * 100, cls=couleur(pire_pnl))
 )
 st.markdown(html, unsafe_allow_html=True)
 st.caption(f"Pire case de la grille : {TICKER} {pire_spot_lbl}, {pire_vol_lbl}")

 for msg in limites_depassees:
     st.error(msg)

with onglet_hedge:
 st.subheader("Hedge")

 # --- Hedge du vega ---
 hedge_v = hedge_vega_suggere(total_vega, surface, spot_actuel, R)
 if hedge_v is None:
    st.caption("VEGA : aucune option de référence disponible pour hedger.")
 else:
    if hedge_vega_necessaire(total_vega):
        etat_v = f'<span class="a">AU-DESSUS DU SEUIL (±{SEUIL_HEDGE_VEGA:.0f})</span>'
    else:
        etat_v = f'<span class="g">sous le seuil (±{SEUIL_HEDGE_VEGA:.0f})</span>'
    st.markdown(
        f'<div class="rw"><span class="a">VEGA</span>{etat_v}</div>'
        f'<div class="d" style="font-size:12px;margin:3px 0 6px">Suggéré : {hedge_v["qty"]:+d} {hedge_v["type"]} '
        f'{hedge_v["strike"]} · {hedge_v["maturite"]} · vega/contrat {hedge_v["vega_contrat"]:.1f} $</div>',
        unsafe_allow_html=True)
    cv1, cv2 = st.columns(2)
    qty_vega = cv1.number_input("Contrats", value=int(hedge_v["qty"]), step=1,
                                key=f"qty_hedge_vega_{hedge_v['qty']}", label_visibility="collapsed")
    if cv2.button("HEDGE VEGA", disabled=(qty_vega == 0)):
        executer_hedge_vega({**hedge_v, "qty": int(qty_vega)}, surface, R, spot_actuel)
        st.rerun()

 # --- Hedge du delta ---
 hedge_qty = hedge_delta(total_delta)
 if hedge_necessaire(total_delta):
    etat_d = f'<span class="a">AU-DESSUS DU SEUIL (±{SEUIL_HEDGE})</span>'
 else:
    etat_d = f'<span class="g">sous le seuil (±{SEUIL_HEDGE})</span>'
 st.markdown(
    f'<div class="rw" style="margin-top:10px"><span class="a">DELTA</span>{etat_d}</div>'
    f'<div class="d" style="font-size:12px;margin:3px 0 6px">Suggéré : {hedge_qty:+.1f} actions {TICKER}</div>',
    unsafe_allow_html=True)
 cd1, cd2 = st.columns(2)
 qty_delta = cd1.number_input("Actions", value=int(round(hedge_qty)), step=10,
                              key=f"qty_hedge_delta_{round(hedge_qty)}", label_visibility="collapsed")
 if cd2.button("HEDGE DELTA", disabled=(qty_delta == 0)):
    ajouter_hedge(qty=int(qty_delta), prix=spot_actuel, date_entree=str(date.today()))
    st.rerun()

# --- Scénario ---
with onglet_scenario:
    st.subheader("Stress test · P&L du book ($)")
    st.markdown(heatmap_html(df_stress, LIMITE_STRESS), unsafe_allow_html=True)
    st.caption(f"Plus la case est foncée, plus la perte approche la limite ({LIMITE_STRESS:,.0f} $).")

    st.subheader("Scénario : et si le marché bouge ?")
    s1, s2, s3 = st.columns(3)
    dS = s1.slider(f"{TICKER} (%)", -5.0, 5.0, 0.0, step=0.5) / 100 * spot_actuel
    dvol = s2.slider("Vol (pts)", -5.0, 5.0, 0.0, step=0.5)
    dt = s3.slider("Jours", 0, 10, 1)

    p_delta, p_gamma, p_vega, p_theta, p_total = pnl_explain(
        total_delta, total_gamma, total_vega, total_theta, dS, dvol, dt)
    lignes_scen = "".join(
        f'<div class="rw"><span class="a">{nom}</span><span class="{couleur(v)}">{v:+,.0f} $</span></div>'
        for nom, v in [("DELTA", p_delta), ("GAMMA", p_gamma), ("VEGA", p_vega), ("THETA", p_theta)])
    lignes_scen += f'<div class="rw" style="font-weight:700"><span class="w">TOTAL</span><span class="{couleur(p_total)}">{p_total:+,.0f} $</span></div>'
    st.markdown(lignes_scen, unsafe_allow_html=True)


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