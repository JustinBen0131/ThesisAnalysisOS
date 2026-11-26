import numpy as np
rng=np.random.default_rng(7)
P,N=4000,8000          # paths, bets per path
q=rng.uniform(0.15,0.85,(P,N))
def run(edge, claimed=0.03, k=0.5):
    p_true=np.clip(q+edge,0.01,0.99)
    Y=(rng.random((P,N))<p_true).astype(float)
    pb=np.clip(q+claimed,0.01,0.99)
    f=k*(pb-q)/(1-q)                       # fractional Kelly stake on YES at fee-free price q
    logE=np.cumsum(np.log1p(f*(Y/q-1)),axis=1)
    hit=(logE>=np.log(20))
    ever=hit.any(1)
    first=np.where(ever,hit.argmax(1),np.nan)
    return ever.mean(), np.nanmedian(first), np.nanpercentile(first,90) if ever.any() else np.nan
for edge in (0.0,0.01,0.02,0.03):
    for k in (0.5,1.0):
        ev,med,p90=run(edge,k=k)
        print(f"true edge {edge:.2f}  stake {k}xKelly(claimed 3c): P(e>=20 within {N} bets)={ev:.4f} median bets={med:.0f} p90={p90:.0f}")
