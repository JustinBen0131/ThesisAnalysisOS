from statistics import NormalDist
import math
N=NormalDist()
def Pstar(frac, theta, T):
    if frac>=1: return 1.0
    return N.cdf(N.inv_cdf(frac)+theta*math.sqrt(T))
print("== Goal-reaching upper bound P* = Phi(Phi^-1(x/b) + theta sqrt T)  [Browne 1999; Follmer-Leukert 1999]")
print("M=b/x  theta  T=1    T=3    T=5    T=10")
for M in (2,10,100,1000):
    for th in (0,0.25,0.5,1.0,2.0,3.0):
        print(f"{M:5d} {th:5.2f} "+" ".join(f"{Pstar(1/M,th,T):6.3f}" for T in (1,3,5,10)))
print()
print("theta*sqrt(T) needed for P*=0.5 (goal-optimal) vs Kelly median sqrt(2 ln M):")
for M in (2,10,100,1000):
    print(M, round(-N.inv_cdf(1/M),3), round(math.sqrt(2*math.log(M)),3))
print()
# With $100/week contributions, x=0, r=0: bound with budget = total contributions C
print("== With $100/week from $0 (budget = total contributions, r=0): upper bound on P(reach b by T)")
for b in (25e3,100e3,1e6):
    for T in (1,3,5,10):
        C=5200*T
        row=[Pstar(C/b,th,T) for th in (0,0.4,1,2,3)]
        print(f"b=${b:>9,.0f} T={T:2d} C=${C:>7,.0f} | th=0:{row[0]:.3f} 0.4:{row[1]:.3f} 1:{row[2]:.3f} 2:{row[3]:.3f} 3:{row[4]:.3f}")
print()
print("== Estimation error: optimal Kelly shrink k*=th^2/(th^2+s^2); growth at full Kelly (th^2-s^2)/2 vs at k*")
for th in (0.25,0.5,1.0):
    for Y in (3,5,10,20):
        s=math.sqrt((1+th*th/2)/Y)
        k=th*th/(th*th+s*s)
        print(f"th={th} years={Y:2d} s={s:.3f} k*={k:.2f} g_full={(th*th-s*s)/2:+.4f} g_k*={th**4/(2*(th*th+s*s)):.4f} g_true_kelly={th*th/2:.4f}")
print()
print("== Expected time for a Kelly bettor's relative wealth (e-value) to reach 20 (ln20 nats), growth th^2/2 per yr")
for th in (0.25,0.5,1,2,3):
    print(f"th={th}: mean {2*math.log(20)/th**2:.1f} years")
print()
print("== Binary odds market: edge per bet in nats (KL) for true p vs price q, and bets to reach e=20")
def kl(p,q): return p*math.log(p/q)+(1-p)*math.log((1-p)/(1-q))
for p,q in ((0.55,0.5),(0.52,0.5),(0.53,0.5),(0.12,0.10),(0.95,0.93)):
    d=kl(p,q); print(f"p={p} q={q}: KL={d:.5f} nats/bet, bets~{math.log(20)/d:.0f}")
