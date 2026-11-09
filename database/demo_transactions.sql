-- ============================================================
-- Supply Chain & Warehouse Management System
-- Transaction Demo — COMMIT / ROLLBACK
-- Deliverable #16: COMMIT/ROLLBACK Demonstration
-- Deliverable #17: Concurrency Scenario
-- ============================================================

-- ============================================================
-- DEMO 1: Successful Transaction (COMMIT)
-- Scenario: Customer places an order — stock deducted atomically
-- ============================================================
BEGIN;

    -- Step 1: Verify stock before order
    SELECT get_stock(1, 1) AS stock_before;

    -- Step 2: Check sufficient stock
    -- (if insufficient, ROLLBACK will happen automatically via trigger)

    -- Step 3: Place order — trigger fn_reduce_stock fires automatically
    INSERT INTO Orders (Customer_ID, Product_ID, Quantity, Order_Date)
    VALUES (1, 1, 2, CURRENT_DATE);

    -- Step 4: Verify stock reduced
    SELECT get_stock(1, 1) AS stock_after;

COMMIT;

-- Expected result: stock_after = stock_before - 2


-- ============================================================
-- DEMO 2: Failed Transaction (ROLLBACK)
-- Scenario: Order exceeds available stock — entire transaction cancelled
-- ============================================================
BEGIN;

    -- Try to order 9999 units (exceeds stock)
    -- The trigger will raise EXCEPTION -> automatic ROLLBACK
    INSERT INTO Orders (Customer_ID, Product_ID, Quantity, Order_Date)
    VALUES (1, 8, 9999, CURRENT_DATE);  -- Nestle Yogurt, only 5 in stock

ROLLBACK;  -- Explicit rollback (trigger exception causes this automatically)

-- Expected result: No new order, stock unchanged


-- ============================================================
-- DEMO 3: Manual Stock Adjustment Transaction
-- Scenario: Admin corrects inventory discrepancy
-- ============================================================
BEGIN;

    -- Adjust stock for product 5 (Lipton Tea) at warehouse 1
    UPDATE Stock
    SET    Quantity = Quantity + 20
    WHERE  Product_ID = 5 AND Warehouse_ID = 1;

    -- Record the adjustment in ledger
    INSERT INTO Inventory_Transaction
        (Product_ID, Warehouse_ID, Trans_Type, Quantity, Reference_No, Notes)
    VALUES
        (5, 1, 'Adjustment', 20, 'ADJ-001', 'Physical count correction by admin');

COMMIT;


-- ============================================================
-- DEMO 4: Transfer Transaction
-- Scenario: Move stock from Multan to Lahore
-- ============================================================
BEGIN;

    -- Deduct from source warehouse (Multan = 1)
    UPDATE Stock
    SET    Quantity = Quantity - 10
    WHERE  Product_ID = 1 AND Warehouse_ID = 1;

    -- Add to destination warehouse (Lahore = 2)
    INSERT INTO Stock (Product_ID, Warehouse_ID, Quantity)
    VALUES (1, 2, 10)
    ON CONFLICT (Product_ID, Warehouse_ID)
    DO UPDATE SET Quantity = Stock.Quantity + EXCLUDED.Quantity;

    -- Log transfer out
    INSERT INTO Inventory_Transaction
        (Product_ID, Warehouse_ID, Trans_Type, Quantity, Reference_No, Notes)
    VALUES
        (1, 1, 'Transfer_Out', -10, 'TRF-001', 'Transfer to Lahore Hub');

    -- Log transfer in
    INSERT INTO Inventory_Transaction
        (Product_ID, Warehouse_ID, Trans_Type, Quantity, Reference_No, Notes)
    VALUES
        (1, 2, 'Transfer_In', 10, 'TRF-001', 'Received from Multan Central');

COMMIT;


-- ============================================================
-- CONCURRENCY SCENARIO (Deliverable #17)
-- ============================================================

-- SCENARIO: Two customers simultaneously order the last 5 units of a product.

-- Session A (Customer 1):
-- BEGIN;
-- INSERT INTO Orders (Customer_ID, Product_ID, Quantity, Order_Date)
-- VALUES (1, 8, 3, CURRENT_DATE);  -- requests 3 units (Nestle Yogurt)
-- [trigger checks stock = 5, proceeds]

-- Session B (Customer 2 — concurrent):
-- BEGIN;
-- INSERT INTO Orders (Customer_ID, Product_ID, Quantity, Order_Date)
-- VALUES (2, 8, 4, CURRENT_DATE);  -- requests 4 units
-- [PostgreSQL locks the Stock row for Product_ID=8]
-- [Session B WAITS until Session A commits or rolls back]

-- Session A commits:
-- COMMIT;  -> stock becomes 2

-- Session B resumes:
-- [trigger re-checks stock = 2, requested = 4 -> EXCEPTION -> ROLLBACK]
-- Session B gets error: "Insufficient stock. Available: 2, Requested: 4"

-- RESOLUTION: PostgreSQL's row-level locking ensures serializable correctness.
-- Only one transaction can update a Stock row at a time.
-- The second order is safely rejected if stock is insufficient.


-- ============================================================
-- EXPLAIN ANALYZE — Index Verification (Deliverable #18)
-- ============================================================

-- Query 1: Orders by status (uses idx_orders_status)
EXPLAIN ANALYZE
SELECT * FROM Orders WHERE Status = 'Pending';

-- Query 2: Stock by product (uses idx_stock_product)
EXPLAIN ANALYZE
SELECT * FROM Stock WHERE Product_ID = 1;

-- Query 3: Shipment by order (uses idx_shipment_order)
EXPLAIN ANALYZE
SELECT * FROM Shipment WHERE Order_ID = 3;
