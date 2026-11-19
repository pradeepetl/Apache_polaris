-- ============================================================
-- Trino Federation Sample Queries
-- ============================================================
-- Catalogs:
--   postgres  — PostgreSQL (customers, products)
--   iceberg   — Iceberg tables on MinIO/S3 (orders, order_items)
--   tpch      — TPC-H benchmark data (generated)
-- ============================================================

-- ========================
-- 1. Query PostgreSQL
-- ========================

-- List all customers
SELECT * FROM postgres.public.customers;

-- Customers by country
SELECT country, COUNT(*) AS customer_count
FROM postgres.public.customers
GROUP BY country
ORDER BY customer_count DESC;

-- Products by category with average price
SELECT category, COUNT(*) AS num_products, ROUND(AVG(price), 2) AS avg_price
FROM postgres.public.products
GROUP BY category
ORDER BY avg_price DESC;

-- ========================
-- 2. Set up Iceberg tables
-- ========================

-- Create a schema in the Iceberg catalog
CREATE SCHEMA IF NOT EXISTS iceberg.shop
  WITH (location = 's3://warehouse/polaris_warehouse/shop');

-- Create orders table
CREATE TABLE iceberg.shop.orders (
    order_id BIGINT,
    customer_id BIGINT,
    order_date DATE,
    status VARCHAR,
    total_amount DECIMAL(10, 2)
) WITH (format = 'PARQUET');

-- Create order_items table
CREATE TABLE iceberg.shop.order_items (
    item_id BIGINT,
    order_id BIGINT,
    product_id BIGINT,
    quantity INT,
    unit_price DECIMAL(10, 2)
) WITH (format = 'PARQUET');

-- Insert sample orders (references customer_ids from Postgres)
INSERT INTO iceberg.shop.orders VALUES
(1001, 1, DATE '2024-01-10', 'shipped', 1349.97),
(1002, 2, DATE '2024-01-12', 'shipped', 89.98),
(1003, 3, DATE '2024-01-15', 'delivered', 449.99),
(1004, 1, DATE '2024-01-20', 'delivered', 59.98),
(1005, 5, DATE '2024-02-01', 'shipped', 1299.99),
(1006, 7, DATE '2024-02-05', 'processing', 199.99),
(1007, 10, DATE '2024-02-10', 'shipped', 639.98),
(1008, 4, DATE '2024-02-14', 'delivered', 129.98),
(1009, 8, DATE '2024-02-20', 'shipped', 399.99),
(1010, 6, DATE '2024-03-01', 'processing', 89.99),
(1011, 12, DATE '2024-03-05', 'shipped', 1749.97),
(1012, 15, DATE '2024-03-10', 'delivered', 49.99),
(1013, 14, DATE '2024-03-15', 'processing', 269.98),
(1014, 9, DATE '2024-03-20', 'shipped', 109.99),
(1015, 20, DATE '2024-03-25', 'delivered', 529.98);

-- Insert sample order items (references product_ids from Postgres)
INSERT INTO iceberg.shop.order_items VALUES
(1, 1001, 1, 1, 1299.99),
(2, 1001, 2, 1, 29.99),
(3, 1001, 14, 1, 19.99),
(4, 1002, 4, 1, 89.99),
(5, 1003, 7, 1, 449.99),
(6, 1004, 3, 1, 49.99),
(7, 1004, 10, 1, 8.99),
(8, 1005, 1, 1, 1299.99),
(9, 1006, 13, 1, 199.99),
(10, 1007, 6, 1, 599.99),
(11, 1007, 8, 1, 39.99),
(12, 1008, 17, 1, 109.99),
(13, 1008, 14, 1, 19.99),
(14, 1009, 5, 1, 399.99),
(15, 1010, 4, 1, 89.99),
(16, 1011, 1, 1, 1299.99),
(17, 1011, 7, 1, 449.99),
(18, 1012, 3, 1, 49.99),
(19, 1013, 13, 1, 199.99),
(20, 1013, 12, 1, 69.99),
(21, 1014, 17, 1, 109.99),
(22, 1015, 5, 1, 399.99),
(23, 1015, 11, 1, 79.99),
(24, 1015, 3, 1, 49.99);

-- ========================
-- 3. Query Iceberg (MinIO)
-- ========================

-- All orders
SELECT * FROM iceberg.shop.orders ORDER BY order_date;

-- Order status summary
SELECT status, COUNT(*) AS cnt, SUM(total_amount) AS total
FROM iceberg.shop.orders
GROUP BY status;

-- ============================================
-- 4. FEDERATION — Cross-source JOINs
-- ============================================

-- Join: Customer names (Postgres) with their orders (Iceberg/MinIO)
SELECT
    c.name AS customer,
    c.country,
    o.order_id,
    o.order_date,
    o.status,
    o.total_amount
FROM iceberg.shop.orders o
JOIN postgres.public.customers c
    ON o.customer_id = c.customer_id
ORDER BY o.order_date;

-- Join: Full order details across all three sources
-- Customer (Postgres) + Order (Iceberg) + Product (Postgres)
SELECT
    c.name AS customer,
    c.country,
    o.order_date,
    p.name AS product,
    p.category,
    oi.quantity,
    oi.unit_price
FROM iceberg.shop.order_items oi
JOIN iceberg.shop.orders o ON oi.order_id = o.order_id
JOIN postgres.public.customers c ON o.customer_id = c.customer_id
JOIN postgres.public.products p ON oi.product_id = p.product_id
ORDER BY o.order_date, c.name;

-- Top customers by total spend (federation: Postgres + Iceberg)
SELECT
    c.name AS customer,
    c.country,
    COUNT(DISTINCT o.order_id) AS num_orders,
    SUM(o.total_amount) AS total_spent
FROM iceberg.shop.orders o
JOIN postgres.public.customers c ON o.customer_id = c.customer_id
GROUP BY c.name, c.country
ORDER BY total_spent DESC;

-- Best-selling products (federation: Postgres + Iceberg)
SELECT
    p.name AS product,
    p.category,
    SUM(oi.quantity) AS total_qty_sold,
    SUM(oi.quantity * oi.unit_price) AS total_revenue
FROM iceberg.shop.order_items oi
JOIN postgres.public.products p ON oi.product_id = p.product_id
GROUP BY p.name, p.category
ORDER BY total_revenue DESC;

-- ============================================
-- 5. BONUS: Mix in TPC-H generated data
-- ============================================

-- Compare our shop's country distribution with TPC-H nations
SELECT 'Our Customers' AS source, country, COUNT(*) AS cnt
FROM postgres.public.customers
GROUP BY country
UNION ALL
SELECT 'TPC-H Nations', name, 1
FROM tpch.tiny.nation
ORDER BY source, cnt DESC;
