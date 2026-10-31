"""诊断：placebo 排序键到底等价于什么。

on : e_i = accum_i / (denom_i + p0)      -> 均值梯度的收缩估计
negctl: e_i = accum_i / (denom_perm(i) + p0)  -> 分母与分子解耦
"""
import torch

torch.manual_seed(0)
n = 200_000
p0 = 8.0

# 现实分布：denom 观测次数重尾；accum 大致随 denom 增长但噪声大
denom = torch.distributions.Gamma(2.0, 0.05).sample((n,)).clamp(0, 500)
noise = torch.randn(n) * 0.6
accum = denom * torch.exp(noise) * 0.01  # mean grad ~ exp(noise)*0.01

def spearman(a, b):
    ra = a.argsort().argsort().float()
    rb = b.argsort().argsort().float()
    ra = (ra - ra.mean()) / ra.std()
    rb = (rb - rb.mean()) / rb.std()
    return float((ra * rb).mean())

e_on = accum / (denom + p0)
perm = torch.randperm(n)
e_nc = accum / (denom[perm] + p0)
mean_grad = accum / denom.clamp_min(1.0)

print("=== Spearman with ranking key ===")
print(f"  on   vs mean_grad : {spearman(e_on, mean_grad):+.4f}")
print(f"  on   vs accum     : {spearman(e_on, accum):+.4f}")
print(f"  nc   vs mean_grad : {spearman(e_nc, mean_grad):+.4f}")
print(f"  nc   vs accum     : {spearman(e_nc, accum):+.4f}")
print()
print("=== top-k overlap (k=5000) ===")
k = 5000
t_on = set(e_on.topk(k).indices.tolist())
t_nc = set(e_nc.topk(k).indices.tolist())
t_mg = set(mean_grad.topk(k).indices.tolist())
t_ac = set(accum.topk(k).indices.tolist())
print(f"  on  vs mean_grad : {len(t_on&t_mg)/k:.1%}")
print(f"  nc  vs mean_grad : {len(t_nc&t_mg)/k:.1%}")
print(f"  nc  vs accum     : {len(t_nc&t_ac)/k:.1%}")
print(f"  on  vs nc        : {len(t_on&t_nc)/k:.1%}")
print()
print("=== 分母膨胀检验：nc 的分数分布被分母噪声摊平 ===")
for nm, e in (("on", e_on), ("nc", e_nc)):
    q = e.quantile(torch.tensor([0.5, 0.9, 0.99, 0.999]))
    print(f"  {nm}: median={q[0]:.5f} p90={q[1]:.5f} p99={q[2]:.5f} p999={q[3]:.5f} cv={e.std()/e.mean():.3f}")
