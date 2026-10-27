# 小程序 API 的 5 种常见鉴权模式（脱敏）

> 这是从若干「教育/题库类」小程序客户端里归纳出来的通用套路，不含任何具体站点信息。
> 认出一个服务属于哪种模式，基本就知道该怎么调。

---

## 模式 A：整包加密 + 时间戳签名（本项目用的这种）

```
header:
  openid  = RSA(openid)
  cdtoken = RSA(token)
  CDKY    = RSA("<毫秒时间戳>_<固定标记>")     ← 防重放
body (form-urlencoded):
  params  = RSA(JSON.stringify(业务字段))
```

特征：
- 客户端里能找到 `-----BEGIN PUBLIC KEY-----`（1024/2048bit）
- 有 `encryptLong` 之类的分段加密函数（PKCS#1 v1.5，每 117 字节一段，密文拼接后整体 base64）
- 服务端会用时间戳校验，**本机时间必须准**

踩坑：直接用 JSON 发 body 会被判"参数错误"，必须 `form-urlencoded`。

---

## 模式 B：拦截器外挂 content（本项目额外用到的）

在模式 A 基础上：

```
body:
  params     = RSA(其余字段)
  content    = 明文 JSON（结构化筛选条件）
  contentKey = RSA("<固定标记，如 title_choose>")
```

服务端先用 `contentKey` 解出标记，决定怎么解释 `content`。
`contentKey` 往往是**常量**（等于一个加密后的类型标签），抓到一次就能硬编码。

---

## 模式 C：只校验 Referer / UA

```
Referer: https://servicewechat.com/<appid>/<ver>/page-frame.html
User-Agent: ... MicroMessenger/... miniProgram/<appid>
```

很多"看起来在防爬"的接口，其实只查这两样。补上就通。
版本号 `<ver>` 会被服务端比对，**换版本要改**（否则返回"请先升级小程序"）。

---

## 模式 D：token 轮换

```
响应: {"code":0, "wxuserInfo": {"token": "新的32位hex"}}
```

服务端**每次响应都下发新 token，旧的下次就不能用**。
处理方式：每次响应后把新 token 存下来；遇到 `-11 login invalid` 就刷新一次重试。

这是最容易漏的一条：只调一个接口时正常，连着调第二个就 `-11`。

---

## 模式 E：设备绑定

首次登录会调 `shebei` / `bind` 类接口，把 `openid + 设备信息` 写进服务端，
之后部分接口要求设备已绑定，否则返回"登录异常"。

特征：客户端里出现 `shebei_id`、`model`、`systemInfo` 的存储读写。

---

## 判断顺序（排查用）

```
全部接口 -17「异常访问」        → 模式 A 的 body 格式不对 / 缺 C
只有部分接口 -17                → 那些接口可能带 content（模式 B）
只有第一个接口通                  → 模式 D（token 换了）
全部 -11「登录异常」              → token 失效或未绑定设备（模式 E）
-14「请先升级小程序」             → Referer/UA 里的版本号不对（模式 C）
-18「请求超时，请同步设备时间」     → CDKY 时间戳没解出来 / 本机时间不准（模式 A）
```

---

## 关于"要不要写进代码"

本项目只把**模式**写进文档，把**端点/密钥**放进 `config.json`（gitignore）。
这样：
- 代码是通用的，能复用到别的服务
- 仓库里没有"针对某一家"的硬编码（除了示例 config）
- 别人 fork 后可以指向自己的服务

这也是为了避免项目变成"某某 App 一键破解脚本"——那种东西通常活不久。
