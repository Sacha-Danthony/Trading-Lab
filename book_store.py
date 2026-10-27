import json
import os

from data import get_spot_price, get_cloture
from book_greeks import valeur_position, multiplicateur
from couts import frais_action, frais_option
from config import TICKER
from datetime import date

FICHIER_FERMEES = "fermees.json"

FICHIER_BOOK = "book.json"


def charger_book():
    if not os.path.exists(FICHIER_BOOK):
        return []
    with open(FICHIER_BOOK, "r") as f:
        contenu = f.read()
        if not contenu.strip():
            return []
        return json.loads(contenu)


def sauvegarder_book(book):
    with open(FICHIER_BOOK, "w") as f:
        json.dump(book, f, indent=2)

def charger_fermees():
    if not os.path.exists(FICHIER_FERMEES):
        return []
    with open(FICHIER_FERMEES, "r") as f:
        contenu = f.read()
        if not contenu.strip():
            return []
        return json.loads(contenu)


def sauvegarder_fermees(fermees):
    with open(FICHIER_FERMEES, "w") as f:
        json.dump(fermees, f, indent=2)


def pnl_realise_total():
    return sum(p["pnl_realise"] for p in charger_fermees())

def _frais(type_option, qty):
    return frais_action(qty) if type_option == "stock" else frais_option(qty)


def ajouter_position(type_option, strike, maturite, qty, prix_entree, date_entree, client=None, mid_entree=None, spot_entree=None):
    book = charger_book()
    nouvel_id = max([p["id"] for p in book], default=0) + 1

    position = {
        "id": nouvel_id,
        "type": type_option,
        "strike": strike,
        "maturite": maturite,
        "qty": qty,
        "prix_entree": prix_entree,
        "date_entree": date_entree,
        "frais": _frais(type_option, qty),
        "client": client,
        "mid_entree": mid_entree,
        "spot_entree": spot_entree,
    }

    book.append(position)
    sauvegarder_book(book)
    return position


def ajouter_hedge(qty, prix, date_entree):
    return ajouter_position(
        type_option="stock",
        strike=None,
        maturite=None,
        qty=qty,
        prix_entree=float(prix),
        date_entree=date_entree
    )


def fermer_position(id_position, prix_sortie):
    book = charger_book()

    position_fermee = None
    nouveau_book = []

    for position in book:
        if position["id"] == id_position:
            position_fermee = position
        else:
            nouveau_book.append(position)

    if position_fermee is None:
        return None

    frais_sortie = _frais(position_fermee["type"], position_fermee["qty"])
    pnl_realise = (prix_sortie - position_fermee["prix_entree"]) * position_fermee["qty"] * multiplicateur(position_fermee) \
    - position_fermee.get("frais", 0) - frais_sortie

    fermees = charger_fermees()
    fermees.append({**position_fermee,
                    "prix_sortie": prix_sortie,
                    "date_sortie": str(date.today()),
                    "pnl_realise": pnl_realise})
    sauvegarder_fermees(fermees)

    sauvegarder_book(nouveau_book)
    return pnl_realise


def pnl_non_realise(position, surface, r=0.05, S=None):
    """P&L latent : (valeur actuelle - prix d'entrée) x quantité x multiplicateur, moins les frais déjà payés."""
    if S is None:
        S = get_spot_price(TICKER)
    valeur_actuelle = valeur_position(position, surface, r, S)
    pnl = (valeur_actuelle - position["prix_entree"]) * position["qty"] * multiplicateur(position) - position.get("frais", 0)
    return pnl

def regler_expirations(ticker=TICKER):
    aujourdhui = str(date.today())
    messages = []
    for position in charger_book():
        if position["type"] == "stock" or position["maturite"] is None:
            continue
        if position["maturite"] < aujourdhui:
            spot = get_cloture(ticker, position["maturite"])
            if spot is None:
                continue
            K = position["strike"]
            valeur = max(spot - K, 0) if position["type"] == "call" else max(K - spot, 0)
            pnl = fermer_position(position["id"], valeur)
            messages.append(f"Échéance : #{position['id']} {position['type']} {K:.0f} réglé à {valeur:.2f} "
                            f"(clôture {spot:.2f}) · P&L {pnl:+,.0f} $")
    return messages
