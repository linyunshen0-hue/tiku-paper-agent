"""协议层：RSA 加密 + 请求体拼装。

这是唯一和"某一家服务"绑定的地方（公钥来自它的客户端），
换服务时只需要换 config 里的 public_key_pem 与 endpoints。
"""
import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

CHUNK = 117  # 1024bit 公钥 − PKCS1 v1.5 的 11 字节开销


class Envelope:
    """把 dict 加密成服务端能解的形态。

    服务端约定（见 docs/protocol-patterns.md 模式 A）：
      - header 三个 RSA 字段：openid / cdtoken / CDKY
      - body：params = RSA(其余字段 JSON)
      - 个别接口额外带 content（明文）+ contentKey（RSA 常量标记）
    """

    def __init__(self, pem: str):
        self._pub = serialization.load_pem_public_key(pem.encode())

    def enc(self, text: str) -> str:
        raw = text.encode()
        out = b""
        for i in range(0, len(raw), CHUNK):
            out += self._pub.encrypt(raw[i:i + CHUNK], padding.PKCS1v15())
        return base64.b64encode(out).decode()

    def headers(self, openid: str, token: str, ts_ms: int) -> dict:
        return {
            "openid": self.enc(openid),
            "cdtoken": self.enc(token) if token else "",
            "CDKY": self.enc(f"{ts_ms}_CDKY"),
        }

    def form(self, body: dict, extra: dict | None = None) -> dict:
        """body → 加密 params；extra（content/contentKey）原样并排放进表单。"""
        form = {"params": self.enc(json.dumps(body, ensure_ascii=False, separators=(",", ":")))}
        if extra:
            form.update(extra)
        return form


def content_envelope(env: Envelope, payload: dict, key_marker: str = "title_choose") -> dict:
    """构造 content / contentKey 这一对（有的服务用它传"结构化筛选条件"）。"""
    return {
        "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "contentKey": env.enc(key_marker),
    }
