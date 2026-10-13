package com.shop.oms.item;

import java.math.BigDecimal;
import java.util.List;

import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface OrderItemMapper {

    @Select("SELECT id, order_id, product_id, qty, unit_price, status FROM order_items WHERE order_id = #{orderId} ORDER BY id")
    List<OrderItem> findByOrder(@Param("orderId") long orderId);

    @Delete("DELETE FROM order_items WHERE order_id = #{orderId}")
    int deleteByOrder(@Param("orderId") long orderId);

    @Insert("INSERT INTO order_items (order_id, product_id, qty, unit_price, status) "
            + "VALUES (#{orderId}, #{productId}, #{qty}, #{unitPrice}, 'PENDING')")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(OrderItem item);

    @Update("UPDATE order_items SET status = 'CONFIRMED' WHERE order_id = #{orderId} AND status = 'PENDING'")
    int confirmPending(@Param("orderId") long orderId);

    @Update("UPDATE order_items SET unit_price = unit_price + #{delta} "
            + "WHERE product_id BETWEEN #{fromId} AND #{toId}")
    int repriceProducts(@Param("fromId") long fromId, @Param("toId") long toId, @Param("delta") BigDecimal delta);

    @Select("SELECT DISTINCT order_id FROM order_items WHERE product_id BETWEEN #{fromId} AND #{toId} ORDER BY order_id")
    List<Long> ordersWithProducts(@Param("fromId") long fromId, @Param("toId") long toId);

    @Select("SELECT COALESCE(SUM(qty * unit_price), 0) FROM order_items WHERE order_id = #{orderId}")
    BigDecimal sumAmount(@Param("orderId") long orderId);

    @Select("SELECT COUNT(*) FROM order_items WHERE order_id = #{orderId}")
    int countItems(@Param("orderId") long orderId);

    @Select("SELECT COUNT(*) FROM order_items WHERE order_id = #{orderId} AND status = 'CONFIRMED'")
    int countConfirmed(@Param("orderId") long orderId);
}
