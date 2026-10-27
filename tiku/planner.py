"""组卷规划器（本项目的核心）。

解决的问题：服务端不让你指定题量，只给你「正确率区间」这一个旋钮。
于是"我要 60 题"就变成一个搜索问题：

    target = 60, limit = 100
    在档位 [0,10,15,...,100] 里二分/逐档收窄，
    直到 count ∈ [0.7*target, min(1.3*target, limit)]

关键设计：**探测用 search（只读、无副作用），生成用 generate（写、只调一次）**。
所以 `plan()` 可以随便跑，永远不会在你的账号里留下垃圾题组。

另外：考点名必须和 id 一起传（服务端会做名称匹配），
所以这里把考点树里的 title 带上，避免"有 id 没名字 → 0 匹配"。
"""
from dataclasses import dataclass

# 服务端固定的正确率档位
RATE_STEPS = [0, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100]


@dataclass
class Plan:
    points: list
    titles: str
    lo: int
    hi: int
    count: int
    ok: bool
    trace: list

    @property
    def range(self):
        return (self.lo, self.hi)

    def cmd(self):
        return f"--points {','.join(map(str, self.points))} --range {self.lo},{self.hi}"


def _unused_pick_steps():
    """所有可能的 (lo, hi) 组合，按"区间宽度从宽到窄"排序。"""
    out = []
    for i, lo in enumerate(RATE_STEPS):
        for hi in RATE_STEPS[i + 1:]:
            out.append((lo, hi, hi - lo))
    out.sort(key=lambda x: -x[2])
    return [(lo, hi) for lo, hi, _ in out]


def plan(client, point_ids, target=60, limit=100, lo_tol=0.7, hi_tol=1.3,
         subject_ids=None, bank_ids=None, max_probe=8) -> Plan:
    """探测出一个能命中 target 的正确率区间（不生成任何题组）。

    策略：从服务端默认档位 (30,70) 出发自适应
      - 超上限 → 双向收窄（每次 2 档，30-70 → 40-60 一次到位）
      - 太少   → 向外放宽（每次 1 档）
    """
    points = [str(x) for x in point_ids]
    tree = client.points()
    titles = ",".join(tree.get(p, {}).get("title", "") for p in points).strip(",")
    if not titles:
        raise RuntimeError("考点 id 不在考点树里，检查 --points")

    lo_bound, hi_bound = target * lo_tol, min(target * hi_tol, limit)
    trace = []
    n_steps = len(RATE_STEPS)
    i_lo = RATE_STEPS.index(30) if 30 in RATE_STEPS else 5
    i_hi = RATE_STEPS.index(70) if 70 in RATE_STEPS else 13

    for _ in range(max_probe):
        if i_lo < 0 or i_hi >= n_steps or i_lo >= i_hi:
            break
        lo, hi = RATE_STEPS[i_lo], RATE_STEPS[i_hi]
        r = client.probe(points, lo, hi, titles, subject_ids=subject_ids, bank_ids=bank_ids)
        n = r["count"]
        trace.append({"lo": lo, "hi": hi, "count": n, "msg": (r["message"] or "")[:60]})
        if lo_bound <= n <= hi_bound:
            return Plan(points, titles, lo, hi, n, True, trace)
        if n > hi_bound:            # 太多 → 收窄
            i_lo += 2
            i_hi -= 2
        else:                        # 太少 → 放宽
            i_lo -= 1
            i_hi += 1
            i_lo, i_hi = max(0, i_lo), min(n_steps - 1, i_hi)

    # 没精确命中：退而求其次，选「不超过上限且最接近 target」的探测结果
    cand = [t for t in trace if 0 < t["count"] <= limit]
    if not cand:
        return Plan(points, titles, 0, 0, 0, False, trace)
    best = min(cand, key=lambda t: abs(t["count"] - target))
    return Plan(points, titles, best["lo"], best["hi"], best["count"], False, trace)


def build(client, point_ids, lo, hi, subject_ids=None, bank_ids=None) -> dict:
    """按已收敛的区间生成一套题组（写操作，一次）。"""
    points = [str(x) for x in point_ids]
    tree = client.points()
    titles = ",".join(tree.get(p, {}).get("title", "") for p in points).strip(",")
    return client.generate(points, lo, hi, titles, subject_ids=subject_ids, bank_ids=bank_ids)


def summarize(client, history_id) -> dict:
    """拉题组摘要（只在内存里统计，不打印题干、不落盘）。"""
    r = client.detail(history_id)
    d = r.get("detail") or {}
    qs = d.get("timuInfo") or []
    from collections import Counter
    return {
        "code": r.get("code"),
        "message": r.get("msg"),
        "count": len(qs),
        "types": dict(Counter(q.get("type") for q in qs)),
        "points": list({q.get("kaodian_level_text") for q in qs if q.get("kaodian_level_text")})[:8],
    }
