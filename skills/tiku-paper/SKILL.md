---
name: tiku-paper
description: 在第三方题库服务上组卷（零存储）。当用户要"按考点/难度组一套题""在某某题库里出卷""刷指定考点"时使用。只调用组卷接口生成题组，不下载、不缓存、不分发任何题目内容。
---

# tiku-paper：零存储组卷

## 先决条件

- 仓库所在目录已 `pip install -r requirements.txt`
- `config.json` 已配置端点（`cp config.example.json config.json` 后填写）
- `python cli.py auth` 已完成（openid/token 在 `~/.tiku/credentials.json`）

## 标准流程（三步，前两步只读）

```bash
# 1. 找考点 id（只读）
python cli.py points --subject "马克思|毛中特|史纲|思修" --limit 60

# 2. 收敛区间（只读，可随便跑；不会产生题组记录）
python cli.py plan --points 63 --target 60

# 3. 生成（写，一次；会返回 history_id）
python cli.py build --points 63 --range 40,60

# 4. 核对（只读，只输出统计，不打印题干）
python cli.py report --history <id> --json
```

## 规则

1. **永远先 plan 再 build**。plan 走 `search`（无副作用），build 走 `generate`（写）。
2. **考点最多 5 个**，必须传考点级 id（章节级会 0 匹配）。
3. **题量上限 100**；plan 的 `--target` 只是目标，实际由区间决定。
4. **两次 build 之间至少隔 10 秒**，不要并发。
5. 绝不把 `detail()` 的内容写文件、打印题干、转格式。只允许输出统计。
6. 单/多选比例、满分由服务端决定（常见 1:1、单选1分/多选2分），不要试图覆盖。

## 输出约定（给上层 AI）

`report --json` 返回：

```json
{"code":0,"count":60,"types":{"单选":30,"多选":30},"points":["考点2 ..."]}
```

用这个判断"这套卷是否符合要求"，不要读题目内容。

## 失败排查

| 现象 | 原因 |
|---|---|
| `-116 登录异常【ID异常】` | body 里缺 openid/cdtoken/isIOS |
| `-11 登录异常` | token 过期，客户端会自动刷新一次 |
| `-17 异常访问` | body 不是 form-urlencoded，或缺 Referer/UA |
| `-18 请求超时，请同步设备时间` | 本机时间不准（CDKY 签名校验） |
| `匹配的题目超过了100道` | 区间太宽，plan 会自动收窄；手动就减小 hi 或增大 lo |
| `没有匹配到题目` | 区间太窄或考点 id 不对 |
