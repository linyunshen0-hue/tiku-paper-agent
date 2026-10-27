"""凭证：openid / token 的获取与缓存。

三种方式，按优先级：
  1. 环境变量 TIKU_OPENID / TIKU_TOKEN
  2. ~/.tiku/credentials.json
  3. 手工输入（交互）
（可选，不随仓库提供）内存读取：只读你本机的微信小程序进程，取你自己账号的 openid。
   这是取证而非攻击，代码里刻意不做批量/其他进程扫描。
"""
import json
import os
import sys

CRED = os.path.join(os.path.expanduser("~"), ".tiku", "credentials.json")


def save_credentials(openid: str, token: str = ""):
    os.makedirs(os.path.dirname(CRED), exist_ok=True)
    json.dump({"openid": openid, "token": token}, open(CRED, "w", encoding="utf-8"))
    try:
        os.chmod(CRED, 0o600)
    except Exception:
        pass


def load_credentials() -> tuple[str, str]:
    if os.environ.get("TIKU_OPENID"):
        return os.environ["TIKU_OPENID"], os.environ.get("TIKU_TOKEN", "")
    if os.path.exists(CRED):
        d = json.load(open(CRED, encoding="utf-8"))
        return d.get("openid", ""), d.get("token", "")
    return "", ""


def interactive() -> tuple[str, str]:
    print("没有找到凭证。请二选一：")
    print("  1) 在目标小程序里点开任意题目，用你习惯的抓包工具取 openid / token")
    print("  2) 直接粘贴（token 可留空，客户端会自动换）")
    openid = input("openid: ").strip()
    token = input("token(可空): ").strip()
    if openid:
        save_credentials(openid, token)
        print(f"已保存到 {CRED}")
    return openid, token


def refresh_token(client) -> bool:
    """调首页接口换一个新 token（多数服务会在响应里轮换）。"""
    ep = (client.cfg.get("endpoints") or {}).get("refresh")
    if not ep:
        return False
    try:
        r = client.post(ep, {}, retry=False)
        return r.get("code") in (0, 200)
    except Exception:
        return False


def ensure() -> tuple[str, str]:
    openid, token = load_credentials()
    if not openid:
        openid, token = interactive()
    return openid, token
