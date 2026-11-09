-- ============================================================
-- OPTIONAL (recommended for production): a database user that can ONLY read
-- Run once as the database owner, then put its connection string in
--   AI_DATABASE_URL=postgresql://scwms_ai:<password>@host/dbname?sslmode=require
-- The AI assistant will then use this user instead of the main one.
-- ============================================================
CREATE ROLE scwms_ai LOGIN PASSWORD 'change-this-password';
GRANT CONNECT ON DATABASE supply_chain_db TO scwms_ai;     -- use your real database name
GRANT USAGE ON SCHEMA public TO scwms_ai;
GRANT SELECT ON Supplier, Product, Warehouse, Customer, Stock, Orders, Shipment,
                Shipment_Tracking, ReorderRule, Inventory_Transaction,
                Low_Stock_Alert, Reorder_Alert, Order_Summary, Warehouse_Inventory,
                Product_Supplier_Detail, Supplier_Product_Summary, Shipment_Tracking_Detail
      TO scwms_ai;
-- NOTE: the Users table (password hashes) is intentionally NOT granted.
