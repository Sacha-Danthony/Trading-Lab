import numpy as np
from scipy.stats import norm


def calculer_d1_d2(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + sigma ** 2 / 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2


def prix_call(S, K, T, r, sigma):
    d1, d2 = calculer_d1_d2(S, K, T, r, sigma)
    prix = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return prix


def prix_put(S, K, T, r, sigma):
    d1, d2 = calculer_d1_d2(S, K, T, r, sigma)
    prix = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return prix


def delta_call(S, K, T, r, sigma):
    d1, d2 = calculer_d1_d2(S, K, T, r, sigma)
    return norm.cdf(d1)


def delta_put(S, K, T, r, sigma):
    d1, d2 = calculer_d1_d2(S, K, T, r, sigma)
    return norm.cdf(d1) - 1


def gamma(S, K, T, r, sigma):
    # identique pour call et put
    d1, d2 = calculer_d1_d2(S, K, T, r, sigma)
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))


def vega(S, K, T, r, sigma):
    # identique pour call et put ; divisé par 100 = sensibilité à +1 point de vol
    d1, d2 = calculer_d1_d2(S, K, T, r, sigma)
    return S * norm.pdf(d1) * np.sqrt(T) / 100


def theta_call(S, K, T, r, sigma):
    # divisé par 365 = perte de valeur par jour calendaire
    d1, d2 = calculer_d1_d2(S, K, T, r, sigma)
    theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
    return theta


def theta_put(S, K, T, r, sigma):
    d1, d2 = calculer_d1_d2(S, K, T, r, sigma)
    theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
    return theta


if __name__ == "__main__":
    # test rapide : call ATM 1 an, vol 20 %, r 5 %  -> prix attendu ~ 10.45 pour S=K=100
    print(prix_call(100, 100, 1, 0.05, 0.2))
    print(delta_call(100, 100, 1, 0.05, 0.2), gamma(100, 100, 1, 0.05, 0.2), vega(100, 100, 1, 0.05, 0.2))
