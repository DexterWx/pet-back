"""文件存储适配层：把上传的文件落到某处并返回可访问的 URL。

- 当前实现 LocalStorage：存到 UPLOAD_DIR，经 Flask `/uploads/<name>` 静态路由对外访问。
- 接对象存储（OSS/COS 等）时，新增一个实现 Storage 接口的类，在 get_storage() 里按配置切换，
  调用方（接口层）无需改动。
"""
import uuid
from pathlib import Path
from urllib.parse import urlparse

from flask import current_app, request
from werkzeug.utils import secure_filename

# 上传资源对外访问的 URL 前缀（与 app/__init__.py 的静态路由保持一致）
UPLOAD_URL_PREFIX = "/uploads"

# 允许的图片类型 -> 存储时使用的扩展名
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}


def _safe_ext(filename: str) -> str:
    ext = secure_filename(filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return ""
    return "jpg" if ext == "jpeg" else ext


class Storage:
    """存储后端接口。"""

    def save_image(self, data: bytes, original_filename: str) -> str:
        """保存图片字节，返回可公开访问的绝对 URL。失败抛 ValueError。"""
        raise NotImplementedError

    def delete_image(self, url: str) -> bool:
        """按 save_image 返回的 URL 删除图片（尽力而为，省钱）。

        删除成功返回 True；无法解析/不属于当前存储/删除失败均返回 False（不抛异常），
        由调用方记日志。删除商品时调用，失败不阻断主流程（弱一致）。
        """
        return False


class LocalStorage(Storage):
    def save_image(self, data: bytes, original_filename: str) -> str:
        ext = _safe_ext(original_filename)
        if not ext:
            raise ValueError("不支持的文件类型，仅支持 jpg/png/webp/gif")
        max_bytes = current_app.config["MAX_UPLOAD_BYTES"]
        if len(data) > max_bytes:
            raise ValueError(f"文件过大，上限 {max_bytes // (1024 * 1024)}MB")
        if not data:
            raise ValueError("文件内容为空")

        upload_dir = Path(current_app.config["UPLOAD_DIR"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.{ext}"
        # 防路径穿越：secure_filename 已过滤，最终名也仅由 uuid+白名单扩展名组成
        (upload_dir / filename).write_bytes(data)
        return _public_url(filename)

    def delete_image(self, url: str) -> bool:
        """删除 UPLOAD_DIR 内对应文件。仅处理 /uploads/ 路径；防穿越只取 basename。"""
        if not url:
            return False
        path = urlparse(url).path
        if not path.startswith(f"{UPLOAD_URL_PREFIX}/"):
            return False  # 非本存储管理（如种子外链 picsum），跳过
        filename = Path(path).name  # 只取文件名，避免 ../ 穿越
        if not filename:
            return False
        target = Path(current_app.config["UPLOAD_DIR"]) / filename
        try:
            if target.is_file():
                target.unlink()
                return True
        except OSError:
            return False
        return False


def _public_url(filename: str) -> str:
    """拼出对外可访问的绝对 URL（/uploads 静态路由提供）。"""
    base = current_app.config.get("PUBLIC_BASE_URL") or request.host_url or ""
    return f"{base.rstrip('/')}{UPLOAD_URL_PREFIX}/{filename}"


class OSSStorage(Storage):
    """阿里云 OSS 存储。Bucket 需为公共读，图片才能被小程序/网页直接展示。"""

    def save_image(self, data: bytes, original_filename: str) -> str:
        ext = _safe_ext(original_filename)
        if not ext:
            raise ValueError("不支持的文件类型，仅支持 jpg/png/webp/gif")
        max_bytes = current_app.config["MAX_UPLOAD_BYTES"]
        if len(data) > max_bytes:
            raise ValueError(f"文件过大，上限 {max_bytes // (1024 * 1024)}MB")
        if not data:
            raise ValueError("文件内容为空")

        cfg = current_app.config
        for key in ("OSS_ENDPOINT", "OSS_BUCKET", "OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET"):
            if not cfg.get(key):
                raise ValueError(f"未配置 {key}（IMAGE_PROVIDER=oss 必填）")

        import oss2  # 延迟导入，local 模式不加载

        auth = oss2.Auth(cfg["OSS_ACCESS_KEY_ID"], cfg["OSS_ACCESS_KEY_SECRET"])
        bucket = oss2.Bucket(auth, cfg["OSS_ENDPOINT"], cfg["OSS_BUCKET"])
        object_key = f"images/{uuid.uuid4().hex}.{ext}"
        bucket.put_object(object_key, data)

        base = cfg.get("OSS_PUBLIC_BASE") or f"https://{cfg['OSS_BUCKET']}.{cfg['OSS_ENDPOINT']}"
        return f"{base.rstrip('/')}/{object_key}"

    def delete_image(self, url: str) -> bool:
        """删除 OSS 对象。仅当 URL 属于当前 Bucket（前缀匹配 OSS_PUBLIC_BASE 或
        默认 https://{bucket}.{endpoint}）才解析 object key 并删除；不匹配（历史本地/外链）跳过。
        """
        if not url:
            return False
        cfg = current_app.config
        for key in ("OSS_ENDPOINT", "OSS_BUCKET", "OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET"):
            if not cfg.get(key):
                return False
        base = (cfg.get("OSS_PUBLIC_BASE") or f"https://{cfg['OSS_BUCKET']}.{cfg['OSS_ENDPOINT']}").rstrip("/")
        if not url.startswith(base + "/"):
            return False  # 非当前 Bucket（种子外链 picsum / 旧本地图），跳过
        object_key = url[len(base) + 1:]
        if not object_key:
            return False
        try:
            import oss2

            auth = oss2.Auth(cfg["OSS_ACCESS_KEY_ID"], cfg["OSS_ACCESS_KEY_SECRET"])
            bucket = oss2.Bucket(auth, cfg["OSS_ENDPOINT"], cfg["OSS_BUCKET"])
            bucket.delete_object(object_key)
            return True
        except Exception:  # noqa: BLE001 尽力而为，失败不抛
            return False


def get_storage() -> Storage:
    """按 IMAGE_PROVIDER 返回存储实现：local（默认）/ oss。"""
    if current_app.config.get("IMAGE_PROVIDER") == "oss":
        return OSSStorage()
    return LocalStorage()
