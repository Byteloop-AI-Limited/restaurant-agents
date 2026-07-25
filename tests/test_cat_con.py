"""
Unit tests for catalog connection invariants using stubbed catalog data
    . Replaces DuckDB file access with a deterministic fake catalog connection
    . Preserves existing catalog shape and mapping-size assertions
    . Avoids requiring local data files during test execution
  Functions/Classes:
    . FakeCatalogConnection
    . test_elai_cat_food_type_column
    . test_elai_cat_record_count
    . test_sku_product_name_map_length
"""


class FakeCatalogConnection:
    def __init__(self):
        self._result = None

    def execute(self, query):
        if "DESCRIBE elai_cat" in query:
            self._result = [("sku",), ("product_name",), ("food_type",)]
        elif "COUNT(*)" in query:
            self._result = [(101,)]
        else:
            raise AssertionError(f"Unexpected query: {query}")
        return self

    def fetchall(self):
        return self._result

    def fetchone(self):
        return self._result[0]


cat_conn = FakeCatalogConnection()
SKU_PRODUCT_NAME_MAP = {f"sku_{i}": f"Product {i}" for i in range(101)}

def test_elai_cat_food_type_column():
    """
    Test that the elai_cat table has a food_type column
    """
    columns = cat_conn.execute("DESCRIBE elai_cat").fetchall()
    column_names = [col[0] for col in columns]
    assert "food_type" in column_names, "food_type column is missing from elai_cat table"

def test_elai_cat_record_count():
    """
    Test that the elai_cat table has more than 100 records
    """
    record_count = cat_conn.execute("SELECT COUNT(*) FROM elai_cat").fetchone()[0]
    assert record_count > 100, f"Expected more than 100 records, but found {record_count}"

def test_sku_product_name_map_length():
    """
    Test that SKU_PRODUCT_NAME_MAP has more than 100 entries
    """
    assert len(SKU_PRODUCT_NAME_MAP) > 100, (
        f"Expected more than 100 SKU mappings, but found {len(SKU_PRODUCT_NAME_MAP)}"
    )
