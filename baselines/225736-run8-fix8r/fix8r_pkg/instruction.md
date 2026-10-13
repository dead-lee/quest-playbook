# 订单系统并发改单时偶发死锁，只能靠重试顶着

## 背景
`/app` 是我们订单管理系统的两个微服务（Maven 多模块工程，Java 17 + Spring Boot 3.2 + MyBatis，依赖已全部下载到本地仓库，可以 `mvn -o package` 离线构建）：

- `order-service`（端口 8081）：负责 `orders` 订单主表。
- `item-service`（端口 8082）：负责 `order_items` 订单明细表和 `inventory` 库存表。
- `oms-common`：公共代码。`TxRunner` 负责开启/提交/回滚本地事务；碰到 MySQL 1213（死锁）或 1205（锁等待超时）会把错误和 `SHOW ENGINE INNODB STATUS` 里的 LATEST DETECTED DEADLOCK 写进日志，然后重试，最多 3 次。

两个服务连同一个 MySQL 8.0（InnoDB，`transaction_isolation` 保持默认的 REPEATABLE-READ，`innodb_lock_wait_timeout = 5`），通过 HTTP 互相调用，跑在同一个容器里。`/opt/oms/dev/` 里有一份开发用的建库脚本 `dev_setup.sql`（表结构、`oms_app` 账号和几行示例数据）和 MySQL 配置 `dev.cnf`，只供本地调试；测试时用的是另一份独立的数据库配置和每次随机生成的测试数据，不会读取这里的文件。主键都是自增的 `BIGINT`，`order_items` 上有非唯一索引 `(order_id, status)` 和 `(product_id)`。

对外的业务接口：

| 接口 | 作用 |
|---|---|
| `POST :8081/orders/{id}/edit`，body `{"lines":[{"productId":p,"qty":q},...]}` | 客户改单：用新的明细整体替换订单原有明细，单价取 `inventory.unit_price`，按差额调整 `inventory.reserved`，更新订单的金额和数量 |
| `POST :8081/orders/{id}/cancel` | 取消订单：删掉全部明细、释放库存占用，订单置为 `CANCELLED`，金额和各项计数清零 |
| `POST :8082/items/{id}/confirm` | 仓库确认：把订单所有 `PENDING` 明细置为 `CONFIRMED`，更新订单的 `confirmed_count` |
| `POST :8082/items/reprice`，body `{"fromProductId":a,"toProductId":b,"delta":"0.25"}` | 调价活动：商品 a..b（含两端）的 `inventory.unit_price` 加上 delta，已经在订单上的这些商品的明细单价也加上 delta，并更新受影响订单的金额 |
| `GET :8081/orders/{id}` | 查询订单主表 |
| `GET :8082/items/{id}` | 查询订单 `{id}` 的全部明细 |

各接口成功时返回 HTTP 200，响应 JSON 字段如下（金额为数字，两位小数）：

- `edit`、`cancel`、`GET /orders/{id}`：订单对象 `{"id", "orderNo", "customerId", "status", "totalAmount", "itemCount", "confirmedCount", "version"}`，取值为本次请求自己的事务写入并提交的订单状态（在同一事务内读出，不受之后其他请求影响：改单返回 `OPEN`、`itemCount` 等于提交的明细行数、`confirmedCount` 为 0；取消返回 `CANCELLED` 和全 0）；`status` 为 `OPEN` 或 `CANCELLED`。
- `confirm`：`{"total", "itemCount", "confirmedCount"}`，即本次确认事务提交时该订单的明细金额合计、明细行数和已确认行数（未取消订单 `confirmedCount` 等于 `itemCount`）。
- `reprice`：`{"orders": n}`，`n` 为受影响的订单数（整数）。
- `GET /items/{id}`：明细数组，每项 `{"id", "orderId", "productId", "qty", "unitPrice", "status"}`，`status` 为 `PENDING` 或 `CONFIRMED`。

业务拒绝（目前只有“订单已取消”这一种）返回 HTTP 409，body `{"error": ..., "mysqlError": 0}`：对已取消的订单再改单或再取消返回 409。对已取消的订单调用 `confirm` 不是错误，返回 200 和 `{"total": 0, "itemCount": 0, "confirmedCount": 0}`，不做任何修改；`confirm` 和 `reprice` 永远不返回 409。`reprice` 返回的 `orders` 等于调价前含有区间内商品明细的未取消订单数。已取消的订单 `totalAmount`、`itemCount`、`confirmedCount` 均为 0，且没有明细。

## 现象
单个请求依次调用时，所有接口的结果都正确。上线后生产环境每天偶发两三次死锁，日志里能看到 1213 和 1205，大促时更多；重试有时也救不回来，接口返回 503，偶尔还会出现订单金额和明细对不上、库存占用和明细数量对不上的情况。目前只能靠 `TxRunner` 的重试先顶着。

## 要求
修改 `/app` 里的 Java 代码，让这些接口在高并发下（几十个客户端同时对同一批、相邻的订单和商品发起改单、取消、确认、调价）不再出现死锁和锁等待超时，并且结果正确。具体会验证：

1. 每个接口的业务结果和上表一致（单线程逐个调用时逐项核对订单金额、明细、确认数、库存占用、价格）。对已取消的订单再改单或取消，返回 HTTP 409；其他请求必须返回 200。并发运行时同样如此：合法的业务请求只接受 HTTP 2xx（本题即 200），任何 4xx/5xx（包括因并发冲突、版本号不一致而返回的 409，以及超时、503）都算失败；并发下 409 按请求时间线判定，而不是看压测结束时的订单状态：设订单 X 唯一一次成功（200）的取消请求为 C，
   - 在 C 的响应返回之后才发出的改单/取消请求，必须返回 409；
   - 一个返回 409 的改单/取消请求，只有在 C 已完成、或与它在时间上重叠时才算正确；X 没有成功取消过、或 C 在它返回之后才发出，409 即为失败；
   - 与 C 时间上重叠（既不完全在 C 之前，也不完全在 C 之后）的请求返回 200 或 409 都可以，但数据必须一致；
   - 每个最终为 `CANCELLED` 的订单恰好有一次取消返回 200，重复取消都返回 409。
2. 并发压测期间，MySQL 服务端 `information_schema.INNODB_METRICS` 里的 `lock_deadlocks` 和 `lock_timeouts` 计数都不能增加。计数取自数据库服务端，重试成功也算一次死锁，所以靠重试、加大重试次数或吞掉异常都没用。
3. 压测结束后数据一致（金额一律按分精确比较，不允许任何误差，任何一项对不上该轮即失败）：每个未取消订单的 `total_amount` 等于其明细 `qty × unit_price` 之和，`item_count`、`confirmed_count` 与明细一致；已取消订单没有明细、金额为 0；每个商品的 `reserved` 等于全部明细中该商品数量之和，`stock` 不变；每个商品的单价等于初始单价加上所有成功调价的 delta；每条明细的 `unit_price` 都等于该商品当前的 `inventory.unit_price`（改单按当时的最新单价写入明细，调价必须覆盖调价提交时所有含该商品的明细，包括并发改单刚写入的）；每个未取消订单的明细恰好是某一次成功改单提交的内容（没改过的保持初始明细）。并发压测中每个响应体也按上面的字段契约逐项校验（金额必须是精确到分的数字，409 的 body 必须是 `{"error": ..., "mysqlError": 0}`）。
4. 请求要真正并发处理：不能用全局锁、单连接池、`LOCK TABLES`、`GET_LOCK` 之类把所有请求串行化。压测期间会定时采样 `performance_schema.data_locks`，统计 `oms_app` 账号下同一时刻持有或等待 `orders`/`order_items`/`inventory` 行锁的不同事务数（只开着事务、不碰这些表的空闲事务不计），峰值低于 4 即判为“被串行化”，该轮不通过。
5. 压测的输入范围：商品 ID 为 1–20。初始数据每次测试随机生成：100–140 个未取消订单（ID 从 1 连续编号），每单 3 行不同商品的明细，数量 1–5；单价 5.00–40.00（步长 0.05），库存 50000–150000，`reserved` 等于初始明细数量之和，客户 ID 1000–9999，初始均为 `PENDING`、`confirmed_count = 0`。每轮约 400 个请求、50 个并发客户端，集中打在 10–30 个 ID 相邻的订单上。改单每次 2–4 个不同商品、每个数量 1–5；调价区间 `toProductId - fromProductId` 为 1–3，delta 为 0.01–0.50；同一订单可能被反复改单、确认，也会在被取消之后继续收到改单请求（应返回 409），而它相邻订单上的请求必须照常成功。
6. 不许改隔离级别（包括在连接串或会话里改），不许改表结构、主键和索引，测试时会用自己的配置和数据重新初始化数据库，服务只拿到 `oms_app` 账号的增删改查权限。保留两个服务的拆分、端口和上面的对外接口。

## 提示
- `TxRunner` 的日志（默认写到 `/var/log/oms/`，可用环境变量 `OMS_LOG_DIR` 改）里记录了每个事务的 BEGIN/COMMIT/ROLLBACK 和死锁现场。
- 可以按 `/opt/oms/dev/dev.cnf` 自己起一个 MySQL（`mysqld --initialize-insecure` 后执行 `dev_setup.sql`），示例数据很少，压测时可以自己多造一些订单，构建后用 `java -jar order-service/target/order-service.jar` 和 `java -jar item-service/target/item-service.jar` 启动两个服务（数据库地址等见各自的 `application.yml`），自己写并发脚本复现。
