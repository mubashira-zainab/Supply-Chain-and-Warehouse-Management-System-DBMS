"""SQL safety filter test (no database needed):  python tests/test_ai_safety.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_assistant as A

OK = ["SELECT * FROM product WHERE price > 1000",
      "select product_name from product where product_name ilike '%set%'",
      "WITH t AS (SELECT 1) SELECT * FROM t;", 'SELECT "product_name" FROM "product"',
      "SELECT w.location, SUM(s.quantity) FROM stock s JOIN warehouse w USING (warehouse_id) GROUP BY 1 -- note"]
BAD = ["DROP TABLE product", "SELECT 1; DELETE FROM product", "SELECT * FROM users", "select password from Users",
       "SELECT * FROM pg_catalog.pg_tables", "SELECT pg_sleep(10)", "SELECT * INTO x FROM product", "UPDATE product SET price=1",
       "SELECT * FROM product FOR UPDATE", "WITH d AS (DELETE FROM product RETURNING *) SELECT * FROM d",
       "SELECT * FROM information_schema.tables", "SELECT /* x */ * FROM Users", "SELECT current_setting('x')", "COPY product TO '/tmp/x'"]
bad_count = 0
for q in OK:
    A.validate_sql(q)
for q in BAD:
    try:
        A.validate_sql(q); print('ACCEPTED (BUG):', q); bad_count += 1
    except A.SqlRejected:
        pass
print(f"{len(OK)} safe queries accepted, {len(BAD) - bad_count}/{len(BAD)} harmful queries blocked")
sys.exit(1 if bad_count else 0)
