"""
Router de Comparación: Ejecuta consultas equivalentes en SQL Server y MongoDB
para verificar integridad de datos después de la migración.
"""

from fastapi import APIRouter, HTTPException
import pandas as pd
from app.database import get_sql_connection, get_mongo_db

router = APIRouter()


@router.get("/summary")
async def compare_summary():
    """
    Compara el resumen general: conteo de registros SQL vs documentos MongoDB.
    """
    try:
        conn = get_sql_connection()
        db = get_mongo_db()
        
        comparisons = []
        
        # 1. Productos
        sql_count = pd.read_sql(
            "SELECT COUNT(*) as cnt FROM SalesLT.Product", conn
        )['cnt'].iloc[0]
        mongo_count = db["products"].count_documents({})
        comparisons.append({
            "entity": "Productos",
            "sql_table": "SalesLT.Product",
            "mongo_collection": "products",
            "sql_count": int(sql_count),
            "mongo_count": mongo_count,
            "match": int(sql_count) == mongo_count
        })
        
        # 2. Clientes
        sql_count = pd.read_sql(
            "SELECT COUNT(*) as cnt FROM SalesLT.Customer", conn
        )['cnt'].iloc[0]
        mongo_count = db["customers"].count_documents({})
        comparisons.append({
            "entity": "Clientes",
            "sql_table": "SalesLT.Customer",
            "mongo_collection": "customers",
            "sql_count": int(sql_count),
            "mongo_count": mongo_count,
            "match": int(sql_count) == mongo_count
        })
        
        # 3. Categorías
        sql_count = pd.read_sql(
            "SELECT COUNT(*) as cnt FROM SalesLT.ProductCategory", conn
        )['cnt'].iloc[0]
        mongo_count = db["product_categories"].count_documents({})
        comparisons.append({
            "entity": "Categorías",
            "sql_table": "SalesLT.ProductCategory",
            "mongo_collection": "product_categories",
            "sql_count": int(sql_count),
            "mongo_count": mongo_count,
            "match": int(sql_count) == mongo_count
        })
        
        # 4. Direcciones
        sql_count = pd.read_sql(
            "SELECT COUNT(*) as cnt FROM SalesLT.Address", conn
        )['cnt'].iloc[0]
        mongo_count = db["addresses"].count_documents({})
        comparisons.append({
            "entity": "Direcciones",
            "sql_table": "SalesLT.Address",
            "mongo_collection": "addresses",
            "sql_count": int(sql_count),
            "mongo_count": mongo_count,
            "match": int(sql_count) == mongo_count
        })
        
        # 5. Órdenes de Venta
        sql_count = pd.read_sql(
            "SELECT COUNT(*) as cnt FROM SalesLT.SalesOrderHeader", conn
        )['cnt'].iloc[0]
        mongo_count = db["sales_orders"].count_documents({})
        comparisons.append({
            "entity": "Órdenes de Venta",
            "sql_table": "SalesLT.SalesOrderHeader",
            "mongo_collection": "sales_orders",
            "sql_count": int(sql_count),
            "mongo_count": mongo_count,
            "match": int(sql_count) == mongo_count
        })
        
        # 6. Detalles de Orden (embebidos)
        sql_count = pd.read_sql(
            "SELECT COUNT(*) as cnt FROM SalesLT.SalesOrderDetail", conn
        )['cnt'].iloc[0]
        
        # Contar detalles embebidos usando aggregation pipeline
        pipeline = [
            {"$project": {"details_count": {"$size": {"$ifNull": ["$order_details", []]}}}},
            {"$group": {"_id": None, "total": {"$sum": "$details_count"}}}
        ]
        result = list(db["sales_orders"].aggregate(pipeline))
        mongo_count = result[0]["total"] if result else 0
        
        comparisons.append({
            "entity": "Detalles de Orden (embebidos)",
            "sql_table": "SalesLT.SalesOrderDetail",
            "mongo_collection": "sales_orders.order_details[]",
            "sql_count": int(sql_count),
            "mongo_count": mongo_count,
            "match": int(sql_count) == mongo_count
        })
        
        conn.close()
        
        all_match = all(c["match"] for c in comparisons)
        
        return {
            "overall_match": all_match,
            "status": "✅ DATOS ÍNTEGROS" if all_match else "⚠️ DISCREPANCIA DETECTADA",
            "comparisons": comparisons
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en comparación: {str(e)}")


@router.get("/products")
async def compare_products():
    """
    Compara productos: misma consulta en SQL y MongoDB.
    Consulta: Top 10 productos más caros con su categoría.
    """
    try:
        conn = get_sql_connection()
        db = get_mongo_db()
        
        # SQL Query
        sql_query = """
            SELECT TOP 10
                p.ProductID,
                p.Name AS ProductName,
                p.ProductNumber,
                p.Color,
                p.ListPrice,
                pc.Name AS CategoryName
            FROM SalesLT.Product p
            LEFT JOIN SalesLT.ProductCategory pc ON p.ProductCategoryID = pc.ProductCategoryID
            ORDER BY p.ListPrice DESC
        """
        sql_df = pd.read_sql(sql_query, conn)
        conn.close()
        
        # MongoDB Query equivalente
        mongo_pipeline = [
            {"$project": {
                "_id": 0,
                "ProductID": 1,
                "ProductName": 1,
                "ProductNumber": 1,
                "Color": 1,
                "ListPrice": 1,
                "CategoryName": "$category.name"
            }},
            {"$sort": {"ListPrice": -1}},
            {"$limit": 10}
        ]
        mongo_results = list(db["products"].aggregate(mongo_pipeline))
        
        return {
            "query_description": "Top 10 productos más caros con su categoría",
            "sql_query": sql_query.strip(),
            "mongo_query": "db.products.aggregate([{$project: ...}, {$sort: {ListPrice: -1}}, {$limit: 10}])",
            "sql_results": sql_df.to_dict(orient='records'),
            "mongo_results": mongo_results,
            "sql_count": len(sql_df),
            "mongo_count": len(mongo_results),
            "match": len(sql_df) == len(mongo_results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en comparación: {str(e)}")


@router.get("/customers")
async def compare_customers():
    """
    Compara clientes: clientes con más direcciones.
    """
    try:
        conn = get_sql_connection()
        db = get_mongo_db()
        
        # SQL Query
        sql_query = """
            SELECT TOP 10
                c.CustomerID,
                c.FirstName + ' ' + c.LastName AS FullName,
                c.CompanyName,
                c.EmailAddress,
                COUNT(ca.AddressID) AS AddressCount
            FROM SalesLT.Customer c
            LEFT JOIN SalesLT.CustomerAddress ca ON c.CustomerID = ca.CustomerID
            GROUP BY c.CustomerID, c.FirstName, c.LastName, c.CompanyName, c.EmailAddress
            ORDER BY COUNT(ca.AddressID) DESC, c.CustomerID
        """
        sql_df = pd.read_sql(sql_query, conn)
        conn.close()
        
        # MongoDB Query equivalente
        mongo_pipeline = [
            {"$project": {
                "_id": 0,
                "CustomerID": 1,
                "FullName": 1,
                "CompanyName": 1,
                "EmailAddress": 1,
                "AddressCount": "$address_count"
            }},
            {"$sort": {"AddressCount": -1, "CustomerID": 1}},
            {"$limit": 10}
        ]
        mongo_results = list(db["customers"].aggregate(mongo_pipeline))
        
        return {
            "query_description": "Top 10 clientes con más direcciones",
            "sql_query": sql_query.strip(),
            "mongo_query": "db.customers.aggregate([{$project: ...}, {$sort: {AddressCount: -1}}, {$limit: 10}])",
            "sql_results": sql_df.to_dict(orient='records'),
            "mongo_results": mongo_results,
            "sql_count": len(sql_df),
            "mongo_count": len(mongo_results),
            "match": len(sql_df) == len(mongo_results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en comparación: {str(e)}")


@router.get("/sales")
async def compare_sales():
    """
    Compara ventas: total de ventas por cliente.
    """
    try:
        conn = get_sql_connection()
        db = get_mongo_db()
        
        # SQL Query
        sql_query = """
            SELECT 
                c.CustomerID,
                c.FirstName + ' ' + c.LastName AS CustomerName,
                COUNT(soh.SalesOrderID) AS TotalOrders,
                SUM(soh.TotalDue) AS TotalSpent
            FROM SalesLT.Customer c
            INNER JOIN SalesLT.SalesOrderHeader soh ON c.CustomerID = soh.CustomerID
            GROUP BY c.CustomerID, c.FirstName, c.LastName
            ORDER BY SUM(soh.TotalDue) DESC
        """
        sql_df = pd.read_sql(sql_query, conn)
        conn.close()
        
        # Convertir tipos para comparación
        for col in sql_df.select_dtypes(include=['float64']).columns:
            sql_df[col] = sql_df[col].round(4)
        
        # MongoDB Query equivalente
        mongo_pipeline = [
            {"$group": {
                "_id": "$customer.id",
                "CustomerName": {"$first": "$customer.name"},
                "TotalOrders": {"$sum": 1},
                "TotalSpent": {"$sum": "$TotalDue"}
            }},
            {"$project": {
                "_id": 0,
                "CustomerID": "$_id",
                "CustomerName": 1,
                "TotalOrders": 1,
                "TotalSpent": {"$round": ["$TotalSpent", 4]}
            }},
            {"$sort": {"TotalSpent": -1}}
        ]
        mongo_results = list(db["sales_orders"].aggregate(mongo_pipeline))
        
        return {
            "query_description": "Total de ventas por cliente, ordenado por monto total",
            "sql_query": sql_query.strip(),
            "mongo_query": "db.sales_orders.aggregate([{$group: ...}, {$sort: {TotalSpent: -1}}])",
            "sql_results": sql_df.to_dict(orient='records'),
            "mongo_results": mongo_results,
            "sql_count": len(sql_df),
            "mongo_count": len(mongo_results),
            "match": len(sql_df) == len(mongo_results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en comparación: {str(e)}")


@router.get("/orders-detail")
async def compare_order_details():
    """
    Compara una orden específica con todos sus detalles.
    """
    try:
        conn = get_sql_connection()
        db = get_mongo_db()
        
        # Obtener primer SalesOrderID disponible
        first_order = pd.read_sql(
            "SELECT TOP 1 SalesOrderID FROM SalesLT.SalesOrderHeader ORDER BY SalesOrderID", 
            conn
        )
        
        if first_order.empty:
            return {"message": "No hay órdenes de venta"}
        
        order_id = int(first_order['SalesOrderID'].iloc[0])
        
        # SQL: Orden con detalles
        sql_query = f"""
            SELECT 
                soh.SalesOrderID,
                soh.SalesOrderNumber,
                soh.OrderDate,
                soh.TotalDue,
                c.FirstName + ' ' + c.LastName AS CustomerName,
                sod.SalesOrderDetailID,
                sod.ProductID,
                p.Name AS ProductName,
                sod.OrderQty,
                sod.UnitPrice,
                sod.LineTotal
            FROM SalesLT.SalesOrderHeader soh
            INNER JOIN SalesLT.Customer c ON soh.CustomerID = c.CustomerID
            INNER JOIN SalesLT.SalesOrderDetail sod ON soh.SalesOrderID = sod.SalesOrderID
            INNER JOIN SalesLT.Product p ON sod.ProductID = p.ProductID
            WHERE soh.SalesOrderID = {order_id}
            ORDER BY sod.SalesOrderDetailID
        """
        sql_df = pd.read_sql(sql_query, conn)
        conn.close()
        
        for col in sql_df.select_dtypes(include=['datetime64', 'datetimetz']).columns:
            sql_df[col] = sql_df[col].astype(str)
        
        # MongoDB: Misma orden
        mongo_order = db["sales_orders"].find_one(
            {"SalesOrderID": order_id},
            {"_id": 0}
        )
        
        # Serializar ObjectId si existe
        if mongo_order and "_id" in mongo_order:
            mongo_order["_id"] = str(mongo_order["_id"])
        
        return {
            "query_description": f"Detalle completo de la orden #{order_id}",
            "sql_query": sql_query.strip(),
            "mongo_query": f'db.sales_orders.findOne({{SalesOrderID: {order_id}}})',
            "sql_results": sql_df.to_dict(orient='records'),
            "mongo_result": mongo_order,
            "sql_detail_count": len(sql_df),
            "mongo_detail_count": len(mongo_order.get("order_details", [])) if mongo_order else 0,
            "match": len(sql_df) == (len(mongo_order.get("order_details", [])) if mongo_order else 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en comparación: {str(e)}")


@router.get("/product-by-category")
async def compare_products_by_category():
    """
    Compara productos agrupados por categoría.
    """
    try:
        conn = get_sql_connection()
        db = get_mongo_db()
        
        # SQL Query
        sql_query = """
            SELECT 
                pc.Name AS CategoryName,
                COUNT(p.ProductID) AS ProductCount,
                AVG(p.ListPrice) AS AvgPrice,
                MIN(p.ListPrice) AS MinPrice,
                MAX(p.ListPrice) AS MaxPrice
            FROM SalesLT.ProductCategory pc
            INNER JOIN SalesLT.Product p ON pc.ProductCategoryID = p.ProductCategoryID
            GROUP BY pc.Name
            ORDER BY COUNT(p.ProductID) DESC
        """
        sql_df = pd.read_sql(sql_query, conn)
        conn.close()
        
        for col in sql_df.select_dtypes(include=['float64']).columns:
            sql_df[col] = sql_df[col].round(4)
        
        # MongoDB Query equivalente
        mongo_pipeline = [
            {"$group": {
                "_id": "$category.name",
                "ProductCount": {"$sum": 1},
                "AvgPrice": {"$avg": "$ListPrice"},
                "MinPrice": {"$min": "$ListPrice"},
                "MaxPrice": {"$max": "$ListPrice"}
            }},
            {"$project": {
                "_id": 0,
                "CategoryName": "$_id",
                "ProductCount": 1,
                "AvgPrice": {"$round": ["$AvgPrice", 4]},
                "MinPrice": 1,
                "MaxPrice": 1
            }},
            {"$sort": {"ProductCount": -1}}
        ]
        mongo_results = list(db["products"].aggregate(mongo_pipeline))
        
        return {
            "query_description": "Productos por categoría con estadísticas de precio",
            "sql_query": sql_query.strip(),
            "mongo_query": "db.products.aggregate([{$group: ...}, {$sort: {ProductCount: -1}}])",
            "sql_results": sql_df.to_dict(orient='records'),
            "mongo_results": mongo_results,
            "sql_count": len(sql_df),
            "mongo_count": len(mongo_results),
            "match": len(sql_df) == len(mongo_results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en comparación: {str(e)}")
