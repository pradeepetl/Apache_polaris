-- ============================================================
-- Global Sales Dataset (second Polaris catalog: global_sales)
-- 4 regions → 8 nested country namespaces → 16 tables (products + sales each)
--
-- Namespaces match exercises/global-sales-setup.sh:
--   middle_east.uae,         middle_east.saudi_arabia
--   africa.south_africa,     africa.nigeria
--   latin_america.brazil,    latin_america.mexico
--   oceania.australia,       oceania.new_zealand
--
-- Trino catalog: global_sales (etc/catalog/global_sales.properties → Polaris warehouse global_sales)
-- Nested namespaces are quoted as one schema:  global_sales."middle_east.uae".sales
--
-- Load everything:  bash exercises/global-sales-load.sh --setup
-- Or run statements one at a time in the SQL Query tab at http://localhost:3000
-- ============================================================

-- ─── 1. CREATE NAMESPACES (no-op if setup script already ran) ──

CREATE SCHEMA IF NOT EXISTS global_sales.middle_east;
CREATE SCHEMA IF NOT EXISTS global_sales.africa;
CREATE SCHEMA IF NOT EXISTS global_sales.latin_america;
CREATE SCHEMA IF NOT EXISTS global_sales.oceania;

CREATE SCHEMA IF NOT EXISTS global_sales."middle_east.uae";
CREATE SCHEMA IF NOT EXISTS global_sales."middle_east.saudi_arabia";
CREATE SCHEMA IF NOT EXISTS global_sales."africa.south_africa";
CREATE SCHEMA IF NOT EXISTS global_sales."africa.nigeria";
CREATE SCHEMA IF NOT EXISTS global_sales."latin_america.brazil";
CREATE SCHEMA IF NOT EXISTS global_sales."latin_america.mexico";
CREATE SCHEMA IF NOT EXISTS global_sales."oceania.australia";
CREATE SCHEMA IF NOT EXISTS global_sales."oceania.new_zealand";

-- Verify: should list the regions and the nested countries
-- SHOW SCHEMAS FROM global_sales;

-- ─── 2. UAE (middle_east.uae) ───────────────────────────────────

CREATE TABLE global_sales."middle_east.uae".products AS
SELECT * FROM (VALUES
  (1, 'iPhone 17 Pro',            'Electronics', 4699.00, 'AED'),
  (2, 'Kandura Premium',          'Apparel',      450.00, 'AED'),
  (3, 'Medjool Dates 1kg',        'Grocery',       85.00, 'AED'),
  (4, 'Oud Perfume 100ml',        'Beauty',      1200.00, 'AED'),
  (5, 'Dyson Airwrap',            'Electronics', 2399.00, 'AED'),
  (6, 'Arabic Coffee Dallah Set', 'Home',         320.00, 'AED')
) AS t(product_id, name, category, price, currency);

CREATE TABLE global_sales."middle_east.uae".sales AS
SELECT * FROM (VALUES
  (7001, 1, 1, 4699.00, DATE '2026-01-09', 'Dubai'),
  (7002, 3, 4,  340.00, DATE '2026-01-21', 'Abu Dhabi'),
  (7003, 4, 2, 2400.00, DATE '2026-02-06', 'Sharjah'),
  (7004, 2, 3, 1350.00, DATE '2026-02-19', 'Dubai'),
  (7005, 5, 1, 2399.00, DATE '2026-03-04', 'Ajman'),
  (7006, 6, 2,  640.00, DATE '2026-03-17', 'Al Ain'),
  (7007, 1, 2, 9398.00, DATE '2026-04-02', 'Dubai')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 3. SAUDI ARABIA (middle_east.saudi_arabia) ─────────────────

CREATE TABLE global_sales."middle_east.saudi_arabia".products AS
SELECT * FROM (VALUES
  (1, 'Samsung Galaxy S26 Ultra', 'Electronics', 5299.00, 'SAR'),
  (2, 'Thobe Classic',            'Apparel',      380.00, 'SAR'),
  (3, 'Saudi Coffee 500g',        'Grocery',       65.00, 'SAR'),
  (4, 'Bukhoor Incense Set',      'Home',         210.00, 'SAR'),
  (5, 'PlayStation 5 Pro',        'Electronics', 2999.00, 'SAR'),
  (6, 'Ajwa Dates 1kg',           'Grocery',      120.00, 'SAR')
) AS t(product_id, name, category, price, currency);

CREATE TABLE global_sales."middle_east.saudi_arabia".sales AS
SELECT * FROM (VALUES
  (8001, 1, 1, 5299.00, DATE '2026-01-11', 'Riyadh'),
  (8002, 2, 2,  760.00, DATE '2026-01-24', 'Jeddah'),
  (8003, 3, 6,  390.00, DATE '2026-02-07', 'Dammam'),
  (8004, 5, 1, 2999.00, DATE '2026-02-22', 'Riyadh'),
  (8005, 6, 5,  600.00, DATE '2026-03-09', 'Medina'),
  (8006, 4, 3,  630.00, DATE '2026-03-21', 'Mecca'),
  (8007, 1, 1, 5299.00, DATE '2026-04-06', 'Khobar')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 4. SOUTH AFRICA (africa.south_africa) ──────────────────────

CREATE TABLE global_sales."africa.south_africa".products AS
SELECT * FROM (VALUES
  (1, 'Hisense 65" TV',         'Electronics', 12999.00, 'ZAR'),
  (2, 'Rooibos Tea 80 bags',    'Grocery',        59.99, 'ZAR'),
  (3, 'Biltong 500g',           'Grocery',       189.00, 'ZAR'),
  (4, 'Veldskoen Boots',        'Footwear',     1295.00, 'ZAR'),
  (5, 'Springbok Rugby Jersey', 'Sports',       1499.00, 'ZAR'),
  (6, 'Weber Braai Kettle',     'Home',         3499.00, 'ZAR')
) AS t(product_id, name, category, price, currency);

CREATE TABLE global_sales."africa.south_africa".sales AS
SELECT * FROM (VALUES
  (9001, 1, 1, 12999.00, DATE '2026-01-13', 'Johannesburg'),
  (9002, 3, 4,   756.00, DATE '2026-01-26', 'Cape Town'),
  (9003, 5, 2,  2998.00, DATE '2026-02-09', 'Durban'),
  (9004, 2, 10,  599.90, DATE '2026-02-23', 'Pretoria'),
  (9005, 6, 1,  3499.00, DATE '2026-03-07', 'Gqeberha'),
  (9006, 4, 2,  2590.00, DATE '2026-03-19', 'Bloemfontein'),
  (9007, 3, 3,   567.00, DATE '2026-04-04', 'Cape Town')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 5. NIGERIA (africa.nigeria) ────────────────────────────────

CREATE TABLE global_sales."africa.nigeria".products AS
SELECT * FROM (VALUES
  (1, 'Tecno Phantom X3',      'Electronics', 650000.00, 'NGN'),
  (2, 'Ankara Fabric 6yd',     'Apparel',      25000.00, 'NGN'),
  (3, 'Jollof Spice Kit',      'Grocery',       4500.00, 'NGN'),
  (4, 'Indomie Carton 40pk',   'Grocery',      12000.00, 'NGN'),
  (5, 'Solar Power Bank',      'Electronics',  45000.00, 'NGN'),
  (6, 'Agbada Set',            'Apparel',      85000.00, 'NGN')
) AS t(product_id, name, category, price, currency);

CREATE TABLE global_sales."africa.nigeria".sales AS
SELECT * FROM (VALUES
  (10001, 1, 1,  650000.00, DATE '2026-01-16', 'Lagos'),
  (10002, 2, 4,  100000.00, DATE '2026-01-29', 'Abuja'),
  (10003, 4, 5,   60000.00, DATE '2026-02-12', 'Kano'),
  (10004, 5, 2,   90000.00, DATE '2026-02-26', 'Ibadan'),
  (10005, 6, 1,   85000.00, DATE '2026-03-10', 'Port Harcourt'),
  (10006, 3, 8,   36000.00, DATE '2026-03-24', 'Lagos'),
  (10007, 1, 2, 1300000.00, DATE '2026-04-09', 'Benin City'),
  (10008, 2, 2,   50000.00, DATE '2026-04-18', 'Enugu')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 6. BRAZIL (latin_america.brazil) ───────────────────────────

CREATE TABLE global_sales."latin_america.brazil".products AS
SELECT * FROM (VALUES
  (1, 'Havaianas Slim',       'Footwear',      59.90, 'BRL'),
  (2, 'Natura Ekos Perfume',  'Beauty',       189.90, 'BRL'),
  (3, 'Cafe Pilao 500g',      'Grocery',       24.90, 'BRL'),
  (4, 'Samsung Galaxy A57',   'Electronics', 2499.00, 'BRL'),
  (5, 'Brazil Home Jersey',   'Sports',       349.90, 'BRL'),
  (6, 'Tramontina Knife Set', 'Home',         299.90, 'BRL')
) AS t(product_id, name, category, price, currency);

CREATE TABLE global_sales."latin_america.brazil".sales AS
SELECT * FROM (VALUES
  (11001, 4, 1, 2499.00, DATE '2026-01-07', 'Sao Paulo'),
  (11002, 1, 5,  299.50, DATE '2026-01-20', 'Rio de Janeiro'),
  (11003, 5, 2,  699.80, DATE '2026-02-04', 'Belo Horizonte'),
  (11004, 2, 1,  189.90, DATE '2026-02-17', 'Brasilia'),
  (11005, 3, 10, 249.00, DATE '2026-03-03', 'Salvador'),
  (11006, 6, 1,  299.90, DATE '2026-03-16', 'Curitiba'),
  (11007, 4, 2, 4998.00, DATE '2026-04-01', 'Sao Paulo')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 7. MEXICO (latin_america.mexico) ───────────────────────────

CREATE TABLE global_sales."latin_america.mexico".products AS
SELECT * FROM (VALUES
  (1, 'Tequila Reposado 750ml', 'Grocery',       899.00, 'MXN'),
  (2, 'Talavera Pottery Plate', 'Home',          450.00, 'MXN'),
  (3, 'Huarache Sandals',       'Footwear',      780.00, 'MXN'),
  (4, 'Xbox Series X',          'Electronics', 13999.00, 'MXN'),
  (5, 'Mexico Away Jersey',     'Sports',       1899.00, 'MXN'),
  (6, 'Mole Poblano Paste 1kg', 'Grocery',       210.00, 'MXN')
) AS t(product_id, name, category, price, currency);

CREATE TABLE global_sales."latin_america.mexico".sales AS
SELECT * FROM (VALUES
  (12001, 4, 1, 13999.00, DATE '2026-01-12', 'Mexico City'),
  (12002, 1, 3,  2697.00, DATE '2026-01-27', 'Guadalajara'),
  (12003, 3, 2,  1560.00, DATE '2026-02-10', 'Monterrey'),
  (12004, 5, 1,  1899.00, DATE '2026-02-24', 'Puebla'),
  (12005, 2, 4,  1800.00, DATE '2026-03-11', 'Oaxaca'),
  (12006, 6, 6,  1260.00, DATE '2026-03-26', 'Puebla'),
  (12007, 1, 2,  1798.00, DATE '2026-04-07', 'Cancun')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 8. AUSTRALIA (oceania.australia) ───────────────────────────

CREATE TABLE global_sales."oceania.australia".products AS
SELECT * FROM (VALUES
  (1, 'Breville Barista Express', 'Home',         899.00, 'AUD'),
  (2, 'UGG Classic Boots',        'Footwear',     289.00, 'AUD'),
  (3, 'Tim Tam Family Pack',      'Grocery',        6.50, 'AUD'),
  (4, 'RM Williams Belt',         'Apparel',      179.00, 'AUD'),
  (5, 'Google Pixel 10',          'Electronics', 1349.00, 'AUD'),
  (6, 'Vegemite 380g',            'Grocery',        8.20, 'AUD')
) AS t(product_id, name, category, price, currency);

CREATE TABLE global_sales."oceania.australia".sales AS
SELECT * FROM (VALUES
  (13001, 1, 1,  899.00, DATE '2026-01-06', 'Sydney'),
  (13002, 2, 2,  578.00, DATE '2026-01-18', 'Melbourne'),
  (13003, 3, 12,  78.00, DATE '2026-02-01', 'Brisbane'),
  (13004, 5, 1, 1349.00, DATE '2026-02-16', 'Perth'),
  (13005, 4, 3,  537.00, DATE '2026-03-02', 'Adelaide'),
  (13006, 6, 10,  82.00, DATE '2026-03-18', 'Canberra'),
  (13007, 1, 1,  899.00, DATE '2026-04-03', 'Hobart')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);

-- ─── 9. NEW ZEALAND (oceania.new_zealand) ───────────────────────

CREATE TABLE global_sales."oceania.new_zealand".products AS
SELECT * FROM (VALUES
  (1, 'Manuka Honey UMF 10+',       'Grocery',   59.99, 'NZD'),
  (2, 'Icebreaker Merino Top',      'Apparel',  189.99, 'NZD'),
  (3, 'Allbirds Wool Runners',      'Footwear', 210.00, 'NZD'),
  (4, 'Whittaker''s Chocolate 250g','Grocery',    6.49, 'NZD'),
  (5, 'All Blacks Jersey',          'Sports',   249.99, 'NZD'),
  (6, 'Fisher & Paykel Kettle',     'Home',     129.00, 'NZD')
) AS t(product_id, name, category, price, currency);

CREATE TABLE global_sales."oceania.new_zealand".sales AS
SELECT * FROM (VALUES
  (14001, 1, 3, 179.97, DATE '2026-01-14', 'Auckland'),
  (14002, 2, 1, 189.99, DATE '2026-01-30', 'Wellington'),
  (14003, 3, 2, 420.00, DATE '2026-02-13', 'Christchurch'),
  (14004, 5, 1, 249.99, DATE '2026-02-27', 'Auckland'),
  (14005, 4, 8,  51.92, DATE '2026-03-13', 'Hamilton'),
  (14006, 6, 1, 129.00, DATE '2026-03-28', 'Dunedin'),
  (14007, 1, 2, 119.98, DATE '2026-04-10', 'Queenstown')
) AS t(sale_id, product_id, quantity, amount, sale_date, city);


-- ============================================================
-- SAMPLE QUERIES
-- ============================================================

-- Total sales by country (local currency)
-- SELECT 'UAE' AS country, 'AED' AS currency, SUM(amount) AS total FROM global_sales."middle_east.uae".sales
-- UNION ALL SELECT 'Saudi Arabia', 'SAR', SUM(amount) FROM global_sales."middle_east.saudi_arabia".sales
-- UNION ALL SELECT 'South Africa', 'ZAR', SUM(amount) FROM global_sales."africa.south_africa".sales
-- UNION ALL SELECT 'Nigeria',      'NGN', SUM(amount) FROM global_sales."africa.nigeria".sales
-- UNION ALL SELECT 'Brazil',       'BRL', SUM(amount) FROM global_sales."latin_america.brazil".sales
-- UNION ALL SELECT 'Mexico',       'MXN', SUM(amount) FROM global_sales."latin_america.mexico".sales
-- UNION ALL SELECT 'Australia',    'AUD', SUM(amount) FROM global_sales."oceania.australia".sales
-- UNION ALL SELECT 'New Zealand',  'NZD', SUM(amount) FROM global_sales."oceania.new_zealand".sales
-- ORDER BY country;

-- Cross-region electronics comparison
-- SELECT 'UAE' AS country, name, price, currency FROM global_sales."middle_east.uae".products WHERE category = 'Electronics'
-- UNION ALL SELECT 'Nigeria', name, price, currency FROM global_sales."africa.nigeria".products WHERE category = 'Electronics'
-- UNION ALL SELECT 'Mexico',  name, price, currency FROM global_sales."latin_america.mexico".products WHERE category = 'Electronics';

-- Join products and sales for a country
-- SELECT p.name, p.category, s.quantity, s.amount, s.city, s.sale_date
-- FROM global_sales."latin_america.brazil".sales s JOIN global_sales."latin_america.brazil".products p ON s.product_id = p.product_id
-- ORDER BY s.amount DESC;

-- Cross-CATALOG query: this catalog (global_sales) + regional sales in polaris_warehouse (Trino catalog: iceberg)
-- SELECT 'iceberg' AS trino_catalog, 'USA' AS country, count(*) AS orders FROM iceberg."north_america.usa".sales
-- UNION ALL SELECT 'iceberg',      'Germany', count(*) FROM iceberg."europe.germany".sales
-- UNION ALL SELECT 'global_sales', 'UAE',     count(*) FROM global_sales."middle_east.uae".sales
-- UNION ALL SELECT 'global_sales', 'Brazil',  count(*) FROM global_sales."latin_america.brazil".sales;


-- ============================================================
-- CLEANUP (uncomment to drop everything)
-- ============================================================

-- DROP TABLE IF EXISTS global_sales."oceania.new_zealand".sales;
-- DROP TABLE IF EXISTS global_sales."oceania.new_zealand".products;
-- DROP TABLE IF EXISTS global_sales."oceania.australia".sales;
-- DROP TABLE IF EXISTS global_sales."oceania.australia".products;
-- DROP TABLE IF EXISTS global_sales."latin_america.mexico".sales;
-- DROP TABLE IF EXISTS global_sales."latin_america.mexico".products;
-- DROP TABLE IF EXISTS global_sales."latin_america.brazil".sales;
-- DROP TABLE IF EXISTS global_sales."latin_america.brazil".products;
-- DROP TABLE IF EXISTS global_sales."africa.nigeria".sales;
-- DROP TABLE IF EXISTS global_sales."africa.nigeria".products;
-- DROP TABLE IF EXISTS global_sales."africa.south_africa".sales;
-- DROP TABLE IF EXISTS global_sales."africa.south_africa".products;
-- DROP TABLE IF EXISTS global_sales."middle_east.saudi_arabia".sales;
-- DROP TABLE IF EXISTS global_sales."middle_east.saudi_arabia".products;
-- DROP TABLE IF EXISTS global_sales."middle_east.uae".sales;
-- DROP TABLE IF EXISTS global_sales."middle_east.uae".products;
-- DROP SCHEMA IF EXISTS global_sales."oceania.new_zealand";
-- DROP SCHEMA IF EXISTS global_sales."oceania.australia";
-- DROP SCHEMA IF EXISTS global_sales."latin_america.mexico";
-- DROP SCHEMA IF EXISTS global_sales."latin_america.brazil";
-- DROP SCHEMA IF EXISTS global_sales."africa.nigeria";
-- DROP SCHEMA IF EXISTS global_sales."africa.south_africa";
-- DROP SCHEMA IF EXISTS global_sales."middle_east.saudi_arabia";
-- DROP SCHEMA IF EXISTS global_sales."middle_east.uae";
-- DROP SCHEMA IF EXISTS global_sales.oceania;
-- DROP SCHEMA IF EXISTS global_sales.latin_america;
-- DROP SCHEMA IF EXISTS global_sales.africa;
-- DROP SCHEMA IF EXISTS global_sales.middle_east;
