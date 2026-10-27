# tiku-paper-agent

**用 AI 决策，在别人的题库里组卷 —— 不下载题库，不存题目，不碰版权。**

一个「零存储组卷」的参考实现：AI 只负责**决策**（考哪些考点、要什么难度区间），
题目由题库服务自己生成成一套可刷的题组。你的磁盘上不会出现任何一道题。

```
AI 决策（考点 + 正确率区间）
      ↓  只传筛选条件
题库服务自己组卷（返回 history_id）
      ↓  只记 id
你打开小程序/App → 题库 → 考点搜题 → 历史 → 开刷
```

---

## 为什么是「零存储」

| 常见做法 | 本项目的做法 |
|---|---|
| 抓包 → 全量拉题库 → 落成本地 JSON | 只在会话内读响应，**不落盘** |
| 本地组卷 → 生成 PDF/网页 | 只生成**服务端题组**，内容不进你的仓库 |
| 分发题库文件（侵权） | 分发**代码**（无版权风险） |

题目与解析的著作权归原出版方。本项目**不提供、不存储、不分发**任何题目内容，
只提供"如何向题库服务提出组卷请求"的自动化逻辑。自用可以，传播题目内容不可以。

详见 [docs/why-zero-storage.md](docs/why-zero-storage.md)。

---

## 它的技术核心不是"逆向"，是两个设计

### 1. 探测与生成分离（不污染历史记录）

题库的"生成题组"接口有个脾气：**匹配数 > 上限就直接拒绝**（不生成），
而"搜索"接口会把候选题目列表和数量一并返回，**且不产生任何副作用**。

所以本项目用两套调用做一件事：

```
探测（只读）：search()   → {"timu_count": 124}     ← 不生成，可以随便调
生成（写）  ：generate() → {"history_id": 1472}    ← 只在收敛完成后调一次
```

**结果：一次组卷只产生 1 个题组记录，而不是几十个探测垃圾。**

### 2. 把「正确率区间」当旋钮，二分逼近目标题量

题库不允许你指定题量，只有两个参数：正确率下限 / 上限。
于是"我要 60 题"变成一道搜索题：

```
档位 [0,10,15,...,95,100]
target=60, limit=100
lo,hi = 0,100  → count 124 超限
lo,hi = 0,70   → count ...
二分/逐档收窄 → count ∈ [0.7*target, min(1.3*target, limit)]  ✅
```

实测（某考研政治题库，考点「马克思主义的创立和发展」）：

| 区间 | 匹配题数 | 结果 |
|---|---|---|
| 30–70 | 124 | 超 100，拒绝 |
| 40–60 | **60** | 命中 → `history_id=1472`（单选30/多选30，满分90） |

完整算法见 [tiku/planner.py](tiku/planner.py)，思路见 [docs/paper-planning.md](docs/paper-planning.md)。

---

## 快速开始

```bash
pip install -r requirements.txt
cp config.example.json config.json      # 填你自己的服务端点/AppID（见下）
python cli.py auth                      # 取 openid/token（本机微信进程内存扫描，或手工输入）
python cli.py points --subject 马原      # 列考点（id + 标题）
python cli.py plan  --points 63 --target 60       # 只探测，不生成（dry-run）
python cli.py build --points 63 --target 60       # 收敛后生成一套
python cli.py show  --history 1472                # 看这套题的摘要（不落盘）
```

`plan` 永远安全：它只调"搜索"接口，不会在你的账号里留下任何题组。

---

## 关于 config

`config.example.json` 里的端点是**示例**（一个考研政治刷题小程序）。
协议本身是通用的，你可以照 [docs/protocol-patterns.md](docs/protocol-patterns.md)
换成任何一个"按考点+难度区间组卷"的题库服务。

```json
{
  "base_url": "https://<host>/",
  "appid": "wx...",
  "version": "19",
  "public_key_pem": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----",
  "endpoints": {
    "points":   "apicdvip/kaodianlevel",
    "search":   "apizhaos/tikutimusearch",
    "generate": "apicdvip/timusearch",
    "detail":   "apicdvip/stdetail"
  }
}
```

> 不同的服务端点不同、签名方式不同。本项目把"协议"和"端点"分开，
> 是为了让你能**换一个服务**而不用改代码。

---

## 命令输出长什么样

```
$ python cli.py plan --points 63 --target 60
考点   63  考点2 马克思主义的创立和发展★
目标   60 题（上限 100）
探测   30-70   → 124 题  超限，收窄
探测   40-60   →  60 题  ✅ 命中
建议   build --points 63 --range 40,60

$ python cli.py build --points 63 --range 40,60
生成成功  history_id=1472
  题量 60  单选 30 / 多选 30  满分 90
入口  题库 → 考点搜题 → 历史记录 → 选「<时间>」那套
```

---

## 边界（实测，不是猜的）

- 题量**上限 100**，超过直接拒
- 单选/多选由服务端**自动 1:1**，不能自定义
- 正确率区间是**定值档位**，不是连续值
- 考点必须传**考点级 id**（章节级会 0 匹配），最多 5 个
- 每次生成会留一条历史记录，所以别反复 `build`（`plan` 随便跑）

---

## 类似项目 / 致谢

"逆向接入第三方平台"是个成熟范式，本项目不主张发明了它：

- `Binaryify/NeteaseCloudMusicApi`（30k★）—— 把客户端协议变成 API 的祖师爷
- `DokiDoki1103/tikuAdapter`（555★）—— 多题库统一成一个 API
- `notnotype/xxt`（279★）—— 网课平台题库爬虫

本项目的差异只有两点：**不落盘**（零版权资产）和**把"组卷"当成搜索问题**（区间收敛）。

---

## License

MIT。见 [LICENSE](LICENSE) 与 [NOTICE.md](NOTICE.md)。
