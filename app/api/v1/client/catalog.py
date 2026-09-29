"""商品目录接口：分类 / 商品列表（搜索、筛选、排序、分页）/ 详情。"""
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


@bp.get("/products/<product_id>")
def product_detail(product_id: str):
    product = Product.query.get(product_id)
    # 下架商品对小程序端不可见，与不存在同样返回 404
    if product is None or not product.on_sale:
        raise ApiError(404, "商品不存在")
    return ok(serializers.product_detail(product))


@bp.get("/products")
def products_list():
    """商品列表：categoryId（'all' 或空为全部）/keyword 标题模糊/sort(default|sales|price)/
    order(asc|desc，默认 desc)/page/pageSize，返回 {list,total,page,pageSize,hasMore}。仅上架商品。"""
    query = Product.query.filter(Product.on_sale.is_(True))

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
