"""商品目录接口：分类 / 商品列表（搜索、筛选、排序、分页）/ 推荐 / 详情。"""
from flask import Blueprint, request

from ....core.response import ApiError, ok
from ....models import Category, Product
from ....services import serializers

bp = Blueprint("catalog", __name__)


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


@bp.get("/categories")
def categories():
    items = Category.query.order_by(Category.sort.asc()).all()
    return ok([{"id": c.id, "name": c.name} for c in items])


# 注意：静态路径 /products/recommend 需先于 /products/<product_id> 注册，避免被通配符抢先匹配
@bp.get("/products/recommend")
def products_recommend():
    items = Product.query.order_by(Product.sort.asc()).limit(6).all()
    return ok([serializers.product_brief(p) for p in items])


@bp.get("/products/<product_id>")
def product_detail(product_id: str):
    product = Product.query.get(product_id)
    if product is None:
        raise ApiError(404, "商品不存在")
    return ok(serializers.product_detail(product))


@bp.get("/products")
def products_list():
    """商品列表：categoryId（'all' 或空为全部）/keyword 标题模糊/sort(default|sales|price)/
    order(asc|desc，默认 desc)/page/pageSize，返回 {list,total,page,pageSize,hasMore}。"""
    query = Product.query

    category_id = request.args.get("categoryId", "")
    if category_id and category_id != "all":
        query = query.filter(Product.category_id == category_id)

    keyword = request.args.get("keyword", "").strip()
    if keyword:
        # SQLite LIKE 对 ASCII 默认不区分大小写，与 Mock 的 toLowerCase 包含匹配一致
        query = query.filter(Product.title.like(f"%{keyword}%"))

    sort = request.args.get("sort", "default")
    descending = request.args.get("order", "desc") != "asc"
    if sort == "sales":
        query = query.order_by(Product.sold.desc() if descending else Product.sold.asc())
    elif sort == "price":
        query = query.order_by(Product.price_fen.desc() if descending else Product.price_fen.asc())
    else:
        query = query.order_by(Product.sort.asc())

    page = max(_int_arg("page", 1), 1)
    page_size = max(_int_arg("pageSize", 10), 1)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return ok({
        "list": [serializers.product_brief(p) for p in items],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "hasMore": page * page_size < total,
    })
