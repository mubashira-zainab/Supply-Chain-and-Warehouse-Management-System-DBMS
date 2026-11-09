-- ============================================================
-- Supply Chain & Warehouse Management System
-- PostgreSQL Schema — Full DDL
-- Student:    Mubashira Zainab | BS Mathematics 5th Semester
-- University: CASPAM, BZU Multan
-- Course:     DBMS (COMP351) | Supervisor: Dr. Imran Javaid
-- Year:       2026
-- ============================================================

-- ── EXTENSIONS ──────────────────────────────────────────────
-- (none required for this project)

-- ── DROP EXISTING OBJECTS (clean reload) ────────────────────
DROP TABLE IF EXISTS Inventory_Transaction CASCADE;
DROP TABLE IF EXISTS ReorderRule          CASCADE;
DROP TABLE IF EXISTS Shipment_Tracking    CASCADE;
DROP TABLE IF EXISTS Shipment             CASCADE;
DROP TABLE IF EXISTS Orders               CASCADE;
DROP TABLE IF EXISTS Stock                CASCADE;
DROP TABLE IF EXISTS Customer             CASCADE;
DROP TABLE IF EXISTS Product              CASCADE;
DROP TABLE IF EXISTS Supplier             CASCADE;
DROP TABLE IF EXISTS Warehouse            CASCADE;
DROP TABLE IF EXISTS Users                CASCADE;
DROP VIEW  IF EXISTS Low_Stock_Alert;
DROP VIEW  IF EXISTS Order_Summary;
DROP VIEW  IF EXISTS Product_Supplier_Detail;
DROP VIEW  IF EXISTS Warehouse_Inventory;
DROP VIEW  IF EXISTS Reorder_Alert;
DROP VIEW  IF EXISTS Supplier_Product_Summary;
DROP VIEW  IF EXISTS Shipment_Tracking_Detail;
DROP FUNCTION IF EXISTS get_stock(INT, INT);

-- ============================================================
-- MASTER DATA TABLES (Deliverable #6: Relational Schema)
-- ============================================================

-- ── SUPPLIER ─────────────────────────────────────────────────
-- Business Rule BR1: Every product must be supplied by a registered supplier.
-- Business Rule BR2: Each supplier has a unique identity.
CREATE TABLE Supplier (
    Supplier_ID  SERIAL       PRIMARY KEY,
    Name         VARCHAR(100) NOT NULL,
    Contact      VARCHAR(20),
    Email        VARCHAR(100),
    Address      VARCHAR(200),
    CONSTRAINT chk_supplier_name CHECK (LENGTH(TRIM(Name)) > 0)
);

-- ── PRODUCT ──────────────────────────────────────────────────
-- Business Rule BR3: Each product belongs to exactly one supplier.
-- Business Rule BR4: Product price must be non-negative.
CREATE TABLE Product (
    Product_ID   SERIAL         PRIMARY KEY,
    Product_Name VARCHAR(100)   NOT NULL,
    Category     VARCHAR(50),
    Price        NUMERIC(10,2)  NOT NULL DEFAULT 0,
    Supplier_ID  INT            REFERENCES Supplier(Supplier_ID) ON DELETE SET NULL,
    CONSTRAINT chk_product_price    CHECK (Price >= 0),
    CONSTRAINT chk_product_name     CHECK (LENGTH(TRIM(Product_Name)) > 0)
);

-- ── WAREHOUSE ────────────────────────────────────────────────
-- Business Rule BR5: Each warehouse is identified by a unique location name.
CREATE TABLE Warehouse (
    Warehouse_ID SERIAL       PRIMARY KEY,
    Location     VARCHAR(100) NOT NULL,
    Latitude     NUMERIC(9,6),            -- map coordinates (used by shipment tracking)
    Longitude    NUMERIC(9,6),
    CONSTRAINT chk_warehouse_location CHECK (LENGTH(TRIM(Location)) > 0),
    CONSTRAINT chk_warehouse_lat CHECK (Latitude  BETWEEN -90  AND 90),
    CONSTRAINT chk_warehouse_lng CHECK (Longitude BETWEEN -180 AND 180)
);

-- ── CUSTOMER ─────────────────────────────────────────────────
-- Business Rule BR6: Each customer has a unique registration.
CREATE TABLE Customer (
    Customer_ID  SERIAL       PRIMARY KEY,
    Name         VARCHAR(100) NOT NULL,
    Phone        VARCHAR(20),
    Email        VARCHAR(100),
    Address      VARCHAR(200),
    Latitude     NUMERIC(9,6),            -- delivery point (used by shipment tracking)
    Longitude    NUMERIC(9,6),
    CONSTRAINT chk_customer_name CHECK (LENGTH(TRIM(Name)) > 0),
    CONSTRAINT chk_customer_lat CHECK (Latitude  BETWEEN -90  AND 90),
    CONSTRAINT chk_customer_lng CHECK (Longitude BETWEEN -180 AND 180)
);

-- ── USERS (Application Login) ────────────────────────────────
CREATE TABLE Users (
    User_ID   SERIAL       PRIMARY KEY,
    Username  VARCHAR(50)  NOT NULL UNIQUE,
    Password  VARCHAR(255) NOT NULL,   -- salted hash (werkzeug), never plain text
    Role      VARCHAR(20)  NOT NULL DEFAULT 'Admin',
    CONSTRAINT chk_role CHECK (Role IN ('Admin','Manager','Viewer'))
);

-- ============================================================
-- TRANSACTION TABLES
-- ============================================================

-- ── STOCK / INVENTORY ────────────────────────────────────────
-- Business Rule BR7: Stock quantity must never be negative.
-- Business Rule BR8: One product can be stored in multiple warehouses (M:N resolved).
-- Business Rule BR9: (Product_ID, Warehouse_ID) pair must be unique.
CREATE TABLE Stock (
    Stock_ID     SERIAL PRIMARY KEY,
    Product_ID   INT    NOT NULL REFERENCES Product(Product_ID)   ON DELETE CASCADE,
    Warehouse_ID INT    NOT NULL REFERENCES Warehouse(Warehouse_ID) ON DELETE CASCADE,
    Quantity     INT    NOT NULL DEFAULT 0,
    CONSTRAINT chk_stock_qty CHECK (Quantity >= 0),
    CONSTRAINT uq_product_warehouse UNIQUE (Product_ID, Warehouse_ID)
);

-- ── ORDERS ───────────────────────────────────────────────────
-- Business Rule BR10: Order quantity must be > 0.
-- Business Rule BR11: Order status follows a defined lifecycle.
-- Business Rule BR12: Stock is auto-deducted on order placement (via trigger).
CREATE TABLE Orders (
    Order_ID    SERIAL      PRIMARY KEY,
    Customer_ID INT         NOT NULL REFERENCES Customer(Customer_ID) ON DELETE CASCADE,
    Product_ID  INT         NOT NULL REFERENCES Product(Product_ID)   ON DELETE RESTRICT,
    Quantity    INT         NOT NULL,
    Order_Date  DATE        NOT NULL DEFAULT CURRENT_DATE,
    Status      VARCHAR(20) NOT NULL DEFAULT 'Pending',
    CONSTRAINT chk_order_qty    CHECK (Quantity > 0),
    CONSTRAINT chk_order_status CHECK (Status IN ('Pending','Processing','Shipped','Delivered','Cancelled'))
);

-- ── SHIPMENT ─────────────────────────────────────────────────
-- Business Rule BR13: A shipment is auto-created when order status becomes 'Shipped'.
-- Business Rule BR14: Each order has at most one shipment record.
CREATE TABLE Shipment (
    Shipment_ID         SERIAL      PRIMARY KEY,
    Order_ID            INT         NOT NULL UNIQUE REFERENCES Orders(Order_ID) ON DELETE CASCADE,
    Shipment_Date       DATE        NOT NULL DEFAULT CURRENT_DATE,
    Status              VARCHAR(20) NOT NULL DEFAULT 'In Transit',
    Carrier             VARCHAR(60) NOT NULL DEFAULT 'SC&WMS Logistics',
    Tracking_No         VARCHAR(30) UNIQUE,                       -- auto-generated by trigger
    Origin_Warehouse_ID INT         REFERENCES Warehouse(Warehouse_ID) ON DELETE SET NULL,
    CONSTRAINT chk_shipment_status CHECK (Status IN ('In Transit','Delivered','Returned'))
);

-- ── SHIPMENT TRACKING (GPS-style checkpoint log, drawn on the map) ───
-- Business Rule BR16: every movement of a shipment is an immutable event row.
-- Business Rule BR17: events carry coordinates so the route can be shown on a map.
CREATE TABLE Shipment_Tracking (
    Event_ID      SERIAL        PRIMARY KEY,
    Shipment_ID   INT           NOT NULL REFERENCES Shipment(Shipment_ID) ON DELETE CASCADE,
    Event_Type    VARCHAR(20)   NOT NULL,
    Location_Name VARCHAR(120)  NOT NULL,
    Latitude      NUMERIC(9,6),
    Longitude     NUMERIC(9,6),
    Note          TEXT,
    Event_Time    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_event_type CHECK (Event_Type IN
        ('Dispatched','In Transit','Out for Delivery','Delayed','Delivered','Returned'))
);

-- ── REORDER RULES ────────────────────────────────────────────
-- Business Rule BR15: Each (Product, Warehouse) pair may have a reorder rule.
-- Used for inventory intelligence alerts.
CREATE TABLE ReorderRule (
    Rule_ID       SERIAL PRIMARY KEY,
    Product_ID    INT    NOT NULL REFERENCES Product(Product_ID)   ON DELETE CASCADE,
    Warehouse_ID  INT    NOT NULL REFERENCES Warehouse(Warehouse_ID) ON DELETE CASCADE,
    Reorder_Point INT    NOT NULL DEFAULT 10,
    Safety_Stock  INT    NOT NULL DEFAULT 5,
    CONSTRAINT chk_reorder_point  CHECK (Reorder_Point >= 0),
    CONSTRAINT chk_safety_stock   CHECK (Safety_Stock  >= 0),
    CONSTRAINT uq_reorder_rule    UNIQUE (Product_ID, Warehouse_ID)
);

-- ── INVENTORY TRANSACTION LEDGER ─────────────────────────────
-- Deliverable #14 (supports audit trail / FMCG ledger)
-- Every stock movement is permanently recorded here.
CREATE TABLE Inventory_Transaction (
    Trans_ID      SERIAL       PRIMARY KEY,
    Product_ID    INT          NOT NULL REFERENCES Product(Product_ID)    ON DELETE RESTRICT,
    Warehouse_ID  INT          NOT NULL REFERENCES Warehouse(Warehouse_ID) ON DELETE RESTRICT,
    Trans_Type    VARCHAR(20)  NOT NULL,
    Quantity      INT          NOT NULL,
    Trans_Date    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Reference_No  VARCHAR(50),
    Notes         TEXT,
    CONSTRAINT chk_trans_type CHECK (Trans_Type IN
        ('Receipt','Sale','Return','Adjustment','Transfer_In','Transfer_Out'))
);

-- ============================================================
-- INDEXES (Deliverable #18: Index Justification)
-- ============================================================

-- idx_orders_status: Speeds up dashboard "Pending Orders" filter
CREATE INDEX idx_orders_status    ON Orders(Status);

-- idx_orders_customer: Speeds up customer order history lookups
CREATE INDEX idx_orders_customer  ON Orders(Customer_ID);

-- idx_stock_product: Speeds up stock lookup per product (used by trigger)
CREATE INDEX idx_stock_product    ON Stock(Product_ID);

-- idx_stock_warehouse: Speeds up warehouse inventory view
CREATE INDEX idx_stock_warehouse  ON Stock(Warehouse_ID);

-- idx_shipment_order: Speeds up shipment lookup by order
CREATE INDEX idx_shipment_order   ON Shipment(Order_ID);

-- idx_tracking_shipment: Speeds up the tracking timeline of one shipment
CREATE INDEX idx_tracking_shipment ON Shipment_Tracking(Shipment_ID, Event_Time);

-- idx_inv_trans_product: Speeds up ledger queries by product
CREATE INDEX idx_inv_trans_product ON Inventory_Transaction(Product_ID);

-- idx_inv_trans_date: Speeds up time-range queries on ledger
CREATE INDEX idx_inv_trans_date   ON Inventory_Transaction(Trans_Date);

-- ============================================================
-- VIEWS (Deliverable #13: Views)
-- ============================================================

-- View 1: Low Stock Alert — products with quantity below 10
CREATE VIEW Low_Stock_Alert AS
    SELECT
        p.Product_Name,
        p.Category,
        w.Location AS Warehouse,
        s.Quantity
    FROM  Stock     s
    JOIN  Product   p ON s.Product_ID   = p.Product_ID
    JOIN  Warehouse w ON s.Warehouse_ID = w.Warehouse_ID
    WHERE s.Quantity < 10
    ORDER BY s.Quantity ASC;

-- View 2: Order Summary — enriched order information
CREATE VIEW Order_Summary AS
    SELECT
        o.Order_ID,
        c.Name        AS Customer_Name,
        p.Product_Name,
        su.Name       AS Supplier_Name,
        o.Quantity,
        o.Order_Date,
        o.Status
    FROM  Orders   o
    JOIN  Customer c  ON o.Customer_ID = c.Customer_ID
    JOIN  Product  p  ON o.Product_ID  = p.Product_ID
    LEFT JOIN Supplier su ON p.Supplier_ID = su.Supplier_ID;

-- View 3: Product-Supplier Detail — joined product + supplier
CREATE VIEW Product_Supplier_Detail AS
    SELECT
        p.Product_ID,
        p.Product_Name,
        p.Category,
        p.Price,
        COALESCE(s.Name,'—')    AS Supplier_Name,
        COALESCE(s.Contact,'—') AS Supplier_Contact,
        COALESCE(s.Email,'—')   AS Supplier_Email
    FROM  Product  p
    LEFT JOIN Supplier s ON p.Supplier_ID = s.Supplier_ID;

-- View 4: Warehouse Inventory — full inventory by location
CREATE VIEW Warehouse_Inventory AS
    SELECT
        w.Warehouse_ID,
        w.Location,
        p.Product_ID,
        p.Product_Name,
        p.Category,
        s.Quantity
    FROM  Stock     s
    JOIN  Product   p ON s.Product_ID   = p.Product_ID
    JOIN  Warehouse w ON s.Warehouse_ID = w.Warehouse_ID
    ORDER BY w.Location, p.Product_Name;

-- View 5: Reorder Alert — products at or below reorder point
CREATE VIEW Reorder_Alert AS
    SELECT
        p.Product_Name,
        p.Category,
        w.Location          AS Warehouse,
        s.Quantity          AS Current_Stock,
        rr.Reorder_Point,
        rr.Safety_Stock,
        (rr.Reorder_Point - s.Quantity) AS Units_Needed
    FROM  Stock       s
    JOIN  Product     p  ON s.Product_ID   = p.Product_ID
    JOIN  Warehouse   w  ON s.Warehouse_ID = w.Warehouse_ID
    JOIN  ReorderRule rr ON s.Product_ID   = rr.Product_ID
                         AND s.Warehouse_ID = rr.Warehouse_ID
    WHERE s.Quantity <= rr.Reorder_Point
    ORDER BY s.Quantity ASC;

-- View 6: Supplier Product Summary — products per supplier
CREATE VIEW Supplier_Product_Summary AS
    SELECT
        s.Supplier_ID,
        s.Name          AS Supplier_Name,
        s.Contact,
        COUNT(p.Product_ID)    AS Total_Products,
        ROUND(AVG(p.Price),2)  AS Avg_Product_Price,
        SUM(COALESCE(st.Quantity,0)) AS Total_Stock
    FROM  Supplier s
    LEFT JOIN Product p  ON p.Supplier_ID  = s.Supplier_ID
    LEFT JOIN Stock   st ON st.Product_ID  = p.Product_ID
    GROUP BY s.Supplier_ID, s.Name, s.Contact
    ORDER BY Total_Products DESC;

-- View 7: Shipment Tracking Detail — everything the map page needs in one row
CREATE VIEW Shipment_Tracking_Detail AS
    SELECT
        sh.Shipment_ID, sh.Tracking_No, sh.Carrier, sh.Order_ID,
        sh.Status        AS Shipment_Status,
        sh.Shipment_Date,
        c.Name           AS Customer_Name,
        c.Address        AS Customer_Address,
        c.Latitude       AS Dest_Lat,  c.Longitude AS Dest_Lng,
        p.Product_Name,  o.Quantity,
        w.Warehouse_ID   AS Origin_Warehouse_ID,
        w.Location       AS Origin_Warehouse,
        w.Latitude       AS Origin_Lat, w.Longitude AS Origin_Lng,
        le.Event_Type    AS Last_Event,
        le.Location_Name AS Last_Location,
        le.Latitude      AS Last_Lat,  le.Longitude AS Last_Lng,
        le.Event_Time    AS Last_Event_Time
    FROM  Shipment sh
    JOIN  Orders   o ON sh.Order_ID    = o.Order_ID
    JOIN  Customer c ON o.Customer_ID  = c.Customer_ID
    JOIN  Product  p ON o.Product_ID   = p.Product_ID
    LEFT JOIN Warehouse w ON sh.Origin_Warehouse_ID = w.Warehouse_ID
    LEFT JOIN LATERAL (
        SELECT * FROM Shipment_Tracking t
        WHERE  t.Shipment_ID = sh.Shipment_ID
        ORDER  BY t.Event_Time DESC, t.Event_ID DESC
        LIMIT  1
    ) le ON TRUE;

-- ============================================================
-- STORED FUNCTION (Deliverable #14)
-- ============================================================

-- Function: Returns current stock quantity for a product at a warehouse.
-- Usage: SELECT get_stock(1, 2);
CREATE OR REPLACE FUNCTION get_stock(p_product_id INT, p_warehouse_id INT)
RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_qty INT;
BEGIN
    SELECT Quantity INTO v_qty
    FROM   Stock
    WHERE  Product_ID   = p_product_id
    AND    Warehouse_ID = p_warehouse_id;

    IF NOT FOUND THEN
        RETURN 0;
    END IF;

    RETURN v_qty;
END;
$$;

-- ============================================================
-- TRIGGERS (Deliverable #15)
-- ============================================================

-- ── TRIGGER 1: Auto-deduct stock when an order is placed ─────
CREATE OR REPLACE FUNCTION fn_reduce_stock()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_available INT;
    v_warehouse  INT;
BEGIN
    -- Find the warehouse with the highest stock for this product
    SELECT Warehouse_ID, Quantity
    INTO   v_warehouse, v_available
    FROM   Stock
    WHERE  Product_ID = NEW.Product_ID
    ORDER  BY Quantity DESC
    LIMIT  1;

    IF v_available IS NULL OR v_available < NEW.Quantity THEN
        RAISE EXCEPTION
            'Insufficient stock. Available: %, Requested: %',
            COALESCE(v_available, 0), NEW.Quantity;
    END IF;

    -- Deduct stock
    UPDATE Stock
    SET    Quantity = Quantity - NEW.Quantity
    WHERE  Product_ID   = NEW.Product_ID
    AND    Warehouse_ID = v_warehouse;

    -- Log to inventory ledger
    INSERT INTO Inventory_Transaction
        (Product_ID, Warehouse_ID, Trans_Type, Quantity, Reference_No, Notes)
    VALUES
        (NEW.Product_ID, v_warehouse, 'Sale', -NEW.Quantity,
         'ORD-' || NEW.Order_ID,
         'Auto-deducted by order trigger');

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_reduce_stock
AFTER INSERT ON Orders
FOR EACH ROW
EXECUTE FUNCTION fn_reduce_stock();

-- ── TRIGGER 2: Auto-create shipment when order → 'Shipped' ──
CREATE OR REPLACE FUNCTION fn_auto_shipment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.Status = 'Shipped' AND OLD.Status <> 'Shipped' THEN
        INSERT INTO Shipment (Order_ID, Shipment_Date, Status)
        VALUES (NEW.Order_ID, CURRENT_DATE, 'In Transit')
        ON CONFLICT (Order_ID) DO NOTHING;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_auto_shipment
AFTER UPDATE ON Orders
FOR EACH ROW
EXECUTE FUNCTION fn_auto_shipment();

-- ── TRIGGER 3: Log all stock additions to ledger ─────────────
CREATE OR REPLACE FUNCTION fn_log_stock_receipt()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Only log when stock is manually increased (not by order deduction)
    IF NEW.Quantity > OLD.Quantity THEN
        INSERT INTO Inventory_Transaction
            (Product_ID, Warehouse_ID, Trans_Type, Quantity, Reference_No, Notes)
        VALUES
            (NEW.Product_ID, NEW.Warehouse_ID, 'Receipt',
             NEW.Quantity - OLD.Quantity,
             'STK-' || NEW.Stock_ID,
             'Stock manually updated');
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_log_stock_receipt
AFTER UPDATE ON Stock
FOR EACH ROW
EXECUTE FUNCTION fn_log_stock_receipt();

-- ── TRIGGER 4: Prepare a new shipment (tracking number + origin warehouse) ──
-- Origin = the warehouse that supplied the order (found through the ledger entry
-- written by trg_reduce_stock, reference 'ORD-<order id>').
CREATE OR REPLACE FUNCTION fn_prepare_shipment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.Tracking_No IS NULL THEN
        NEW.Tracking_No := 'SCW' || TO_CHAR(NEW.Shipment_Date, 'YYMMDD')
                                 || LPAD(NEW.Order_ID::TEXT, 4, '0');
    END IF;

    IF NEW.Origin_Warehouse_ID IS NULL THEN
        SELECT Warehouse_ID INTO NEW.Origin_Warehouse_ID
        FROM   Inventory_Transaction
        WHERE  Reference_No = 'ORD-' || NEW.Order_ID
        AND    Trans_Type   = 'Sale'
        ORDER  BY Trans_ID
        LIMIT  1;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prepare_shipment
BEFORE INSERT ON Shipment
FOR EACH ROW
EXECUTE FUNCTION fn_prepare_shipment();

-- ── TRIGGER 5: First tracking event = "Dispatched" from the origin warehouse ──
CREATE OR REPLACE FUNCTION fn_first_tracking_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    w RECORD;
BEGIN
    SELECT Location, Latitude, Longitude INTO w
    FROM   Warehouse WHERE Warehouse_ID = NEW.Origin_Warehouse_ID;

    IF FOUND THEN
        INSERT INTO Shipment_Tracking
            (Shipment_ID, Event_Type, Location_Name, Latitude, Longitude, Note, Event_Time)
        VALUES
            (NEW.Shipment_ID, 'Dispatched', w.Location, w.Latitude, w.Longitude,
             'Picked up and dispatched by ' || NEW.Carrier,
             CASE WHEN NEW.Shipment_Date >= CURRENT_DATE THEN CURRENT_TIMESTAMP
                  ELSE NEW.Shipment_Date + TIME '09:00' END);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_first_tracking_event
AFTER INSERT ON Shipment
FOR EACH ROW
EXECUTE FUNCTION fn_first_tracking_event();

-- ── TRIGGER 6: Shipment status change -> tracking event + order sync ────────
CREATE OR REPLACE FUNCTION fn_shipment_status_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    c RECORD;
    w RECORD;
BEGIN
    IF NEW.Status = 'Delivered' THEN
        SELECT cu.Address, cu.Latitude, cu.Longitude INTO c
        FROM   Orders o JOIN Customer cu ON o.Customer_ID = cu.Customer_ID
        WHERE  o.Order_ID = NEW.Order_ID;

        INSERT INTO Shipment_Tracking
            (Shipment_ID, Event_Type, Location_Name, Latitude, Longitude, Note)
        VALUES
            (NEW.Shipment_ID, 'Delivered', COALESCE(c.Address, 'Customer address'),
             c.Latitude, c.Longitude, 'Delivered to customer');

        UPDATE Orders SET Status = 'Delivered'
        WHERE  Order_ID = NEW.Order_ID AND Status <> 'Delivered';

    ELSIF NEW.Status = 'Returned' THEN
        SELECT Location, Latitude, Longitude INTO w
        FROM   Warehouse WHERE Warehouse_ID = NEW.Origin_Warehouse_ID;

        INSERT INTO Shipment_Tracking
            (Shipment_ID, Event_Type, Location_Name, Latitude, Longitude, Note)
        VALUES
            (NEW.Shipment_ID, 'Returned', COALESCE(w.Location, 'Origin warehouse'),
             w.Latitude, w.Longitude, 'Shipment returned to origin');
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_shipment_status_event
AFTER UPDATE ON Shipment
FOR EACH ROW
WHEN (OLD.Status IS DISTINCT FROM NEW.Status)
EXECUTE FUNCTION fn_shipment_status_event();

-- ============================================================
-- END OF SCHEMA
-- ============================================================
