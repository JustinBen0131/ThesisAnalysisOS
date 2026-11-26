import numpy as np, math, sys, json
gh_x, gh_w = np.polynomial.hermite_e.hermegauss(41); gh_w = gh_w/gh_w.sum()
def solve(theta, sigma, L, b, T, c=100.0, fixed=None, nf=41, ngrid=500, dt=1/52):
    steps=int(round(T/dt))
    w=np.concatenate([[0.0], np.geomspace(20, b, ngrid)])  # states below goal; >=b absorbing value 1
    m=theta*sigma - 0.5*sigma**2
    R=np.exp(m*dt + sigma*math.sqrt(dt)*gh_x)-1.0     # simple weekly returns at nodes
    fs=np.array([fixed]) if fixed is not None else np.linspace(0,L,nf)
    V=np.zeros_like(w)  # terminal: below b -> 0
    pol_snap={}
    for k in range(steps):
        # next wealth for each (state, action, node)
        Wn=w[:,None,None]*(1+fs[None,:,None]*R[None,None,:])+c
        Wn=np.maximum(Wn,0.0)
        Vn=np.where(Wn>=b,1.0,np.interp(Wn,w,V))
        EV=(Vn*gh_w[None,None,:]).sum(-1)
        j=EV.argmax(1)
        V=EV[np.arange(len(w)),j]
        t_left=(k+1)*dt
        for snap in (0.25,1.0,T):
            if abs(t_left-snap)<dt/2: pol_snap[snap]=fs[j].copy()
    return w,V,pol_snap
sigma=0.18
out=[]
for b in (1e5,1e6):
  for T in (3,5,10):
    for theta in (0.0,0.4,1.0,2.0):
      row={'b':b,'T':T,'theta':theta}
      for L in (1.0,3.0):
        w,V,_=solve(theta,sigma,L,b,T)
        row[f'opt_L{int(L)}']=V[0]
      kel=min(theta/sigma,3.0)
      for name,f in (('index100',1.0),('cash',0.0),('kelly_cap3',kel),('halfkelly_cap3',min(kel/2,3.0))):
        w,V,_=solve(theta,sigma,3.0,b,T,fixed=f)
        row[name]=V[0]
      out.append(row)
      print(json.dumps({k:(round(v,4) if isinstance(v,float) else v) for k,v in row.items()}),flush=True)
json.dump(out,open('dp_results.json','w'))
