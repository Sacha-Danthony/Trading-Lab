# Frais de transaction (hypothèses de simulation, à sourcer auprès d'un broker réel)
FRAIS_OPTION_PAR_CONTRAT = 0.65   # 0,65 $ par contrat, ramené à l'option (1 contrat = 100 options)
FRAIS_ACTION_PAR_ACTION = 0.005         # 0,005 $ par action


def frais_option(qty):
    return abs(qty) * FRAIS_OPTION_PAR_CONTRAT


def frais_action(qty):
    return abs(qty) * FRAIS_ACTION_PAR_ACTION
