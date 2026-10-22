"""Remet le lab à zéro : book vide, nouveau lot de RFQ au prochain lancement, journal vide.
La surface sauvegardée (surface.json) est conservée."""
import os

for f in ("book.json", "flow.json", "journal.json", "fermees.json", "historique.json"):
    if os.path.exists(f):
        os.remove(f)
        print("supprimé :", f)
print("Lab remis à zéro.")
