"""微信登录：code2Session 换取 openid + 手机号快速验证（getuserphonenumber）。

- WECHAT_MOCK_LOGIN=true（本地联调）：不调微信接口，固定 openid 模拟单一身份，手机号返回 Mock 值。
- WECHAT_MOCK_LOGIN=false：真实调用 jscode2session + getuserphonenumber，需 WECHAT_APPID/WECHAT_SECRET。
手机号来自微信 `getPhoneNumber` 按钮回传的 code（微信担保，无需短信）。
"""
import time

import requests
from flask import current_app

from ..core.response import ApiError

WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
WECHAT_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WECHAT_PHONE_URL = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"

# Mock 模式固定 openid / phone（与 pet-mini 早期 Mock 同语义）
MOCK_OPENID = "mock_openid_dev"
MOCK_PHONE = "13800000000"

# access_token 进程内缓存（单 worker 足够；多实例应换共享存储）
_token_cache = {"token": "", "exp": 0.0}


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


def _get_access_token() -> str:
    """获取并缓存小程序全局 access_token（提前 5 分钟过期）。"""
    if current_app.config.get("WECHAT_MOCK_LOGIN"):
        return "MOCK_ACCESS_TOKEN"
    now = time.time()
    if _token_cache["token"] and now < _token_cache["exp"] - 300:
        return _token_cache["token"]

    appid = current_app.config.get("WECHAT_APPID", "")
    secret = current_app.config.get("WECHAT_SECRET", "")
    if not appid or not secret:
        raise ApiError(500, "服务端未配置 WECHAT_APPID/WECHAT_SECRET")
    try:
        resp = requests.get(
            WECHAT_TOKEN_URL,
            params={"grant_type": "client_credential", "appid": appid, "secret": secret},
            timeout=10,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise ApiError(500, f"获取 access_token 失败: {e}") from e
    if "access_token" not in data:
        raise ApiError(500, f"获取 access_token 失败: errcode={data.get('errcode')} {data.get('errmsg', '')}")
    _token_cache["token"] = data["access_token"]
    _token_cache["exp"] = now + int(data.get("expires_in", 7200))
    return _token_cache["token"]


def get_phone_number(phone_code: str) -> str:
    """用 getPhoneNumber 回传的 code 换取用户手机号（微信担保）。

    Mock 模式忽略 code 直接返回固定手机号；真实模式未传 code 视为未授权 -> 400（不允许登录）。
    """
    if current_app.config.get("WECHAT_MOCK_LOGIN"):
        return MOCK_PHONE
    if not phone_code:
        raise ApiError(400, "需要授权手机号后才能登录")

    token = _get_access_token()
    try:
        resp = requests.post(
            WECHAT_PHONE_URL,
            params={"access_token": token},
            json={"code": phone_code},
            timeout=10,
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise ApiError(500, f"调用手机号接口失败: {e}") from e

    if data.get("errcode") != 0 or "phone_info" not in data:
        raise ApiError(400, f"手机号授权失败: errcode={data.get('errcode')} {data.get('errmsg', '')}")
    info = data["phone_info"]
    return str(info.get("purePhoneNumber") or info.get("phoneNumber") or "")
