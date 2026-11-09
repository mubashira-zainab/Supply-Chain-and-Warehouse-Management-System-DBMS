# Supply Chain & Warehouse Management System
## Academic Documentation — 20 Deliverables
**Student:** Mubashira Zainab | BS Mathematics 5th Semester | CASPAM, BZU Multan
**Course:** DBMS (COMP351) | **Supervisor:** Dr. Imran Javaid | 2026

---

## Deliverable 1: Business Problem & Scope

**Problem Statement:**
Businesses managing physical goods across multiple warehouses face critical challenges:
- No real-time visibility into stock levels across locations
- Manual tracking leads to stockouts, over-ordering, and wasted resources
- No audit trail for inventory movements
- Delayed detection of low-stock conditions leads to lost sales

**Our Solution — Supply Chain & Warehouse Management System (SCWMS):**
A PostgreSQL-backed web application that digitizes the entire supply chain pipeline:
`Supplier → Product → Warehouse → Stock → Order → Shipment`

**System Boundary (In Scope):**
- Supplier registration and management
- Product catalog with category and pricing
- Multi-warehouse stock tracking
- Customer registration
- Order placement with automatic stock deduction
- Shipment tracking
- Inventory intelligence: low stock alerts, reorder alerts, audit ledger

**Out of Scope:** Payment processing, route optimization, employee HR module

---

## Deliverable 2: Terminology Sheet

| FMCG/DBMS Term | Definition | In Our System |
|---|---|---|
| SKU (Stock Keeping Unit) | Unique identifier for a product variant | Product_ID |
| Inventory | Goods held in a warehouse | Stock table |
| Reorder Point | Quantity level triggering replenishment | ReorderRule.Reorder_Point |
| Safety Stock | Buffer stock against demand spikes | ReorderRule.Safety_Stock |
| Stockout | Condition when quantity = 0 | Detected via Low_Stock_Alert view |
| Lead Time | Time between order and receipt | Tracked via Order_Date vs Shipment_Date |
| OTIF | On-Time-In-Full delivery metric | Shipment status tracking |
| Audit Trail | Record of every inventory change | Inventory_Transaction table |
| Stock Ledger | Chronological log of all movements | Inventory_Transaction |
| POS | Point of Sale | Orders table (customer purchases) |
| FIFO | First In First Out | Stock deduction strategy |
| FEFO | First Expire First Out | Applicable to perishables |
| Replenishment | Restocking from supplier | Add Stock operation |
| Dispatch | Sending goods from warehouse | Shipment creation |
| In Transit | Goods shipped but not yet received | Shipment.Status = 'In Transit' |

---

## Deliverable 3: Actor List

| Actor | Role | System Interactions |
|---|---|---|
| Admin | Full system access | All CRUD operations, user management |
| Manager | Operational management | View reports, update orders, manage stock |
| Viewer | Read-only access | View dashboard, reports only |
| Supplier (external) | Provides products | Registered in Supplier table |
| Customer (external) | Places orders | Registered in Customer table |
| PostgreSQL Triggers | Automated actors | Auto-deduct stock, auto-create shipments |

---

## Deliverable 4: Business-Rule Catalogue

| Rule ID | Business Rule | Enforcement Method |
|---|---|---|
| BR-01 | Every product must be supplied by a registered supplier | FK: Product.Supplier_ID → Supplier |
| BR-02 | Supplier name cannot be empty | CHECK (LENGTH(TRIM(Name)) > 0) |
| BR-03 | Product price must be ≥ 0 | CHECK (Price >= 0) |
| BR-04 | Product name cannot be empty | CHECK (LENGTH(TRIM(Product_Name)) > 0) |
| BR-05 | Stock quantity must never be negative | CHECK (Quantity >= 0) |
| BR-06 | One product at one warehouse = one stock record | UNIQUE (Product_ID, Warehouse_ID) |
| BR-07 | Order quantity must be > 0 | CHECK (Quantity > 0) |
| BR-08 | Order status must follow defined lifecycle | CHECK (Status IN ('Pending','Processing','Shipped','Delivered','Cancelled')) |
| BR-09 | Stock is auto-deducted when order is placed | Trigger: trg_reduce_stock |
| BR-10 | Cannot order more than available stock | Exception raised in trigger fn_reduce_stock |
| BR-11 | Shipment auto-created when order → 'Shipped' | Trigger: trg_auto_shipment |
| BR-12 | Each order has at most one shipment | UNIQUE constraint on Shipment.Order_ID |
| BR-13 | Shipment status follows defined values | CHECK (Status IN ('In Transit','Delivered','Returned')) |
| BR-14 | Every stock change is logged in audit ledger | Trigger: trg_log_stock_receipt |
| BR-15 | Reorder point must be ≥ 0 | CHECK (Reorder_Point >= 0) |

---

## Deliverable 7: Normalization Analysis

### Unnormalized Form (UNF) — Before Design

Consider if all data was in one flat table:

```
FLAT_TABLE(Order_ID, Customer_Name, Customer_Phone, Customer_Email,
           Product_Name, Category, Price,
           Supplier_Name, Supplier_Contact,
           Warehouse_Location, Stock_Quantity,
           Order_Date, Status)
```

**Problems:**
- Customer info repeats per order → Update Anomaly
- Supplier info repeats per product → Update Anomaly
- Cannot add a supplier without a product → Insertion Anomaly
- Deleting last order loses customer data → Deletion Anomaly

---

### 1NF (First Normal Form)

**Rule:** Atomic values, no repeating groups, each row uniquely identifiable.

Applied:
- Separate tables for each entity: Supplier, Product, Warehouse, Customer, Stock, Orders, Shipment
- Each column holds atomic values (no multi-valued attributes)
- Each table has a primary key

**Result:** All 8 tables are in 1NF.

---

### 2NF (Second Normal Form)

**Rule:** 1NF + No partial dependencies (every non-key attribute depends on the FULL primary key).

**Stock Table Analysis:**
- PK: `(Product_ID, Warehouse_ID)` — composite key
- `Quantity` depends on BOTH Product_ID AND Warehouse_ID
- No partial dependency — full functional dependency

**All tables checked:**
```
Supplier_ID → Name, Contact, Email, Address          ✓ Full FD
Product_ID  → Product_Name, Category, Price, Supplier_ID  ✓ Full FD
(Product_ID, Warehouse_ID) → Quantity                ✓ Full FD
Order_ID → Customer_ID, Product_ID, Quantity, Status ✓ Full FD
```

**Result:** All tables are in 2NF.

---

### 3NF (Third Normal Form)

**Rule:** 2NF + No transitive dependencies (non-key attributes must not depend on other non-key attributes).

**Before 3NF (hypothetical violation):**
```
Orders(Order_ID, Customer_ID, Customer_Name, Customer_City, Product_ID, ...)
```
- `Order_ID → Customer_ID → Customer_Name` — TRANSITIVE dependency!

**After 3NF (our actual design):**
```
Orders(Order_ID, Customer_ID, Product_ID, Quantity, Order_Date, Status)
Customer(Customer_ID, Name, Phone, Email, Address)
```
- `Order_ID → Customer_ID` (FK reference only)
- `Customer_ID → Name, Phone, ...` (in separate table)
- No transitive dependency in Orders

**All transitive dependencies removed:**
- Supplier info → separate Supplier table (not repeated in Product)
- Warehouse info → separate Warehouse table (not repeated in Stock)
- Customer info → separate Customer table (not repeated in Orders)

**Result:** All tables are in 3NF. ✓

---

## Deliverable 5: ER Diagram (Text Representation)

```
SUPPLIER (PK: Supplier_ID)
    |
    | 1:N (One supplier → many products)
    |
PRODUCT (PK: Product_ID, FK: Supplier_ID)
    |
    | M:N resolved by Stock
    |
STOCK (PK: Stock_ID, FK: Product_ID + Warehouse_ID)
    |
WAREHOUSE (PK: Warehouse_ID)

CUSTOMER (PK: Customer_ID)
    |
    | 1:N (One customer → many orders)
    |
ORDERS (PK: Order_ID, FK: Customer_ID + Product_ID)
    |
    | 1:1 (One order → at most one shipment)
    |
SHIPMENT (PK: Shipment_ID, FK: Order_ID)

REORDERRULE (PK: Rule_ID, FK: Product_ID + Warehouse_ID)
INVENTORY_TRANSACTION (PK: Trans_ID, FK: Product_ID + Warehouse_ID)
```

---

## Deliverable 6: Relational Schema

```
Supplier     (Supplier_ID*, Name, Contact, Email, Address)
Product      (Product_ID*, Product_Name, Category, Price, Supplier_ID^)
Warehouse    (Warehouse_ID*, Location)
Customer     (Customer_ID*, Name, Phone, Email, Address)
Stock        (Stock_ID*, Product_ID^, Warehouse_ID^, Quantity)
Orders       (Order_ID*, Customer_ID^, Product_ID^, Quantity, Order_Date, Status)
Shipment     (Shipment_ID*, Order_ID^, Shipment_Date, Status)
ReorderRule  (Rule_ID*, Product_ID^, Warehouse_ID^, Reorder_Point, Safety_Stock)
Inventory_Transaction (Trans_ID*, Product_ID^, Warehouse_ID^, Trans_Type,
                       Quantity, Trans_Date, Reference_No, Notes)
Users        (User_ID*, Username, Password, Role)

* = Primary Key    ^ = Foreign Key
```

---

## Deliverable 10: DML Scripts Summary

```sql
-- INSERT: Add new supplier
INSERT INTO Supplier (Name, Contact, Email, Address)
VALUES ('New Supplier', '0300-0000000', 'new@supplier.pk', 'Multan');

-- SELECT with JOIN: Customer order history
SELECT o.Order_ID, p.Product_Name, o.Quantity, o.Status
FROM Orders o
JOIN Product p ON o.Product_ID = p.Product_ID
WHERE o.Customer_ID = 1;

-- UPDATE: Change order status
UPDATE Orders SET Status = 'Processing' WHERE Order_ID = 5;

-- DELETE: Remove cancelled order
DELETE FROM Orders WHERE Order_ID = 99 AND Status = 'Cancelled';

-- AGGREGATE with GROUP BY and HAVING:
SELECT Category, COUNT(*) AS Products, ROUND(AVG(Price),2) AS Avg_Price
FROM Product
GROUP BY Category
HAVING COUNT(*) > 1
ORDER BY Avg_Price DESC;
```
