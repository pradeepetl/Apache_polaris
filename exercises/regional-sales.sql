-- ============================================================
-- Regional Sales Dataset
-- 3 regions → 6 nested country namespaces → 12 tables (products + sales each)
--
-- Namespaces match exercises/regional-sales-setup.sh:
--   north_america.usa, north_america.canada
--   europe.uk,         europe.germany
--   asia_pacific.japan, asia_pacific.india
--
-- Nested namespaces require iceberg.rest-catalog.nested-namespace-enabled=true
-- (etc/catalog/iceberg.properties). Trino has no 4-part names, so the nested
-- namespace must be quoted as one schema:  iceberg."north_america.usa".sales
--
-- Run directly in the SQL Query tab at http://localhost:3000
-- Execute each statement one at a time.
-- ============================================================

-- ─── 1. CREATE NAMESPACES (no-op if setup script already ran) ──

CREATE SCHEMA IF NOT EXISTS iceberg.north_america;
CREATE SCHEMA IF NOT EXISTS iceberg.europe;
CREATE SCHEMA IF NOT EXISTS iceberg.asia_pacific;

CREATE SCHEMA IF NOT EXISTS iceberg."north_america.usa";
CREATE SCHEMA IF NOT EXISTS iceberg."north_america.canada";
CREATE SCHEMA IF NOT EXISTS iceberg."europe.uk";
CREATE SCHEMA IF NOT EXISTS iceberg."europe.germany";
CREATE SCHEMA IF NOT EXISTS iceberg."asia_pacific.japan";
CREATE SCHEMA IF NOT EXISTS iceberg."asia_pacific.india";

-- Verify: should list the regions and the nested countries
-- SHOW SCHEMAS FROM iceberg;

-- ─── 2. USA (north_america.usa) ─────────────────────────────────

CREATE TABLE iceberg."north_america.usa".products AS
SELECT * FROM (VALUES
  (1, 'MacBook Pro 16"',    'Electronics', 2499.00, 'USD'),
  (2, 'Levi''s 501 Jeans',  'Apparel',       59.99, 'USD'),
  (3, 'Instant Pot Duo',    'Home',           89.95, 'USD'),
  (4, 'Nike Air Max 90',    'Footwear',      129.99, 'USD'),
  (5, 'Organic Almonds 1lb','Grocery',        12.49, 'USD'),
  (6, 'Yeti Tumbler 30oz',  'Home',           35.00, 'USD')
) AS t(product_id, name, category, price, currency);

CREATE TABLE iceberg."north_america.usa".sales AS
SELECT * FROM (VALUES
  (1001, 1, 1, 2499.00, DATE '2026-01-15', 'New York'),
  (1002, 2, 3,  179.97, DATE '2026-01-18', 'Los Angeles'),
  (1003, 3, 2,  179.90, DATE '2026-02-03', 'Chicago'),
  (1004, 4, 1,  129.99, DATE '2026-02-14', 'Houston'),
  (1005, 5, 5,   62.45, DATE '2026-03-01', 'Phoenix'),
  (1006, 1, 2, 4998.00, DATE '2026-03-10', 'San Francisco'),
  (1007, 6, 4,  140.00, DATE '2026-03-22', 'Seattle'),
  (1008, 2, 1,   59.99, DATE '2026-04-05', 'Miami')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 3. CANADA (north_america.canada) ───────────────────────────

CREATE TABLE iceberg."north_america.canada".products AS
SELECT * FROM (VALUES
  (1, 'Canada Goose Parka',  'Apparel',    1295.00, 'CAD'),
  (2, 'Maple Syrup 500ml',   'Grocery',      14.99, 'CAD'),
  (3, 'Samsung Galaxy S26',  'Electronics', 1399.00, 'CAD'),
  (4, 'Roots Sweatpants',    'Apparel',       88.00, 'CAD'),
  (5, 'Tim Hortons K-Cups',  'Grocery',       29.99, 'CAD'),
  (6, 'Bauer Hockey Stick',  'Sports',       249.99, 'CAD')
) AS t(product_id, name, category, price, currency);

CREATE TABLE iceberg."north_america.canada".sales AS
SELECT * FROM (VALUES
  (2001, 1, 1, 1295.00, DATE '2026-01-10', 'Toronto'),
  (2002, 2, 6,   89.94, DATE '2026-01-25', 'Vancouver'),
  (2003, 3, 1, 1399.00, DATE '2026-02-08', 'Montreal'),
  (2004, 4, 2,  176.00, DATE '2026-02-20', 'Calgary'),
  (2005, 6, 3,  749.97, DATE '2026-03-05', 'Ottawa'),
  (2006, 5, 4,  119.96, DATE '2026-03-18', 'Edmonton'),
  (2007, 1, 1, 1295.00, DATE '2026-04-02', 'Winnipeg')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 4. UK (europe.uk) ──────────────────────────────────

CREATE TABLE iceberg."europe.uk".products AS
SELECT * FROM (VALUES
  (1, 'Dyson V15 Detect',     'Electronics', 599.99, 'GBP'),
  (2, 'Burberry Scarf',       'Apparel',     370.00, 'GBP'),
  (3, 'PG Tips 240 bags',     'Grocery',       4.99, 'GBP'),
  (4, 'Dr. Martens 1460',     'Footwear',    149.00, 'GBP'),
  (5, 'Cadbury Roses Tin',    'Grocery',       8.50, 'GBP'),
  (6, 'Le Creuset Dutch Oven','Home',        260.00, 'GBP')
) AS t(product_id, name, category, price, currency);

CREATE TABLE iceberg."europe.uk".sales AS
SELECT * FROM (VALUES
  (3001, 1, 1,  599.99, DATE '2026-01-12', 'London'),
  (3002, 3, 10,  49.90, DATE '2026-01-20', 'Manchester'),
  (3003, 2, 1,  370.00, DATE '2026-02-05', 'Edinburgh'),
  (3004, 4, 2,  298.00, DATE '2026-02-18', 'Birmingham'),
  (3005, 5, 5,   42.50, DATE '2026-03-01', 'Liverpool'),
  (3006, 6, 1,  260.00, DATE '2026-03-15', 'Bristol'),
  (3007, 1, 1,  599.99, DATE '2026-04-01', 'Leeds')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 5. GERMANY (europe.germany) ─────────────────────────

CREATE TABLE iceberg."europe.germany".products AS
SELECT * FROM (VALUES
  (1, 'Braun Series 9 Pro',  'Electronics', 329.99, 'EUR'),
  (2, 'Adidas Ultraboost',   'Footwear',    179.95, 'EUR'),
  (3, 'Ritter Sport 250g',   'Grocery',       2.49, 'EUR'),
  (4, 'WMF Pressure Cooker', 'Home',         189.00, 'EUR'),
  (5, 'Hugo Boss Polo',      'Apparel',       89.95, 'EUR'),
  (6, 'Steiff Teddy Bear',   'Toys',         149.00, 'EUR')
) AS t(product_id, name, category, price, currency);

CREATE TABLE iceberg."europe.germany".sales AS
SELECT * FROM (VALUES
  (4001, 2, 2,  359.90, DATE '2026-01-08', 'Berlin'),
  (4002, 1, 1,  329.99, DATE '2026-01-22', 'Munich'),
  (4003, 3, 20,  49.80, DATE '2026-02-10', 'Hamburg'),
  (4004, 4, 1,  189.00, DATE '2026-02-28', 'Frankfurt'),
  (4005, 5, 3,  269.85, DATE '2026-03-12', 'Cologne'),
  (4006, 6, 2,  298.00, DATE '2026-03-25', 'Stuttgart'),
  (4007, 2, 1,  179.95, DATE '2026-04-08', 'Dusseldorf')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 6. JAPAN (asia_pacific.japan) ──────────────────────────────

CREATE TABLE iceberg."asia_pacific.japan".products AS
SELECT * FROM (VALUES
  (1, 'Sony WH-1000XM6',      'Electronics', 49800.00, 'JPY'),
  (2, 'Uniqlo Heattech Top',  'Apparel',      1990.00, 'JPY'),
  (3, 'Matcha Powder 100g',   'Grocery',      1280.00, 'JPY'),
  (4, 'Asics Gel-Kayano 31',  'Footwear',    18700.00, 'JPY'),
  (5, 'Zojirushi Rice Cooker','Home',        32800.00, 'JPY'),
  (6, 'Pocky Mega Pack',      'Grocery',       498.00, 'JPY')
) AS t(product_id, name, category, price, currency);

CREATE TABLE iceberg."asia_pacific.japan".sales AS
SELECT * FROM (VALUES
  (5001, 1, 1, 49800.00, DATE '2026-01-05', 'Tokyo'),
  (5002, 2, 5,  9950.00, DATE '2026-01-19', 'Osaka'),
  (5003, 5, 1, 32800.00, DATE '2026-02-02', 'Yokohama'),
  (5004, 3, 3,  3840.00, DATE '2026-02-15', 'Nagoya'),
  (5005, 4, 1, 18700.00, DATE '2026-03-01', 'Sapporo'),
  (5006, 6, 10, 4980.00, DATE '2026-03-20', 'Fukuoka'),
  (5007, 1, 2, 99600.00, DATE '2026-04-03', 'Kyoto')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 7. INDIA (asia_pacific.india) ──────────────────────────────

CREATE TABLE iceberg."asia_pacific.india".products AS
SELECT * FROM (VALUES
  (1, 'OnePlus 14 Pro',      'Electronics', 64999.00, 'INR'),
  (2, 'Fabindia Kurta',      'Apparel',      2499.00, 'INR'),
  (3, 'Tata Gold Tea 500g',  'Grocery',       285.00, 'INR'),
  (4, 'Prestige Cooker 5L',  'Home',         2150.00, 'INR'),
  (5, 'Woodland Boots',      'Footwear',     4995.00, 'INR'),
  (6, 'Amul Butter 500g',    'Grocery',       280.00, 'INR')
) AS t(product_id, name, category, price, currency);

CREATE TABLE iceberg."asia_pacific.india".sales AS
SELECT * FROM (VALUES
  (6001, 1, 1, 64999.00, DATE '2026-01-14', 'Mumbai'),
  (6002, 3, 10, 2850.00, DATE '2026-01-28', 'Delhi'),
  (6003, 2, 2,  4998.00, DATE '2026-02-11', 'Bangalore'),
  (6004, 4, 3,  6450.00, DATE '2026-02-25', 'Chennai'),
  (6005, 5, 1,  4995.00, DATE '2026-03-08', 'Hyderabad'),
  (6006, 6, 8,  2240.00, DATE '2026-03-22', 'Kolkata'),
  (6007, 1, 1, 64999.00, DATE '2026-04-05', 'Pune'),
  (6008, 2, 4,  9996.00, DATE '2026-04-15', 'Ahmedabad')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);


-- ============================================================
-- SAMPLE QUERIES
-- ============================================================

-- Total sales by country
-- SELECT 'USA' AS country, SUM(amount) AS total FROM iceberg."north_america.usa".sales
-- UNION ALL SELECT 'Canada', SUM(amount) FROM iceberg."north_america.canada".sales
-- UNION ALL SELECT 'UK', SUM(amount) FROM iceberg."europe.uk".sales
-- UNION ALL SELECT 'Germany', SUM(amount) FROM iceberg."europe.germany".sales
-- UNION ALL SELECT 'Japan', SUM(amount) FROM iceberg."asia_pacific.japan".sales
-- UNION ALL SELECT 'India', SUM(amount) FROM iceberg."asia_pacific.india".sales
-- ORDER BY total DESC;

-- Cross-region electronics comparison
-- SELECT 'USA' AS country, name, price, currency FROM iceberg."north_america.usa".products WHERE category = 'Electronics'
-- UNION ALL SELECT 'Japan', name, price, currency FROM iceberg."asia_pacific.japan".products WHERE category = 'Electronics'
-- UNION ALL SELECT 'India', name, price, currency FROM iceberg."asia_pacific.india".products WHERE category = 'Electronics';

-- Join products and sales for a country
-- SELECT p.name, p.category, s.quantity, s.amount, s.city, s.sale_date
-- FROM iceberg."north_america.usa".sales s JOIN iceberg."north_america.usa".products p ON s.product_id = p.product_id
-- ORDER BY s.amount DESC;


-- ============================================================
-- CLEANUP (uncomment to drop everything)
-- ============================================================

-- DROP TABLE IF EXISTS iceberg."asia_pacific.india".sales;
-- DROP TABLE IF EXISTS iceberg."asia_pacific.india".products;
-- DROP TABLE IF EXISTS iceberg."asia_pacific.japan".sales;
-- DROP TABLE IF EXISTS iceberg."asia_pacific.japan".products;
-- DROP TABLE IF EXISTS iceberg."europe.germany".sales;
-- DROP TABLE IF EXISTS iceberg."europe.germany".products;
-- DROP TABLE IF EXISTS iceberg."europe.uk".sales;
-- DROP TABLE IF EXISTS iceberg."europe.uk".products;
-- DROP TABLE IF EXISTS iceberg."north_america.canada".sales;
-- DROP TABLE IF EXISTS iceberg."north_america.canada".products;
-- DROP TABLE IF EXISTS iceberg."north_america.usa".sales;
-- DROP TABLE IF EXISTS iceberg."north_america.usa".products;
-- DROP SCHEMA IF EXISTS iceberg."asia_pacific.india";
-- DROP SCHEMA IF EXISTS iceberg."asia_pacific.japan";
-- DROP SCHEMA IF EXISTS iceberg."europe.germany";
-- DROP SCHEMA IF EXISTS iceberg."europe.uk";
-- DROP SCHEMA IF EXISTS iceberg."north_america.canada";
-- DROP SCHEMA IF EXISTS iceberg."north_america.usa";
-- DROP SCHEMA IF EXISTS iceberg.asia_pacific;
-- DROP SCHEMA IF EXISTS iceberg.europe;
-- DROP SCHEMA IF EXISTS iceberg.north_america;
