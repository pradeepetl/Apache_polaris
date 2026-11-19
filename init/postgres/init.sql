CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    city VARCHAR(100),
    country VARCHAR(50),
    signup_date DATE
);

INSERT INTO customers (name, email, city, country, signup_date) VALUES
('Alice Johnson', 'alice@example.com', 'New York', 'USA', '2023-01-15'),
('Bob Smith', 'bob@example.com', 'London', 'UK', '2023-02-20'),
('Carlos Ruiz', 'carlos@example.com', 'Madrid', 'Spain', '2023-03-10'),
('Diana Chen', 'diana@example.com', 'Shanghai', 'China', '2023-03-22'),
('Eva Mueller', 'eva@example.com', 'Berlin', 'Germany', '2023-04-05'),
('Frank Tanaka', 'frank@example.com', 'Tokyo', 'Japan', '2023-04-18'),
('Grace Kim', 'grace@example.com', 'Seoul', 'South Korea', '2023-05-01'),
('Hassan Ali', 'hassan@example.com', 'Dubai', 'UAE', '2023-05-14'),
('Irene Costa', 'irene@example.com', 'Sao Paulo', 'Brazil', '2023-06-02'),
('James Brown', 'james@example.com', 'Sydney', 'Australia', '2023-06-20'),
('Katya Ivanova', 'katya@example.com', 'Moscow', 'Russia', '2023-07-08'),
('Liam O''Brien', 'liam@example.com', 'Dublin', 'Ireland', '2023-07-25'),
('Maria Silva', 'maria@example.com', 'Lisbon', 'Portugal', '2023-08-12'),
('Naveen Patel', 'naveen@example.com', 'Mumbai', 'India', '2023-08-30'),
('Olivia Martin', 'olivia@example.com', 'Paris', 'France', '2023-09-15'),
('Pierre Dupont', 'pierre@example.com', 'Lyon', 'France', '2023-09-28'),
('Quinn Taylor', 'quinn@example.com', 'Toronto', 'Canada', '2023-10-10'),
('Raj Sharma', 'raj@example.com', 'Delhi', 'India', '2023-10-22'),
('Sofia Romano', 'sofia@example.com', 'Rome', 'Italy', '2023-11-05'),
('Tom Wilson', 'tom@example.com', 'Chicago', 'USA', '2023-11-20');

CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(50),
    price DECIMAL(10, 2),
    stock_quantity INT
);

INSERT INTO products (name, category, price, stock_quantity) VALUES
('Laptop Pro 15', 'Electronics', 1299.99, 150),
('Wireless Mouse', 'Electronics', 29.99, 500),
('USB-C Hub', 'Electronics', 49.99, 300),
('Mechanical Keyboard', 'Electronics', 89.99, 250),
('Monitor 27"', 'Electronics', 399.99, 120),
('Standing Desk', 'Furniture', 599.99, 80),
('Ergonomic Chair', 'Furniture', 449.99, 100),
('Desk Lamp', 'Furniture', 39.99, 400),
('Notebook Pack (5)', 'Office', 12.99, 1000),
('Pen Set', 'Office', 8.99, 800),
('Backpack', 'Accessories', 79.99, 200),
('Webcam HD', 'Electronics', 69.99, 350),
('Headphones', 'Electronics', 199.99, 180),
('Phone Stand', 'Accessories', 19.99, 600),
('Cable Organizer', 'Accessories', 14.99, 700),
('Whiteboard', 'Office', 89.99, 90),
('Portable SSD 1TB', 'Electronics', 109.99, 220),
('Mouse Pad XL', 'Accessories', 24.99, 450),
('Blue Light Glasses', 'Accessories', 34.99, 350),
('Coffee Mug', 'Office', 9.99, 900);
