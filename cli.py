#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""tiku-paper-agent CLI

  python cli.py auth                          # 取/换凭证
  python cli.py points [--subject 马原]        # 列考点
  python cli.py plan  --points 63 --target 60  # 只探测（安全）
  python cli.py build --points 63 --range 40,60
  python cli.py show  --history 1472
  python cli.py auto  --subject 马原 --target 60 --yes   # 一条龙（会写）
"""
import argparse
import json
import os
import sys

from tiku import auth, planner
from tiku.client import TikuClient

HERE = os.path.dirname(os.path.abspath(__file__))


def load_cfg(path="config.json"):
    p = path if os.path.isabs(path) else os.path.join(HERE, path)
    if not os.path.exists(p):
        sys.exit(f"缺少 {path}：请 cp config.example.json config.json 并填写端点")
    return json.load(open(p, encoding="utf-8"))


def make_client(cfg, sleep=2.5):
    openid, token = auth.ensure()
    if not openid:
        sys.exit("没有 openid，先跑 python cli.py auth")
    c = TikuClient(cfg, openid, token, sleep=sleep)
    if not token:                      # 没 token 先换一个（服务端在响应里轮换）
        ep = (cfg.get("endpoints") or {}).get("refresh")
        if ep:
            c.post(ep, {}, retry=False)
    return c


def filter_points(tree, keyword=""):
    rows = []
    for pid, v in tree.items():
        title = v.get("title") or ""
        if keyword and not any(k and k in title for k in keyword.split("|")):
            continue
        rows.append((pid, title, v.get("p_level_id")))
    rows.sort(key=lambda x: x[0].zfill(6))
    return rows


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("auth")
    s.add_argument("--openid"); s.add_argument("--token", default="")

    s = sub.add_parser("points")
    s.add_argument("--subject", default="")
    s.add_argument("--limit", type=int, default=40)

    s = sub.add_parser("plan")
    s.add_argument("--points", required=True, help="考点 id，逗号分隔，最多 5 个")
    s.add_argument("--target", type=int, default=60)
    s.add_argument("--limit", type=int, default=100)

    s = sub.add_parser("build")
    s.add_argument("--points", required=True)
    s.add_argument("--range", required=True, help="如 40,60")

    s = sub.add_parser("show")
    s.add_argument("--history", required=True)

    s = sub.add_parser("auto")
    s.add_argument("--points", required=True)
    s.add_argument("--target", type=int, default=60)
    s.add_argument("--yes", action="store_true", help="确认写入（不加则只 plan）")

    s = sub.add_parser("report")
    s.add_argument("--history", required=True)
    s.add_argument("--json", action="store_true", help="输出机器可读摘要给 agent")

    a = ap.parse_args()
    cfg = load_cfg()

    if a.cmd == "auth":
        if a.openid:
            auth.save_credentials(a.openid, a.token)
            print(f"已保存到 {auth.CRED}")
        else:
            auth.interactive()
        return

    client = make_client(cfg)

    if a.cmd == "points":
        tree = client.points()
        rows = filter_points(tree, a.subject)
        print(f"考点 {len(rows)} 条（关键词「{a.subject or '全部'}」）")
        for pid, title, parent in rows[:a.limit]:
            print(f"  {pid:>6}  {title}   (parent={parent})")
        return

    points = [x.strip() for x in (getattr(a, "points", "") or "").split(",") if x.strip()]

    if a.cmd == "plan":
        p = planner.plan(client, points, target=a.target, limit=a.limit)
        print(f"考点   {','.join(p.points)}  {p.titles}")
        print(f"目标   {a.target} 题（上限 {a.limit}）")
        for t in p.trace:
            flag = "✅" if t["count"] and abs(t["count"] - a.target) <= a.target * .3 else ""
            print(f"探测   {t['lo']:>3}-{t['hi']:<3} → {t['count']:>4} 题 {flag} {t['msg']}")
        print(("建议   " + p.cmd()) if p.ok else "没有命中，请换考点或放宽 target")
        return

    if a.cmd == "build":
        lo, hi = [int(x) for x in a.range.split(",")]
        r = planner.build(client, points, lo, hi)
        if r["history_id"]:
            print(f"生成成功  history_id={r['history_id']}")
            print(f"  题量 {r['count']}  单选 {r['single']} / 多选 {r['multi']}  满分 {r['full_score']}")
            print("入口  题库 → 考点搜题 → 历史记录")
        else:
            print(f"生成失败：{r['message']}")
        return

    if a.cmd == "show":
        r = client.detail(a.history)
        d = r.get("detail") or {}
        qs = d.get("timuInfo") or []
        print(f"题组 {a.history}  {len(qs)} 题  code={r.get('code')}")
        for q in qs[:3]:
            print(f"  [{q.get('type')}] {q.get('kaodian_level_text')}  答案 {q.get('right_text')}")
        return

    if a.cmd == "report":
        s = planner.summarize(client, a.history)
        print(json.dumps(s, ensure_ascii=False, indent=1) if a.json else
              f"{s['count']} 题 {s['types']} 考点 {s['points'][:3]}")
        return

    if a.cmd == "auto":
        p = planner.plan(client, points, target=a.target)
        for t in p.trace:
            print(f"探测 {t['lo']}-{t['hi']} → {t['count']}")
        if not p.ok:
            sys.exit("没有收敛到目标区间")
        if not a.yes:
            print(f"（未写入）确认后加 --yes，或手动跑： python cli.py build {p.cmd()}")
            return
        r = planner.build(client, points, p.lo, p.hi)
        print(f"history_id={r['history_id']}  {r['count']} 题 满分 {r['full_score']}")


if __name__ == "__main__":
    main()
