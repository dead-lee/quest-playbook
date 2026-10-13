-- Developer sandbox only (NOT used by the grader): creates the oms schema with a handful of
-- sample rows so the services can be started and poked locally.
-- mysql -uroot < /opt/oms/dev/dev_setup.sql
CREATE DATABASE IF NOT EXISTS oms DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE oms;
DROP TABLE IF EXISTS order_items, orders, inventory;
CREATE TABLE orders (
  id              BIGINT NOT NULL AUTO_INCREMENT,
  order_no        VARCHAR(32) NOT NULL,
  customer_id     BIGINT NOT NULL,
  status          VARCHAR(16) NOT NULL DEFAULT 'OPEN',
  total_amount    DECIMAL(14,2) NOT NULL DEFAULT 0,
  item_count      INT NOT NULL DEFAULT 0,
  confirmed_count INT NOT NULL DEFAULT 0,
  version         INT NOT NULL DEFAULT 0,
  updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_orders_customer (customer_id),
  KEY idx_orders_status (status)
) ENGINE=InnoDB;
CREATE TABLE order_items (
  id          BIGINT NOT NULL AUTO_INCREMENT,
  order_id    BIGINT NOT NULL,
  product_id  BIGINT NOT NULL,
  qty         INT NOT NULL,
  unit_price  DECIMAL(12,2) NOT NULL,
  status      VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  PRIMARY KEY (id),
  KEY idx_items_order_status (order_id, status),
  KEY idx_items_product (product_id)
) ENGINE=InnoDB;
CREATE TABLE inventory (
  product_id  BIGINT NOT NULL,
  sku         VARCHAR(32) NOT NULL,
  unit_price  DECIMAL(12,2) NOT NULL,
  stock       INT NOT NULL,
  reserved    INT NOT NULL DEFAULT 0,
  PRIMARY KEY (product_id)
) ENGINE=InnoDB;

INSERT INTO inventory (product_id, sku, unit_price, stock, reserved) VALUES
(1,'DEV-A',9.90,500,3),(2,'DEV-B',4.50,500,4),(3,'DEV-C',12.00,500,2),
(4,'DEV-D',7.25,500,1),(5,'DEV-E',3.80,500,2),(6,'DEV-F',15.60,500,0);
INSERT INTO orders (id, order_no, customer_id, status, total_amount, item_count, confirmed_count) VALUES
(1,'DEV-1',7,'OPEN',33.90,2,0),(2,'DEV-2',8,'OPEN',25.25,2,0),
(3,'DEV-3',9,'OPEN',17.50,2,0),(4,'DEV-4',7,'OPEN',9.90,1,0);
INSERT INTO order_items (order_id, product_id, qty, unit_price) VALUES
(1,1,1,9.90),(1,3,2,12.00),(2,2,4,4.50),(2,4,1,7.25),(3,5,2,3.80),(3,1,1,9.90),(4,1,1,9.90);
CREATE USER IF NOT EXISTS 'oms_app'@'%' IDENTIFIED BY 'oms_app';
CREATE USER IF NOT EXISTS 'oms_app'@'localhost' IDENTIFIED BY 'oms_app';
GRANT SELECT, INSERT, UPDATE, DELETE ON oms.* TO 'oms_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON oms.* TO 'oms_app'@'localhost';
GRANT PROCESS ON *.* TO 'oms_app'@'%';
GRANT PROCESS ON *.* TO 'oms_app'@'localhost';
FLUSH PRIVILEGES;
