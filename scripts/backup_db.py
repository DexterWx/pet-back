#!/usr/bin/env python3
"""SQLite 在线备份 → gzip → 上传阿里云 OSS（私有 ACL）→ 过期清理。

用法（在 pet-back 目录下）：
    uv run python scripts/backup_db.py                  # 备份 + 上传 + 清理
    uv run python scripts/backup_db.py --no-upload      # 只落本地（不删，供排查用）
    uv run python scripts/backup_db.py --keep-local 3 --keep-oss 7   # 想多留几份时手动指定

默认策略：**本地不留副本，OSS 只留最新 1 份**（Bucket 按量计费，不堆历史）。
上传失败时**不删本地文件**，宁可多留一份也别把备份弄丢。

为什么这么设计：
- 用 sqlite3 的 backup() 做在线拷贝：**不要 cp 正在写入的库**，那样可能拿到不完整的页。
- 上传前对副本跑 PRAGMA integrity_check：坏副本不如没有，否则出事故时才发现备份是废的。
- 当前 Bucket 是公共读（商品图要走直链），所以备份对象必须显式打 `x-oss-object-acl: private`，
  并且脚本会匿名 GET 复核一次是否真的不可读——公共可读的库备份等于把全库挂到公网。
  更稳妥的做法是另建一个私有 Bucket，然后把 OSS_BACKUP_BUCKET 指过去。
- 凭证完全复用 .env 的 OSS_*，不新增必填配置；下面的可选项都有默认值：
    BACKUP_DIR         本地备份目录，默认 instance/backups
    OSS_BACKUP_BUCKET  存备份的 Bucket，默认复用 OSS_BUCKET
    OSS_BACKUP_PREFIX  对象前缀，默认 backups
    BACKUP_UPLOAD      设成 0/false 等效于 --no-upload
"""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.core.config import Config  # noqa: E402  复用 .env，不重复解析配置


def _flag(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _is_oss_configured() -> bool:
    return all(_flag(k) for k in ("OSS_ENDPOINT", "OSS_BUCKET", "OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_SECRET"))


def make_local_copy(backup_dir: Path) -> Path:
    """在线备份出 .db，压缩成 .db.gz 后删掉未压缩的中间文件。"""
    uri = Config.SQLALCHEMY_DATABASE_URI
    if not uri.startswith("sqlite:///"):
        raise SystemExit(f"本脚本只支持 SQLite，当前 DATABASE_URL={uri}")
    src_path = Path(uri.replace("sqlite:///", ""))
    if not src_path.exists():
        raise SystemExit(f"源库不存在：{src_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp_db = backup_dir / f".petstore-{stamp}.tmp.db"
    gz = backup_dir / f"petstore-{stamp}.db.gz"

    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(tmp_db)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()

    # 完整性校验放在副本上，不碰线上库
    check = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        tmp_db.unlink(missing_ok=True)
        raise SystemExit(f"备份副本校验失败（integrity_check={result}），已放弃本次备份")

    with tmp_db.open("rb") as fin, gzip.open(gz, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout)
    tmp_db.unlink()
    print(f"本地备份完成：{gz.name}  原 {src_path.stat().st_size} B -> 压缩后 {gz.stat().st_size} B")
    return gz


def build_bucket():
    import oss2  # 延迟导入：--no-upload 时不需要

    bucket_name = _flag("OSS_BACKUP_BUCKET") or Config.OSS_BUCKET
    auth = oss2.Auth(Config.OSS_ACCESS_KEY_ID, Config.OSS_ACCESS_KEY_SECRET)
    return bucket_name, oss2.Bucket(auth, Config.OSS_ENDPOINT, bucket_name)


def upload(bucket_name: str, gz: Path) -> str:
    prefix = _flag("OSS_BACKUP_PREFIX", "backups").strip("/")
    key = f"{prefix}/{gz.name}"
    _, bucket = build_bucket()
    bucket.put_object_from_file(key, str(gz), headers={"x-oss-object-acl": "private"})
    url = f"https://{bucket_name}.{Config.OSS_ENDPOINT}/{key}"
    print(f"已上传 OSS：oss://{bucket_name}/{key}")

    # 匿名读一次：200 说明这个对象在公网上可下载（公共读 Bucket 下 ACL 没生效）
    import requests

    try:
        status = requests.get(url, timeout=15).status_code
    except Exception as e:  # noqa: BLE001 复核失败不影响备份本身
        print(f"  匿名可读性复核跳过：{type(e).__name__} {e}")
        return key
    if status == 200:
        print(f"  ⚠️ 警告：{url} 可被匿名下载（HTTP 200）。请立即改为私有 Bucket 或开启阻止公共访问！")
    else:
        print(f"  匿名访问返回 HTTP {status}（非 200 即符合预期，备份不可被公网读取）")
    return key


def prune(backup_dir: Path, bucket_name: str, key: str, keep_local: int, keep_oss: int) -> None:
    locals_ = sorted(backup_dir.glob("petstore-*.db.gz"), key=lambda p: p.name, reverse=True)
    for old in locals_[max(keep_local, 0):]:
        old.unlink()
        print(f"清理本地旧备份：{old.name}")

    if not key or keep_oss <= 0:
        return
    import oss2

    _, bucket = build_bucket()
    prefix = _flag("OSS_BACKUP_PREFIX", "backups").strip("/") + "/"
    keys = sorted(
        (o.key for o in oss2.ObjectIterator(bucket, prefix=prefix) if o.key.endswith(".db.gz")),
        reverse=True,
    )
    for old in keys[keep_oss:]:
        bucket.delete_object(old)
        print(f"清理 OSS 旧备份：oss://{bucket_name}/{old}")


def main() -> int:
    ap = argparse.ArgumentParser(description="SQLite 备份并上传 OSS")
    ap.add_argument("--no-upload", action="store_true", help="只备份到本地，不上传 OSS")
    ap.add_argument("--keep-local", type=int, default=0, help="本地保留份数（默认 0：上传成功就不留）")
    ap.add_argument("--keep-oss", type=int, default=1, help="OSS 保留份数（默认 1：只留最新）")
    args = ap.parse_args()

    backup_dir = Path(_flag("BACKUP_DIR") or BASE_DIR / "instance" / "backups")
    upload_enabled = not args.no_upload and _flag("BACKUP_UPLOAD", "1").lower() not in ("0", "false", "no")

    gz = make_local_copy(backup_dir)

    if not upload_enabled:
        print("跳过上传（--no-upload 或 BACKUP_UPLOAD=0）：本地副本保留不删")
        prune(backup_dir, "", "", max(args.keep_local, 1), 0)
        return 0
    if not _is_oss_configured():
        print("OSS 未配置完整（OSS_ENDPOINT/BUCKET/ACCESS_KEY_*）：本地副本保留不删")
        prune(backup_dir, "", "", max(args.keep_local, 1), 0)
        return 0

    bucket_name, _ = build_bucket()
    try:
        key = upload(bucket_name, gz)
    except Exception as e:  # noqa: BLE001 上传失败绝不动本地副本
        print(f"❌ 上传失败，本地副本已保留：{gz}  （{type(e).__name__}: {e}）")
        return 1
    prune(backup_dir, bucket_name, key, args.keep_local, args.keep_oss)
    print("备份流程全部完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
