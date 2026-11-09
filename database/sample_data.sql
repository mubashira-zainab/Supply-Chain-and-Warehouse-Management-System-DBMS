-- ============================================================
-- Supply Chain & Warehouse Management System
-- Sample Dataset — Pakistani Business Data
-- Student:    Mubashira Zainab | BS Mathematics 5th Semester
-- University: CASPAM, BZU Multan
-- Course:     DBMS (COMP351) | Supervisor: Dr. Imran Javaid
-- Deliverable #9: Realistic Sample Dataset
-- Deliverable #10: DML Scripts
-- ============================================================

-- ── USERS ────────────────────────────────────────────────────
INSERT INTO Users (Username, Password, Role) VALUES
('admin',   'scrypt:32768:8:1$jOWXX2UPkaot25wA$3b9740c34a7032b456768c7d396f82c374f8c6a41b5a2c36895916cb68efc0c454b7cc90308462934f75ffafd703fb72b479c90d18213d09271bc8acafc784a5', 'Admin'),
('manager', 'scrypt:32768:8:1$8WF3o1anMuv3RN50$4cfeaea0c1a7bf5254de7859ea877b88af5ab2cf57e861e11df671af7f7b41e104d97ff0c8b00f35dc55e350de31c6eb9015f63464d81f736821a0988701eb59', 'Manager'),
('viewer',  'scrypt:32768:8:1$VDATxMyeeXOpbQZc$138a53fe0a0b2cb378fd6290bedd0c5c836c58905e9e9d56132541da8d11a8a1291d0e771021dfcd5c6e46aab7afb13407d5702578d126d67d5658e1b03e77d7', 'Viewer');
-- demo logins: admin/admin123 · manager/manager123 · viewer/viewer123  (passwords are stored hashed)

-- ── SUPPLIERS ────────────────────────────────────────────────
INSERT INTO Supplier (Name, Contact, Email, Address) VALUES
('Pak Agro Traders',      '0300-1234567', 'pakagro@gmail.com',     'Industrial Area, Lahore'),
('National Foods Ltd',    '0301-9876543', 'info@nationalfoods.pk', 'Korangi, Karachi'),
('Unilever Pakistan',     '051-111-8722', 'supply@unilever.pk',    'Blue Area, Islamabad'),
('Punjab Dairy Products', '0311-5556666', 'info@punjabdairy.pk',   'Faisalabad Industrial Zone'),
('Multan Steel Works',    '061-4512345',  'sales@multansteel.pk',  'Bosan Road, Multan');

-- ── PRODUCTS ─────────────────────────────────────────────────
INSERT INTO Product (Product_Name, Category, Price, Supplier_ID) VALUES
('Basmati Rice 5kg',        'Grains',      850.00,   1),
('Wheat Flour 10kg',        'Grains',      950.00,   1),
('National Salt 1kg',       'Condiments',  55.00,    2),
('Rafhan Corn Oil 5L',      'Edible Oil',  2200.00,  2),
('Lipton Yellow Label Tea', 'Beverages',   1200.00,  3),
('Surf Excel 1kg',          'Detergent',   450.00,   3),
('Olpers Milk 1L',          'Dairy',       280.00,   4),
('Nestle Yogurt 400g',      'Dairy',       150.00,   4),
('Steel Pipe 1inch',        'Hardware',    3500.00,  5),
('Corrugated Sheet',        'Hardware',    8500.00,  5);

-- ── WAREHOUSES ───────────────────────────────────────────────
INSERT INTO Warehouse (Location, Latitude, Longitude) VALUES
('Multan Central Warehouse', 30.1575, 71.5249),
('Lahore Distribution Hub', 31.5204, 74.3587),
('Karachi South Warehouse', 24.8607, 67.0011);

-- ── STOCK (Inventory) ────────────────────────────────────────
INSERT INTO Stock (Product_ID, Warehouse_ID, Quantity) VALUES
-- Multan Warehouse
(1, 1, 120),  -- Basmati Rice
(2, 1, 90),   -- Wheat Flour
(3, 1, 200),  -- National Salt
(4, 1, 45),   -- Corn Oil
(5, 1, 8),    -- Lipton Tea  (LOW STOCK)
(6, 1, 60),   -- Surf Excel
(7, 1, 35),   -- Olpers Milk
(8, 1, 5),    -- Nestle Yogurt (LOW STOCK)
-- Lahore Warehouse
(1, 2, 80),   -- Basmati Rice
(2, 2, 50),   -- Wheat Flour
(4, 2, 30),   -- Corn Oil
(5, 2, 25),   -- Lipton Tea
(6, 2, 40),   -- Surf Excel
(9, 2, 15),   -- Steel Pipe
-- Karachi Warehouse
(3, 3, 300),  -- National Salt
(4, 3, 70),   -- Corn Oil
(7, 3, 20),   -- Olpers Milk
(10, 3, 6);   -- Corrugated Sheet (LOW STOCK)

-- ── REORDER RULES ────────────────────────────────────────────
INSERT INTO ReorderRule (Product_ID, Warehouse_ID, Reorder_Point, Safety_Stock) VALUES
(1, 1, 30, 15),  -- Basmati Rice — Multan
(2, 1, 25, 10),  -- Wheat Flour  — Multan
(4, 1, 20, 8),   -- Corn Oil     — Multan
(5, 1, 15, 5),   -- Lipton Tea   — Multan (already below reorder!)
(7, 1, 20, 8),   -- Olpers Milk  — Multan
(5, 2, 20, 8),   -- Lipton Tea   — Lahore
(9, 2, 10, 4),   -- Steel Pipe   — Lahore
(10,3, 10, 4);   -- Corrugated Sheet — Karachi

-- ── CUSTOMERS ────────────────────────────────────────────────
INSERT INTO Customer (Name, Phone, Email, Address, Latitude, Longitude) VALUES
('Ali Hassan', '0300-1111111', 'ali.hassan@gmail.com', 'Model Town, Lahore', 31.5204, 74.3587),
('Fatima Zahra', '0311-2222222', 'fatima.z@hotmail.com', 'F-8 Sector, Islamabad', 33.6844, 73.0479),
('Hamza Malik', '0333-3333333', 'hamza.malik@yahoo.com', 'Gulshan-e-Iqbal, Karachi', 24.8607, 67.0011),
('Sara Noor', '0321-4444444', 'sara.noor@gmail.com', 'Cantt Area, Multan', 30.1575, 71.5249),
('Usman Traders LLC', '061-9876543', 'usman.traders@biz.pk', 'Hussain Agahi, Multan', 30.1575, 71.5249);

-- ── ORDERS ───────────────────────────────────────────────────
INSERT INTO Orders (Customer_ID, Product_ID, Quantity, Order_Date, Status) VALUES
(1, 1, 5,  '2026-09-01', 'Delivered'),
(2, 5, 3,  '2026-09-05', 'Delivered'),
(3, 6, 10, CURRENT_DATE - 3, 'Shipped'),
(4, 10, 2, CURRENT_DATE - 2, 'Shipped'),
(5, 2, 20, '2026-09-18', 'Processing'),
(1, 4, 4,  '2026-09-20', 'Pending'),
(2, 3, 15, '2026-09-22', 'Pending'),
(3, 9, 2,  '2026-09-25', 'Pending');

-- ── SHIPMENTS ────────────────────────────────────────────────
INSERT INTO Shipment (Order_ID, Shipment_Date, Status) VALUES
(1, '2026-09-02',       'Delivered'),
(2, '2026-09-06',       'Delivered'),
(3, CURRENT_DATE - 2,   'In Transit'),
(4, CURRENT_DATE - 1,   'In Transit');
-- Tracking_No, Origin warehouse and the first "Dispatched" event are created automatically
-- by triggers trg_prepare_shipment and trg_first_tracking_event.

-- ── SHIPMENT TRACKING HISTORY (checkpoints drawn on the map) ─
INSERT INTO Shipment_Tracking (Shipment_ID, Event_Type, Location_Name, Latitude, Longitude, Note, Event_Time) VALUES
-- #1  Multan -> Lahore (delivered)
(1, 'In Transit',       'Sahiwal Transit Hub',   30.6682, 73.1114, 'Scanned at sorting hub',      '2026-09-02 15:30'),
(1, 'Out for Delivery', 'Lahore Delivery Station', 31.5204, 74.3587, 'Out for delivery',            '2026-09-03 08:45'),
(1, 'Delivered',        'Model Town, Lahore',    31.5204, 74.3587, 'Delivered to customer',        '2026-09-03 12:10'),
-- #2  Lahore -> Islamabad (delivered)
(2, 'In Transit',       'Jhelum Transit Hub',    32.9345, 73.731, 'Scanned at sorting hub',       '2026-09-06 14:00'),
(2, 'Delivered',        'F-8 Sector, Islamabad', 33.6844, 73.0479,    'Delivered to customer',        '2026-09-07 11:20'),
-- #3  Multan -> Karachi (in transit, currently near Sukkur)
(3, 'In Transit',       'Bahawalpur Transit Hub', 29.3956, 71.6836,   'Scanned at sorting hub',       (CURRENT_DATE - 2) + TIME '15:30'),
(3, 'In Transit',       'Rahim Yar Khan Hub',    28.4202, 70.2952,    'Scanned at sorting hub',       (CURRENT_DATE - 1) + TIME '07:40'),
(3, 'In Transit',       'Sukkur Transit Hub',    27.7052, 68.8574,    'Departed hub, on schedule',    (CURRENT_DATE - 1) + TIME '19:05'),
-- #4  Karachi -> Multan (in transit, currently near Nawabshah)
(4, 'In Transit',       'Hyderabad Transit Hub', 25.396, 68.3578,    'Scanned at sorting hub',       (CURRENT_DATE - 1) + TIME '14:20'),
(4, 'In Transit',       'Nawabshah Transit Hub', 26.2442, 68.41,    'Scanned at sorting hub',       (CURRENT_DATE - 1) + TIME '22:10');

-- ── INVENTORY TRANSACTION LEDGER (initial receipts) ─────────
INSERT INTO Inventory_Transaction
    (Product_ID, Warehouse_ID, Trans_Type, Quantity, Reference_No, Notes)
VALUES
(1, 1, 'Receipt', 120, 'PO-001', 'Initial stock receipt from Pak Agro Traders'),
(2, 1, 'Receipt', 90,  'PO-002', 'Initial stock receipt'),
(3, 1, 'Receipt', 200, 'PO-003', 'Initial stock receipt from National Foods'),
(4, 1, 'Receipt', 45,  'PO-004', 'Initial stock receipt'),
(5, 1, 'Receipt', 10,  'PO-005', 'Initial stock receipt from Unilever'),
(6, 1, 'Receipt', 60,  'PO-006', 'Initial stock receipt'),
(7, 1, 'Receipt', 35,  'PO-007', 'Initial stock receipt from Punjab Dairy'),
(8, 1, 'Receipt', 5,   'PO-008', 'Initial stock receipt'),
(1, 2, 'Receipt', 80,  'PO-009', 'Initial stock receipt — Lahore Hub'),
(2, 2, 'Receipt', 50,  'PO-010', 'Initial stock receipt — Lahore Hub'),
(5, 1, 'Sale',   -2,   'ORD-001', 'Sold via Order #1 (corrected ledger entry)'),
(5, 1, 'Sale',   -3,   'ORD-002', 'Sold via Order #2');

-- ============================================================
-- DML DEMO SCRIPTS (Deliverable #10)
-- ============================================================

-- DEMO 1: SELECT — all products with price > 1000
-- SELECT * FROM Product WHERE Price > 1000 ORDER BY Price DESC;

-- DEMO 2: UPDATE — change order status
-- UPDATE Orders SET Status = 'Processing' WHERE Order_ID = 5;

-- DEMO 3: DELETE — remove a cancelled order
-- DELETE FROM Orders WHERE Order_ID = 99 AND Status = 'Cancelled';

-- DEMO 4: AGGREGATE — average price per category
-- SELECT Category, COUNT(*) AS Products, ROUND(AVG(Price),2) AS Avg_Price
-- FROM Product GROUP BY Category ORDER BY Avg_Price DESC;

-- DEMO 5: JOIN — order details with customer and product
-- SELECT o.Order_ID, c.Name, p.Product_Name, o.Quantity, o.Status
-- FROM Orders o
-- JOIN Customer c ON o.Customer_ID = c.Customer_ID
-- JOIN Product  p ON o.Product_ID  = p.Product_ID;

-- DEMO 6: SUBQUERY — products never ordered
-- SELECT Product_Name FROM Product
-- WHERE Product_ID NOT IN (SELECT DISTINCT Product_ID FROM Orders);

-- DEMO 7: HAVING — warehouses with total stock > 100
-- SELECT w.Location, SUM(s.Quantity) AS Total_Stock
-- FROM Stock s JOIN Warehouse w ON s.Warehouse_ID = w.Warehouse_ID
-- GROUP BY w.Location HAVING SUM(s.Quantity) > 100;

-- DEMO 8: Function call
-- SELECT get_stock(1, 1);  -- Stock of product 1 in warehouse 1
