"""统一响应结构与全局错误处理。

契约对齐 pet-mini/mock/server.js：
- 响应体 {code, data, message}，code=0 成功；400 业务错误；401 未登录；404 不存在；500 服务异常。
- HTTP 状态码与 body code 保持一致（小程序 utils/request.js 真实传输层按
  statusCode===200 ? 0 : statusCode 归一化，body.message 透出，两种约定均兼容）。
"""
from flask import jsonify
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    """业务异常：由全局错误处理器统一转为 {code, data, message} 响应。"""

    def __init__(self, code: int = 400, message: str = "请求失败"):
        super().__init__(message)
        self.code = code
        self.message = message


def ok(data=None, message: str = "ok"):
    return jsonify({"code": 0, "data": data, "message": message}), 200


def err(code: int, message: str, http_status: int | None = None):
    return (
        jsonify({"code": code, "data": None, "message": message}),
        http_status or code,
    )


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(e: ApiError):
        return err(e.code, e.message)

    @app.errorhandler(HTTPException)
    def handle_http_exception(e: HTTPException):
        return err(e.code or 500, e.description or e.name)

    @app.errorhandler(Exception)
    def handle_unexpected(e: Exception):
        app.logger.exception("未捕获异常: %s", e)
        return err(500, "服务器内部错误")
