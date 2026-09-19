"""数据库维护 CLI 命令：flask seed / flask reset-db。"""
import click
from flask.cli import AppGroup, with_appcontext

from ..models import db
from .seed import run_seed

bp = AppGroup("db", help="数据库维护命令")


@bp.command("seed")
@with_appcontext
def seed_cmd():
    """灌种子数据（幂等：已存在则跳过）"""
    db.create_all()
    added = run_seed()
    click.echo(f"种子数据完成，新增: {added}")


@bp.command("reset")
@with_appcontext
def reset_cmd():
    """删表重建 + 灌种子（清空全部业务数据，谨慎使用）"""
    db.drop_all()
    db.create_all()
    added = run_seed()
    click.echo(f"数据库已重建，新增: {added}")


def register_cli(app):
    app.cli.add_command(bp, "db")
