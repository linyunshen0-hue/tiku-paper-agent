"""HTTP 客户端：form-urlencoded + Referer + UA + token 自动轮换。

三个坑（别的项目踩过的，这里直接封好）：
  1. body 必须 application/x-www-form-urlencoded（用 JSON 会被判"异常访问"）
  2. 必须带 Referer 指向小程序页面容器，否则被拒
  3. token 可能每次响应都轮换（响应里的 wxuserInfo.token 就是新的），要跟着换
"""
import json
import ssl
import time
import urllib.parse
import urllib.request

from .protocol import Envelope

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


class TikuClient:
    def __init__(self, cfg: dict, openid: str, token: str = "", sleep: float = 2.5):
        self.cfg = cfg
        self.env = Envelope(cfg["public_key_pem"])
        self.openid = openid
        self.token = token
        self.sleep = sleep
        self._last = 0.0

    # ---------- 底层 ----------
    def _throttle(self):
        wait = self.sleep - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def post(self, path: str, body: dict, extra: dict | None = None, retry: bool = True) -> dict:
        self._throttle()
        url = path if path.startswith("http") else self.cfg["base_url"].rstrip("/") + "/" + path.lstrip("/")
        # 业务字段里也要带 openid/cdtoken/isIOS（与客户端拦截器一致），否则 -116「ID异常」
        body = dict(body or {})
        body.setdefault("openid", self.openid)
        body.setdefault("cdtoken", self.token)
        body.setdefault("isIOS", "")
        form = self.env.form(body, extra)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"https://servicewechat.com/{self.cfg['appid']}/{self.cfg['version']}/page-frame.html",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/107.0.0.0 Safari/537.36 MicroMessenger/3.9.5.81 NetType/WIFI miniProgram/{self.cfg['appid']}"
            ),
        }
        headers.update(self.env.headers(self.openid, self.token, int(time.time() * 1000)))
        req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(),
                                     headers=headers, method="POST")
        raw = urllib.request.urlopen(req, timeout=30, context=_SSL).read().decode("utf-8", "replace")
        try:
            r = json.loads(raw)
        except Exception:
            return {"code": -999, "msg": raw[:300]}

        # token 轮换：顺手把新的存下来（响应里的 wxuserInfo.token 就是下一次要用的）
        tok = (r.get("wxuserInfo") or {}).get("token")
        if not tok and isinstance(r.get("data"), dict):
            tok = r["data"].get("token")
        if tok and tok != self.token:
            self.token = tok
            from .auth import save_credentials
            save_credentials(self.openid, tok)

        # 登录态失效 → 换 token 重试一次
        if r.get("code") == -11 and retry:
            from .auth import refresh_token
            if refresh_token(self):
                return self.post(path, body, extra, retry=False)
        return r

    # ---------- 业务 ----------
    def points(self) -> dict:
        """考点树：{id: {title, p_level_id, parentId}}"""
        r = self.post(self.cfg["endpoints"]["points"], {"from": "cdtk"})
        if r.get("code") != 0:
            raise RuntimeError(f"取考点失败：{r.get('code')} {r.get('msg')}")
        return r.get("kaodian_level") or {}

    def _search_body(self, point_ids, lo, hi, subject_ids=None, bank_ids=None):
        return {
            "right_rate_dayu": lo,
            "right_rate_xiaoyu": hi,
            "p_kaodian_id_choose": [str(x) for x in point_ids],
            "top_level_id_choose": [str(x) for x in (bank_ids or [])],
            "p_level_id_choose": [str(x) for x in (subject_ids or [])],
        }

    def probe(self, point_ids, lo, hi, titles="", **kw) -> dict:
        """只读探测：返回 {count, candidates[]}，不生成题组。"""
        from .protocol import content_envelope
        extra = content_envelope(self.env, {
            "kaodian_choose": titles, "hexing_choose": "", "chongci_choose": ""})
        r = self.post(self.cfg["endpoints"]["search"],
                      self._search_body(point_ids, lo, hi, **kw), extra)
        detail = r.get("detail") or {}
        return {
            "raw": r,
            "count": int(detail.get("timu_count") or 0),
            "candidates": r.get("timu_detail") or [],
            "message": r.get("msg"),
        }

    def generate(self, point_ids, lo, hi, titles="", **kw) -> dict:
        """写操作：生成一套题组，返回 history_id。"""
        from .protocol import content_envelope
        extra = content_envelope(self.env, {
            "kaodian_choose": titles, "hexing_choose": "", "chongci_choose": ""})
        r = self.post(self.cfg["endpoints"]["generate"],
                      self._search_body(point_ids, lo, hi, **kw), extra)
        detail = r.get("detail") or {}
        return {
            "raw": r,
            "history_id": r.get("history_id") or detail.get("history_id"),
            "count": int(detail.get("timu_count") or 0),
            "single": detail.get("danxuan_count"),
            "multi": detail.get("duoxuan_count"),
            "full_score": detail.get("manfen"),
            "message": r.get("msg"),
        }

    def detail(self, history_id) -> dict:
        """拉题组内容（仅在内存里用，绝不落盘）。"""
        return self.post(self.cfg["endpoints"]["detail"], {
            "history_id": str(history_id),
            "tiku_item": "kaodian_shouti",
            "from": "shouti_dati",
        })
