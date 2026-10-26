import yfinance as yf
from config import TICKER
from datetime import datetime, timedelta
import streamlit as st

@st.cache_data(ttl=300)
def get_spot_price(ticker: str = TICKER) -> float:
    """Dernier prix de clôture du sous-jacent."""
    data = yf.download(ticker, period="5d", progress=False)
    spot = data["Close"].iloc[-1].item()
    return float(spot)


@st.cache_data(ttl=300)
def get_maturites(ticker: str = TICKER):
    """Dates d'échéance disponibles."""
    t = yf.Ticker(ticker)
    return t.options


@st.cache_data(ttl=300)
def get_option_chain(ticker: str = TICKER, maturite: str = None):
    """Calls et puts cotés pour une maturité."""
    t = yf.Ticker(ticker)
    if maturite is None:
        maturite = t.options[0]
    chain = t.option_chain(maturite)
    return chain.calls, chain.puts


def filtrer_options(df, spot):
    """Garde les options liquides : bid > 0, strike entre 80 % et 120 % du spot, spread relatif < 10 %."""
    df = df.copy()
    df["spread_rel"] = (df["ask"] - df["bid"]) / ((df["ask"] + df["bid"]) / 2)
    df_filtre = df[(df["bid"] > 0) & (df["strike"] > spot * 0.8) & (df["strike"] < spot * 1.2) & (df["spread_rel"] < 0.10)]
    return df_filtre


def get_prix_marche(ticker, maturite, strike, type_option):
    """Mid du marché pour une option précise, ou None si pas de cotation exploitable."""
    calls, puts = get_option_chain(ticker, maturite)
    df = calls if type_option == "call" else puts
    ligne = df[df["strike"] == strike]
    if ligne.empty:
        return None
    bid = float(ligne["bid"].iloc[0])
    ask = float(ligne["ask"].iloc[0])
    if bid <= 0 or ask <= 0:
        return None
    return (bid + ask) / 2


if __name__ == "__main__":
    print(get_spot_price())


def get_cloture(ticker, jour):
    debut = datetime.strptime(jour, "%Y-%m-%d")
    fin = debut + timedelta(days=5)
    data = yf.download(ticker, start=jour, end=fin.strftime("%Y-%m-%d"), progress=False)
    if data.empty:
        return None
    return float(data["Close"].iloc[0].item())