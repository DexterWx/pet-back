"""管理端文件上传接口：图片上传到当前 IMAGE_PROVIDER（local/oss），返回可访问 URL。

供 pet-web 商品/分类/Banner 管理上传图片使用；小程序端不暴露此接口。
"""
from flask import Blueprint, request

from ....core.response import ApiError, ok
from ....core.security import admin_required
from ....services import storage

bp = Blueprint("admin_upload", __name__, url_prefix="/upload")


@bp.post("/image")
@admin_required
def upload_image():
    """上传图片（multipart/form-data，字段名 file），返回 {url}。"""
    file = request.files.get("file")
    if file is None or not file.filename:
        raise ApiError(400, "未选择文件")
    try:
        url = storage.get_storage().save_image(file.read(), file.filename)
    except ValueError as e:
        raise ApiError(400, str(e))
    return ok({"url": url})
