


def pnl_explain(delta_net, gamma_net, vega_net, theta_net, dS, dvol, dt):
    """Explique le P&L d'un book par les Greeks : delta, gamma, vega, theta.
    dS en $, dvol en points de vol, dt en jours."""
    pnl_delta = delta_net * dS
    pnl_gamma = 0.5 * gamma_net * dS ** 2
    pnl_vega = vega_net * dvol
    pnl_theta = theta_net * dt
    pnl_total = pnl_delta + pnl_gamma + pnl_vega + pnl_theta
    return pnl_delta, pnl_gamma, pnl_vega, pnl_theta, pnl_total



  