import json
import os
from datetime import datetime

FICHIER_JOURNAL = "journal.json"


def charger_journal():
    if not os.path.exists(FICHIER_JOURNAL):
        return []
    with open(FICHIER_JOURNAL, "r") as f:
        contenu = f.read()
        if not contenu.strip():
            return []
        return json.loads(contenu)


def sauvegarder_journal(journal):
    with open(FICHIER_JOURNAL, "w") as f:
        json.dump(journal, f, indent=2)


def ajouter_entree(texte, greeks):
    journal = charger_journal()

    entree = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "texte": texte,
        "greeks": greeks
    }

    journal.append(entree)
    sauvegarder_journal(journal)
    return entree
