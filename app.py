import streamlit as st
from datetime import date, datetime
from flow_store import obtenir_lot_du_jour, marquer_traitee,charger_historique_rfq, stats_rfq
from book_store import charger_book, pnl_non_realise, fermer_position, ajouter_hedge, regler_expirations, pnl_realise_total, charger_fermees
from vol_surface import construire_surface, sauvegarder_surface, charger_surface, calculer_T, get_vol
from quoting import coter, decision_client, executer_rfq, proba_acceptation, explication 
from book_greeks import (delta_net_book, gamma_net_book, vega_net_book, theta_net_book,
                         valeur_position, hedge_delta,delta_position, gamma_position, vega_position, valeur_modele, multiplicateur)
from limites import (verifier_limites, risque_apres_trade, trade_bloque, hedge_necessaire, skew_suggere, hedge_vega_necessaire,
                         LIMITE_STRESS, LIMITE_DELTA, LIMITE_VEGA, grille_stress_complete, SEUIL_HEDGE, SEUIL_HEDGE_VEGA)
from data import get_spot_price, get_historique_spot,PERIODES
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
from html import escape
import altair as alt
import numpy as np

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
.kp { display:flex; gap:28px; margin:4px 0 6px; }
.kp small { display:block; color:#777; font-size:11px; letter-spacing:.08em; }
.kp b { font-size:22px; }
.jr table.t td { white-space: normal; }
.sb { position:fixed; left:0; right:0; bottom:0; height:26px; background:#111; border-top:1px solid #333;
      display:flex; gap:28px; align-items:center; padding:0 14px; font-size:12px; color:#777; z-index:999; }
.sb b { color:#e8e8e8; font-weight:400; }
[data-testid="stMainBlockContainer"] { padding-bottom: 40px; }
[data-testid="stMarkdownContainer"] { overflow-x: auto; }
[data-testid="stElementToolbar"] { display: none; }
</style>
""", unsafe_allow_html=True)


lot = obtenir_lot_du_jour()

# --- Règlement des options arrivées à échéance (AVANT de construire la surface) ---
for msg in regler_expirations():
    st.toast(msg)

aujourdhui = str(date.today())
maturites_besoin = sorted(set(
    [p["maturite"] for p in charger_book() if p["maturite"] and p["maturite"] >= aujourdhui]
    + [r["maturite"] for r in lot if r["maturite"] >= aujourdhui]
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

def signe(x):
    x = round(x)
    return f"{x:+,}" if x != 0 else "0"

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
            if txt.lstrip("+-") .replace("0", "").replace(".", "").replace(",", "") == "":
                txt = txt.lstrip("+-")
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

def courbe_html(valeurs, etiquettes, coul="#ff9f1a", w=520, h=170):
    if len(valeurs) < 2:
        return ""
    g, d, haut, bas = 52, 10, 10, 22          # marges : gauche, droite, haut, bas
    mn, mx = min(valeurs + [0]), max(valeurs + [0])
    ecart = (mx - mn) or 1

    def x(i):
        return g + i * (w - g - d) / (len(valeurs) - 1)

    def y(v):
        return haut + (mx - v) / ecart * (h - haut - bas)

    svg = ""
    for k in range(5):                        # 5 niveaux horizontaux
        niv = mn + k * ecart / 4
        svg += (f'<line x1="{g}" y1="{y(niv):.1f}" x2="{w - d}" y2="{y(niv):.1f}" stroke="#222"/>'
                f'<text x="{g - 6}" y="{y(niv) + 3:.1f}" fill="#777" font-size="10" text-anchor="end">{niv:,.0f}</text>')
    svg += f'<line x1="{g}" y1="{y(0):.1f}" x2="{w - d}" y2="{y(0):.1f}" stroke="#555" stroke-dasharray="3,3"/>'
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(valeurs))
    svg += f'<polyline points="{pts}" fill="none" stroke="{coul}" stroke-width="2"/>'
    for i, (v, e) in enumerate(zip(valeurs, etiquettes)):
        svg += (f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" fill="{coul}"/>'
                f'<text x="{x(i):.1f}" y="{h - 6}" fill="#777" font-size="10" text-anchor="middle">{e[5:]}</text>')
    svg += (f'<text x="{x(len(valeurs) - 1):.1f}" y="{y(valeurs[-1]) - 8:.1f}" fill="#fff" '
            f'font-size="11" text-anchor="end">{valeurs[-1]:+,.0f} $</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}">{svg}</svg>'

def couleur_vol(v, lo=10, hi=30):
    t = max(0, min(1, (v - lo) / (hi - lo)))
    if t < 0.5:
        a, b, u = (20, 40, 90), (30, 110, 150), t * 2
    else:
        a, b, u = (30, 110, 150), (240, 170, 50), (t - 0.5) * 2
    r, g, bl = (int(a[i] + (b[i] - a[i]) * u) for i in range(3))
    return f"rgb({r},{g},{bl})"

# --- Limites (calculées AVANT le bandeau pour le voyant) ---
limites_depassees = verifier_limites(total_delta, total_vega)
df_stress = pd.DataFrame(grille_stress_complete(book, surface, spot_actuel, R)).T

pire_pnl = df_stress.min().min()
pire_vol_lbl, pire_spot_lbl = df_stress.stack().idxmin()
if pire_pnl < -LIMITE_STRESS:
    limites_depassees.append(f"Stress {round(pire_pnl):,} \\$ au-delà de la limite (−{round(LIMITE_STRESS):,} \\$)")

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

etat_limites = "rouge" if limites_depassees else "ambre" if seuils_hedge else "vert"
precedent = st.session_state.get("etat_limites")
if precedent is not None and etat_limites != precedent:
    if etat_limites == "rouge":
        st.toast("Limite dépassée : " + " · ".join(limites_depassees), icon="🔴")
    elif etat_limites == "ambre":
        st.toast("Seuil de hedge atteint : " + " · ".join(seuils_hedge), icon="🟠")
    else:
        st.toast("Toutes les limites sont de nouveau respectées", icon="🟢")
st.session_state["etat_limites"] = etat_limites

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
 onglet_flux = c_flux.container(border=False)
 onglet_book = c_book.container(border=False)
 onglet_risque = c_risque.container(border=False)
 onglet_hedge = c_risque.container(border=False)
with tab_analyse:
 onglet_spy, = st.columns(1)
 onglet_pnl, onglet_scenario, onglet_vol = st.columns([1.25, 1, 1.1], gap="small")
with tab_journal:
 onglet_journal = st.container()


# --- Flux client ---
with onglet_flux:
  st.subheader("Flux client du jour")
  st.checkbox("Mode formation : voir le modèle d'acceptation", key="mode_formation")
  formation = st.session_state.get("mode_formation", False)

  if "message_rfq" in st.session_state:
    ok, msg = st.session_state.pop("message_rfq")
    st.toast(msg, icon="✅" if ok else "❌")

  # 1) Blotter : une ligne par RFQ
  lignes_rfq = []
  court = {"Asset manager": "AM", "Corporate": "CORP", "Hedge fund": "HF", "Fonds de vol": "VOL"}
  for r in lot:
    if r.get("traitee"):
      if r.get("passe"):
        statut = '<span class="d">PASSÉ</span>'
      else:
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
    if rfq.get("passe"):
      st.write("⏸ PASSÉE : aucune cotation envoyée au client (décision du desk).")
      st.caption(f"Prix non envoyé (au moment de la décision) : bid {rfq['bid']:.3f} / ask {rfq['ask']:.3f}")
    else:
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

    b1, b2 = st.columns(2)
    if b1.button(f"QUOTE #{rfq['id']}", disabled=bool(bloquees)):
      with st.spinner("Le client réfléchit…"):
        time.sleep(1.5)
      cotation = coter(rfq, surface, spread=spread, skew=skew)
      accepte = decision_client(rfq, cotation)
      if accepte:
        executer_rfq(rfq, cotation, spot=spot_actuel)
      marquer_traitee(rfq["id"], cotation, accepte)
      st.session_state["message_rfq"] = (accepte, explication(rfq, cotation, accepte, detail=formation))
      st.rerun()
    if b2.button(f"PASSER #{rfq['id']}"):
      marquer_traitee(rfq["id"], apercu, False, passe=True)
      st.session_state["message_rfq"] = (False, f"RFQ #{rfq['id']} passée : pas de cotation envoyée au client.")
      st.rerun()

    
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
            "Gamma": round(gamma_position(p, surface, R, spot_actuel) * p["qty"] * mult, 2),
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
            "Gamma": 0.0,
            "Vega": 0.0,
        })

    tot_pnl = sum(l["P&L ($)"] for l in lignes_book)
    tot_delta = sum(l["Delta"] for l in lignes_book)
    tot_gamma = sum(l["Gamma"] for l in lignes_book)
    tot_vega = sum(l["Vega"] for l in lignes_book)
    lignes_book.append({
        "#": None, "Type": "TOTAL", "Strike": "", "Échéance": "",
        "Qté": None, "Entrée": None, "Valeur": None,
        "P&L ($)": round(tot_pnl, 2),
        "Delta": round(tot_delta, 1),
        "Gamma": round(tot_gamma, 2),
        "Vega": round(tot_vega, 1),
    })
    df_book = pd.DataFrame(lignes_book)
    formats_book = {"Strike": ".0f", "Qté": "+,.0f", "Entrée": ".2f", "Valeur": ".2f",
                    "P&L ($)": "+,.0f", "Delta": "+,.0f", "Gamma": "+,.2f", "Vega": "+,.0f"}
    df_book["#"] = df_book["#"].apply(lambda x: "" if x is None or pd.isna(x) else str(x))

    formats_book = {"Strike": ".0f", "Qté": "+.0f", "Entrée": ".2f", "Valeur": ".2f",
                    "P&L ($)": "+,.0f", "Delta": "+,.0f", "Vega": "+,.0f"}
    st.markdown(html_table(df_book, formats_book, colonnes_couleur=("P&L ($)", "Gamma")), unsafe_allow_html=True)

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
    st.caption(f"Revalorisation complète de chaque option. Plus la case est foncée, plus la perte approche la limite ({LIMITE_STRESS:,.0f} $).")

    st.subheader("Scénario : et si le marché bouge ?")
    s1, s2, s3 = st.columns(3)
    dS = s1.slider(f"{TICKER} (%)", -5.0, 5.0, 0.0, step=0.5) / 100 * spot_actuel
    dvol = s2.slider("Vol (pts)", -5.0, 5.0, 0.0, step=0.5)
    dt = s3.slider("Jours", 0, 10, 1)

    # Approximation par les grecques : utile pour voir d'où vient le P&L
    p_delta, p_gamma, p_vega, p_theta, p_total = pnl_explain(
        total_delta, total_gamma, total_vega, total_theta, dS, dvol, dt)

    # Revalorisation complète : chaque option est repricée dans le scénario
    valeur_base = sum(valeur_modele(p, surface, R, spot_actuel) * p["qty"] * multiplicateur(p) for p in book)
    valeur_scen = sum(valeur_modele(p, surface, R, spot_actuel + dS, choc_vol=dvol, jours=dt) * p["qty"] * multiplicateur(p) for p in book)
    p_reval = valeur_scen - valeur_base

    lignes_scen = "".join(
        f'<div class="rw"><span class="a">{nom}</span><span class="{couleur(round(v))}">{signe(v)} $</span></div>'
        for nom, v in [("DELTA", p_delta), ("GAMMA", p_gamma), ("VEGA", p_vega), ("THETA", p_theta)])
    lignes_scen += (f'<div class="rw"><span class="d">TOTAL (APPROX. GRECQUES)</span>'
                    f'<span class="{couleur(round(p_total))}">{signe(p_total)} $</span></div>')
    lignes_scen += (f'<div class="rw" style="font-weight:700"><span class="w">TOTAL (REVALORISATION)</span>'
                    f'<span class="{couleur(round(p_reval))}">{signe(p_reval)} $</span></div>')
    st.markdown(lignes_scen, unsafe_allow_html=True)
    st.caption("Le détail par grecque est une approximation ; le total en revalorisation est le chiffre de référence. "
               "L'écart entre les deux vient des effets que les grecques ne captent pas (gamma qui change, vanna, volga).")


# --- Cours du SPY ---
with onglet_spy:
    st.subheader(f"{TICKER} · cours")
    c_per, c_type = st.columns([3, 2])
    periode = c_per.segmented_control("Période", list(PERIODES), default="1J",
                                      key="periode_spy", label_visibility="collapsed") or "1J"
    type_g = c_type.segmented_control("Type", ["Ligne", "Chandeliers"], default="Ligne",
                                      key="type_spy", label_visibility="collapsed") or "Ligne"
    h = get_historique_spot(TICKER, periode)
    if len(h) >= 2:
        ouv, haut, bas, der = h["Open"].iloc[0], h["High"].max(), h["Low"].min(), h["Close"].iloc[-1]
        var = (der / ouv - 1) * 100
        st.markdown(
            f'<div class="kp"><div><small>OUVERTURE</small><b class="w">{ouv:.2f}</b></div>'
            f'<div><small>PLUS HAUT</small><b class="w">{haut:.2f}</b></div>'
            f'<div><small>PLUS BAS</small><b class="w">{bas:.2f}</b></div>'
            f'<div><small>DERNIER</small><b class="w">{der:.2f}</b></div>'
            f'<div><small>VARIATION</small><b class="{couleur(var)}">{var:+.2f} %</b></div>'
            f'<div><small>VOLUME</small><b class="w">{h["Volume"].sum() / 1e6:,.1f} M</b></div></div>',
            unsafe_allow_html=True)

        clotures = get_historique_spot(TICKER, "3M")["Close"]
        rendements = np.log(clotures / clotures.shift(1)).dropna()
        vol_real = rendements.tail(20).std() * np.sqrt(252) * 100
        vol_impl = get_vol(K=round(spot_actuel), T=30 / 365, surface=surface)
        if vol_impl is not None:
            vol_impl = vol_impl * 100
            ecart = vol_impl - vol_real
            st.markdown(
                f'<div class="kp"><div><small>VOL RÉALISÉE 20J</small><b class="w">{vol_real:.1f} %</b></div>'
                f'<div><small>VOL IMPLICITE ATM 30J</small><b class="w">{vol_impl:.1f} %</b></div>'
                f'<div><small>IMPLICITE − RÉALISÉE</small><b class="a">{ecart:+.1f} pts</b></div></div>',
                unsafe_allow_html=True)
        duree = {"1J": "5 minutes", "5J": "30 minutes"}.get(periode, "1 jour")
        st.caption(f"1 bougie = {duree} · heure de New York · données Yahoo retardées · molette pour zoomer, glisser pour se déplacer")

        df_c = h.reset_index()
        df_c = df_c.rename(columns={df_c.columns[0]: "Date"})
        df_c["Date"] = df_c["Date"].dt.tz_localize(None)
        df_c["i"] = range(len(df_c))
        format_x = {"1J": "%H:%M", "5J": "%d/%m %H:%M"}.get(periode, "%d/%m")
        etiquettes = df_c["Date"].dt.strftime(format_x).tolist()
        pas = max(1, len(df_c) // 8)
        expr = "[" + ",".join(f"'{e}'" for e in etiquettes) + "][datum.value]"
        base = alt.Chart(df_c).encode(x=alt.X("i:Q", title=None, scale=alt.Scale(nice=False, padding=8),
                                              axis=alt.Axis(values=list(range(0, len(df_c), pas)), labelExpr=expr)))
        echelle = alt.Scale(zero=False)
        infos = [alt.Tooltip("Date:T", title="Date", format="%d/%m %H:%M"),
                 alt.Tooltip("Open:Q", title="Ouverture", format=".2f"),
                 alt.Tooltip("High:Q", title="Haut", format=".2f"),
                 alt.Tooltip("Low:Q", title="Bas", format=".2f"),
                 alt.Tooltip("Close:Q", title="Clôture", format=".2f")]

        if type_g == "Ligne":
            trace = base.mark_line(color="#ff9f1a", strokeWidth=1.6).encode(y=alt.Y("Close:Q", title=None, scale=echelle))
        else:
            coul = alt.condition("datum.Close >= datum.Open", alt.value("#2ee66b"), alt.value("#ff4d4d"))
            largeur = max(2, min(8, int(900 / len(df_c))))
            meches = base.mark_rule().encode(y=alt.Y("Low:Q", title=None, scale=echelle), y2="High:Q", color=coul)
            corps = base.mark_bar(size=largeur).encode(y="Open:Q", y2="Close:Q", color=coul)
            trace = meches + corps

        survol = alt.selection_point(on="pointerover", nearest=True, fields=["Date"], empty=False)
        points = base.mark_point(opacity=0).encode(y="Close:Q", tooltip=infos).add_params(survol)
        ligne_v = base.mark_rule(color="#777").encode(opacity=alt.condition(survol, alt.value(1), alt.value(0)))
        graphe = (trace + points + ligne_v).properties(height=260, background="#050505").interactive(bind_y=False)
        graphe = graphe.configure_axis(
            labelFont="DejaVu Sans Mono, Consolas, monospace", labelColor="#ff9f1a", labelFontSize=11,
            gridColor="#1a1a1a", domainColor="#333", tickColor="#333",
        ).configure_view(strokeWidth=0)
        st.altair_chart(graphe, use_container_width=True)
    else:
        st.caption("Pas de données disponibles pour cette période.")


# --- P&L ---
with onglet_pnl:
    st.subheader("P&L du book")

    pnl_total = 0
    for position in book:
        pnl = pnl_non_realise(position, surface, S=spot_actuel)
        pnl_total = pnl_total + pnl
    realise = pnl_realise_total()

    st.markdown(
        f'<div class="kp"><div><small>NON RÉALISÉ</small><b class="{couleur(pnl_total)}">{pnl_total:+,.0f} $</b></div>'
        f'<div><small>RÉALISÉ</small><b class="{couleur(realise)}">{realise:+,.0f} $</b></div>'
        f'<div><small>TOTAL</small><b class="{couleur(pnl_total + realise)}">{pnl_total + realise:+,.0f} $</b></div></div>',
        unsafe_allow_html=True)
    st.caption("Non réalisé = valeur actuelle des positions ouvertes − prix d'entrée, frais déduits.")

    st.markdown('<div class="a" style="margin-top:8px;font-size:13px">POSITIONS FERMÉES</div>', unsafe_allow_html=True)
    fermees = charger_fermees()
    if fermees:
        df_f = pd.DataFrame([{"#": f["id"], "Type": f["type"], "K": f["strike"], "Qté": f["qty"],
                              "Entrée": f["prix_entree"], "Sortie": f["prix_sortie"],
                              "Date": str(f["date_sortie"])[5:], "P&L": f["pnl_realise"]} for f in fermees])
        st.markdown(html_table(df_f, {"K": ".0f", "Qté": "+.0f", "Entrée": ".2f", "Sortie": ".2f",
                                      "P&L": "+,.0f"}, colonnes_couleur=("P&L",)),
                    unsafe_allow_html=True)
    else:
        st.caption("Aucune position fermée pour l'instant.")

    enregistrer_snapshot(spot_actuel, total_delta, total_gamma, total_vega, total_theta,
                         pnl_total, realise)

   # --- Markout par client ---
    st.subheader("Markout par client")
    if mk:
        df_mk = pd.DataFrame([{"Client": c, "N": v["nb"],
                               "Spread": v["spread_capte"],
                               "Markout": v["markout"],
                               "Après hedge": v["markout_hedge"],
                               "Net": v["spread_capte"] + v["markout_hedge"]} for c, v in mk.items()])
        cols_mk = ("Spread", "Markout", "Après hedge", "Net")
        st.markdown(html_table(df_mk, {c: "+,.0f" for c in cols_mk}, colonnes_couleur=cols_mk),
                    unsafe_allow_html=True)
        st.caption("Montants en $. Après hedge = markout brut moins l'effet du delta : ce que ton hedge ne couvre pas.")
    else:
        st.caption("Pas encore de trades avec un client identifié.")

# --- Historique ---
with onglet_pnl:
    st.subheader("Historique du desk")
    historique = charger_historique()
    if len(historique) >= 2:
        st.markdown(courbe_html([e["pnl_total"] for e in historique], [e["date"] for e in historique]),
                    unsafe_allow_html=True)
    else:
        st.caption("La courbe apparaîtra dès que tu auras au moins 2 jours d'historique.")

    attribution = expliquer_pnl(historique)
    st.subheader("D'où vient le P&L ?")
    if attribution:
        df_attr = pd.DataFrame([{"Date": l["date"], "Variation": l["variation"], "Delta": l["delta"],
                                 "Gamma": l["gamma"], "Theta": l["theta"], "Résidu": l["residu"]}
                                for l in attribution])
        cols_attr = ("Variation", "Delta", "Gamma", "Theta", "Résidu")
        st.markdown(html_table(df_attr, {c: "+,.0f" for c in cols_attr}, colonnes_couleur=cols_attr),
                    unsafe_allow_html=True)
        st.caption("Montants en $. Résidu = vega, spread des nouveaux trades, frais et hedges : tout ce que le delta, "
                   "le gamma et le theta du snapshot précédent n'expliquent pas.")
    else:
        st.caption("Il faut au moins 2 jours de snapshots pour expliquer le P&L.")

# --- Journal ---
with onglet_journal:
    st.subheader("Journal de trading")

    c_txt, c_btn = st.columns([5, 1])
    texte = c_txt.text_area("Qu'as-tu fait aujourd'hui, et pourquoi ?", height=80)
    if c_btn.button("ENREGISTRER"):
        if texte.strip():
            greeks = {
                "delta": round(total_delta, 2),
                "gamma": round(total_gamma, 4),
                "vega": round(total_vega, 2),
                "theta": round(total_theta, 2)
            }
            ajouter_entree(texte, greeks)
            st.rerun()

    entrees = list(reversed(charger_journal()))
    if entrees:
        df_j = pd.DataFrame([{"Date": e["date"], "Note": escape(e["texte"]),
                              "Delta": e["greeks"]["delta"], "Gamma": e["greeks"]["gamma"],
                              "Vega": e["greeks"]["vega"], "Theta": e["greeks"]["theta"]} for e in entrees])
        st.markdown('<div class="jr">' + html_table(df_j, {"Delta": "+,.1f", "Gamma": "+,.2f",
                    "Vega": "+,.1f", "Theta": "+,.1f"}) + "</div>", unsafe_allow_html=True)
    else:
        st.caption("Aucune entrée pour l'instant.")

# --- Vol ---
with onglet_vol:
    st.subheader("Surface de volatilité")
    st.caption(f"Calibration : {st.session_state.date_calibration} · options OTM (puts sous le spot, calls au-dessus)")

    # Heatmap : maturités (lignes) × strikes (colonnes)
    strikes_hm = list(range(round(spot_actuel * 0.9 / 10) * 10, round(spot_actuel * 1.1 / 10) * 10 + 1, 20))
    entete = "<tr><th></th>" + "".join(f"<th>{k}</th>" for k in strikes_hm) + "</tr>"
    lignes_hm = ""
    for m in sorted(surface.keys()):
        T = calculer_T(m)
        cases = ""
        for k in strikes_hm:
            v = get_vol(K=k, T=T, surface=surface)
            if v is None:
                cases += "<td></td>"
            else:
                cases += f'<td style="background:{couleur_vol(v * 100)};color:#fff;text-align:center">{v * 100:.1f}</td>'
        lignes_hm += f'<tr><td class="d">{round(T * 365)}J</td>{cases}</tr>'
    st.markdown(f'<table class="t">{entete}{lignes_hm}</table>', unsafe_allow_html=True)

    # Structure par terme : vol ATM par échéance
    lignes_vol = []
    for m in sorted(surface.keys()):
        T = calculer_T(m)
        vol_atm = get_vol(K=round(spot_actuel), T=T, surface=surface)
        if vol_atm is not None:
            lignes_vol.append({"Échéance": m, "Jours": round(T * 365), "Vol ATM (%)": vol_atm * 100})
    st.markdown('<div class="a" style="margin-top:10px;font-size:13px">STRUCTURE PAR TERME (ATM)</div>', unsafe_allow_html=True)
    st.markdown(html_table(pd.DataFrame(lignes_vol), {"Vol ATM (%)": ".2f"}), unsafe_allow_html=True)

    # Smile par échéance
    dates_smile = sorted(surface.keys())
    pas = max(1, len(dates_smile) // 4)
    dates_smile = dates_smile[::pas][:4]
    strikes_grille = list(range(round(spot_actuel * 0.9), round(spot_actuel * 1.1) + 1, 5))
    courbes = {}
    for m in dates_smile:
        T = calculer_T(m)
        vols = [get_vol(K=k, T=T, surface=surface) for k in strikes_grille]
        courbes[m] = [None if v is None else v * 100 for v in vols]
    st.markdown('<div class="a" style="margin-top:10px;font-size:13px">SMILE PAR ÉCHÉANCE (VOL %, SELON LE STRIKE)</div>', unsafe_allow_html=True)
    couleurs_smile = ["#ff9f1a", "#3fd0ff", "#ffffff", "#ff5fc8"]
    st.line_chart(pd.DataFrame(courbes, index=strikes_grille), color=couleurs_smile[:len(courbes)])

    # --- Barre d'état ---
nb_a_coter = sum(1 for r in lot if not r.get("traitee"))
if limites_depassees:
    txt_lim = f'<b class="r">{len(limites_depassees)} DÉPASSÉE(S)</b>'
else:
    txt_lim = '<b class="g">OK</b>'
st.markdown(
    f'<div class="sb">'
    f'<span>POSITIONS <b>{len(book)}</b></span>'
    f'<span>RFQ À COTER <b>{nb_a_coter}</b> / {len(lot)}</span>'
    f'<span>LIMITES {txt_lim}</span>'
    f'<span>SURFACE <b>{st.session_state.date_calibration}</b></span>'
    f'<span>DONNÉES <b>Yahoo, retardées</b></span>'
    f'<span style="margin-left:auto">PAGE CALCULÉE À {maintenant}</span>'
    f'</div>', unsafe_allow_html=True)
