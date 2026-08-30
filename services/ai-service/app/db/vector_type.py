from pgvector.sqlalchemy import Vector
from sqlalchemy import Float
from sqlalchemy.types import JSON, TypeDecorator


class EmbeddingVector(TypeDecorator):
    """pgvector's native `vector(dim)` on Postgres; a plain JSON array on other dialects (SQLite,
    used in the offline test suite) so chunk *storage* stays testable everywhere. Similarity
    search (cosine_distance and friends) only exists on the Postgres column type — those queries
    are Postgres-only by nature and are verified against the real Docker stack, not offline."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int):
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return list(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return list(value)

    class comparator_factory(TypeDecorator.Comparator):
        """TypeDecorator doesn't inherit the impl's custom comparator methods automatically, so
        pgvector's distance operators are re-declared here (same operators
        pgvector.sqlalchemy.Vector itself uses). Only meaningful when the underlying column is a
        real Postgres `vector` column."""

        def cosine_distance(self, other):
            return self.op("<=>", return_type=Float)(other)

        def l2_distance(self, other):
            return self.op("<->", return_type=Float)(other)

        def max_inner_product(self, other):
            return self.op("<#>", return_type=Float)(other)
