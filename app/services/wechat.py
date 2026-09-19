"""微信登录：code2Session 封装。

- WECHAT_MOCK_LOGIN=true（默认，本地联调）：不调微信接口，固定 openid 模拟单一身份，
  行为对齐 pet-mini Mock（首次登录即注册，之后直接登录）。
- WECHAT_MOCK_LOGIN=false：真实调用微信 jscode2session，需配置 WECHAT_APPID/WECHAT_SECRET。
"""
import requests
from flask import current_app

from ..core.response import ApiError

WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"

# Mock 模式固定 openid（与 pet-mini mock/server.js 的 MOCK_OPENID 同语义）
MOCK_OPENID = "mock_openid_dev"


def code2session(code: str) -> str:
    """用 wx.login 的临时 code 换取 openid。"""
    if not code:
        raise ApiError(400, "缺少登录凭证 code")

    if current_app.config.get("WECHAT_MOCK_LOGIN"):
        return MOCK_OPENID

    appid = current_app.config.get("WECHAT_APPID", "")
    secret = current_app.config.get("WECHAT_SECRET", "")
    if not appid or not secret:
        raise ApiError(500, "服务端未配置 WECHAT_APPID/WECHAT_SECRET")

    try:
        resp = requests.get(
            WECHAT_CODE2SESSION_URL,
            params={
                "appid": appid,
                "secret": secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise ApiError(500, f"调用微信接口失败: {e}") from e

    if "openid" not in data:
        raise ApiError(400, f"微信登录失败: errcode={data.get('errcode')} {data.get('errmsg', '')}")
    return data["openid"]
