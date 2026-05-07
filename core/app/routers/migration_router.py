"""
Router de Migración: Transforma datos de SQL Server a MongoDB usando Pandas.

Estrategia de migración aplicando patrones DDD:
- Dominio "Customer": Customer + CustomerAddress + Address (incrustación)
- Dominio "Product": Product + ProductCategory + ProductModel + ProductModelProductDescription + ProductDescription (incrustación)
- Dominio "Sales": SalesOrderHeader + SalesOrderDetail (incrustación de detalles en header)

Patrones aplicados:
1. Embedding (incrustación): datos relacionados se incrustan como subdocumentos
2. Referencing (referencia): se mantienen IDs como referencia cuando los datos son independientes
3. Denormalization: se copian campos frecuentemente consultados para evitar joins
"""

from fastapi import APIRouter, HTTPException
import pandas as pd
import numpy as np
from datetime import datetime
from app.database import get_sql_connection, get_mongo_db

router = APIRouter()

# Estado global de migración
migration_status = {
    "is_running": False,
    "progress": 0,
    "current_step": "",
    "steps_completed": [],
    "errors": [],
    "started_at": None,
    "completed_at": None
}


def clean_dataframe(df):
    """Limpia un DataFrame para ser compatible con MongoDB."""
    # Reemplazar NaN/NaT con None
    df = df.where(pd.notnull(df), None)
    
    # Convertir columnas datetime
    for col in df.select_dtypes(include=['datetime64', 'datetimetz']).columns:
        df[col] = df[col].apply(lambda x: x.isoformat() if pd.notna(x) else None)
    
    # Convertir bytes a string
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: x.hex() if isinstance(x, (bytes, bytearray)) else x)
    
    # Convertir numpy types a python nativos
    for col in df.columns:
        if df[col].dtype in [np.int64, np.int32]:
            df[col] = df[col].apply(lambda x: int(x) if pd.notna(x) else None)
        elif df[col].dtype in [np.float64, np.float32]:
            df[col] = df[col].apply(lambda x: float(x) if pd.notna(x) else None)
    
    return df


@router.get("/status")
async def get_migration_status():
    """Obtiene el estado actual de la migración."""
    return migration_status


@router.post("/reset")
async def reset_migration():
    """Limpia MongoDB y resetea el estado de migración."""
    try:
        db = get_mongo_db()
        
        # Eliminar todas las colecciones
        for col_name in db.list_collection_names():
            db.drop_collection(col_name)
        
        migration_status.update({
            "is_running": False,
            "progress": 0,
            "current_step": "Reset completado",
            "steps_completed": [],
            "errors": [],
            "started_at": None,
            "completed_at": None
        })
        
        return {"message": "MongoDB limpiado y migración reseteada"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al resetear: {str(e)}")


@router.post("/execute")
async def execute_full_migration():
    """
    Ejecuta la migración completa de SQL Server a MongoDB.
    
    Dominios migrados:
    1. Customers (con direcciones embebidas)
    2. Products (con categorías, modelos y descripciones embebidas)
    3. Sales Orders (con detalles de orden y datos del producto embebidos)
    """
    global migration_status
    
    if migration_status["is_running"]:
        raise HTTPException(status_code=409, detail="Ya hay una migración en progreso")
    
    migration_status.update({
        "is_running": True,
        "progress": 0,
        "current_step": "Iniciando migración...",
        "steps_completed": [],
        "errors": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": None
    })
    
    try:
        conn = get_sql_connection()
        db = get_mongo_db()
        
        # ========================================
        # PASO 1: Migrar Categorías de Producto
        # ========================================
        migration_status["current_step"] = "Paso 1/6: Migrando categorías de producto..."
        migration_status["progress"] = 10
        
        categories_df = pd.read_sql("""
            SELECT 
                pc.ProductCategoryID,
                pc.Name AS CategoryName,
                pc.ParentProductCategoryID,
                parent.Name AS ParentCategoryName,
                pc.rowguid,
                pc.ModifiedDate
            FROM SalesLT.ProductCategory pc
            LEFT JOIN SalesLT.ProductCategory parent 
                ON pc.ParentProductCategoryID = parent.ProductCategoryID
        """, conn)
        categories_df = clean_dataframe(categories_df)
        
        if not categories_df.empty:
            db.drop_collection("product_categories")
            db["product_categories"].insert_many(categories_df.to_dict(orient='records'))
        
        migration_status["steps_completed"].append(
            f"✅ Categorías: {len(categories_df)} registros migrados"
        )
        
        # ========================================
        # PASO 2: Migrar Productos (con embedding)
        # ========================================
        migration_status["current_step"] = "Paso 2/6: Migrando productos con modelos y descripciones embebidas..."
        migration_status["progress"] = 25
        
        products_df = pd.read_sql("""
            SELECT 
                p.ProductID,
                p.Name AS ProductName,
                p.ProductNumber,
                p.Color,
                p.StandardCost,
                p.ListPrice,
                p.Size,
                p.Weight,
                p.ProductCategoryID,
                pc.Name AS CategoryName,
                parent_pc.Name AS ParentCategoryName,
                p.ProductModelID,
                pm.Name AS ModelName,
                p.SellStartDate,
                p.SellEndDate,
                p.DiscontinuedDate,
                p.ThumbNailPhoto,
                p.ThumbnailPhotoFileName,
                p.rowguid,
                p.ModifiedDate
            FROM SalesLT.Product p
            LEFT JOIN SalesLT.ProductCategory pc ON p.ProductCategoryID = pc.ProductCategoryID
            LEFT JOIN SalesLT.ProductCategory parent_pc ON pc.ParentProductCategoryID = parent_pc.ProductCategoryID
            LEFT JOIN SalesLT.ProductModel pm ON p.ProductModelID = pm.ProductModelID
        """, conn)
        products_df = clean_dataframe(products_df)
        
        # Obtener descripciones de modelos
        descriptions_df = pd.read_sql("""
            SELECT 
                pmpd.ProductModelID,
                pd.ProductDescriptionID,
                pd.Description,
                pmpd.Culture
            FROM SalesLT.ProductModelProductDescription pmpd
            INNER JOIN SalesLT.ProductDescription pd 
                ON pmpd.ProductDescriptionID = pd.ProductDescriptionID
        """, conn)
        descriptions_df = clean_dataframe(descriptions_df)
        
        # Crear documentos de productos con descripciones embebidas
        product_docs = []
        for _, prod in products_df.iterrows():
            doc = prod.to_dict()
            
            # Embeber categoría como subdocumento
            doc["category"] = {
                "id": doc.pop("ProductCategoryID", None),
                "name": doc.pop("CategoryName", None),
                "parent_name": doc.pop("ParentCategoryName", None)
            }
            
            # Embeber modelo con sus descripciones
            model_id = doc.pop("ProductModelID", None)
            model_name = doc.pop("ModelName", None)
            
            model_descs = descriptions_df[
                descriptions_df["ProductModelID"] == model_id
            ].to_dict(orient='records') if model_id else []
            
            doc["model"] = {
                "id": model_id,
                "name": model_name,
                "descriptions": model_descs
            }
            
            # Remover ThumbNailPhoto binario (muy grande para MongoDB)
            doc.pop("ThumbNailPhoto", None)
            
            product_docs.append(doc)
        
        if product_docs:
            db.drop_collection("products")
            db["products"].insert_many(product_docs)
        
        migration_status["steps_completed"].append(
            f"✅ Productos: {len(product_docs)} registros migrados (con categorías y descripciones embebidas)"
        )
        
        # ========================================
        # PASO 3: Migrar Clientes (con direcciones embebidas)
        # ========================================
        migration_status["current_step"] = "Paso 3/6: Migrando clientes con direcciones embebidas..."
        migration_status["progress"] = 45
        
        customers_df = pd.read_sql("""
            SELECT 
                c.CustomerID,
                c.NameStyle,
                c.Title,
                c.FirstName,
                c.MiddleName,
                c.LastName,
                c.Suffix,
                c.CompanyName,
                c.SalesPerson,
                c.EmailAddress,
                c.Phone,
                c.PasswordHash,
                c.PasswordSalt,
                c.rowguid,
                c.ModifiedDate
            FROM SalesLT.Customer c
        """, conn)
        customers_df = clean_dataframe(customers_df)
        
        # Obtener direcciones de clientes
        addresses_df = pd.read_sql("""
            SELECT 
                ca.CustomerID,
                ca.AddressType,
                a.AddressID,
                a.AddressLine1,
                a.AddressLine2,
                a.City,
                a.StateProvince,
                a.CountryRegion,
                a.PostalCode,
                a.rowguid AS address_rowguid,
                a.ModifiedDate AS address_modified
            FROM SalesLT.CustomerAddress ca
            INNER JOIN SalesLT.Address a ON ca.AddressID = a.AddressID
        """, conn)
        addresses_df = clean_dataframe(addresses_df)
        
        # Crear documentos de clientes con direcciones embebidas
        customer_docs = []
        for _, cust in customers_df.iterrows():
            doc = cust.to_dict()
            
            # Nombre completo denormalizado
            name_parts = [doc.get("FirstName", "")]
            if doc.get("MiddleName"):
                name_parts.append(doc["MiddleName"])
            name_parts.append(doc.get("LastName", ""))
            doc["FullName"] = " ".join(name_parts)
            
            # Embeber direcciones
            cust_addresses = addresses_df[
                addresses_df["CustomerID"] == doc["CustomerID"]
            ].drop(columns=["CustomerID"]).to_dict(orient='records')
            
            doc["addresses"] = cust_addresses
            doc["address_count"] = len(cust_addresses)
            
            customer_docs.append(doc)
        
        if customer_docs:
            db.drop_collection("customers")
            db["customers"].insert_many(customer_docs)
        
        migration_status["steps_completed"].append(
            f"✅ Clientes: {len(customer_docs)} registros migrados (con {len(addresses_df)} direcciones embebidas)"
        )
        
        # ========================================
        # PASO 4: Migrar Direcciones (colección independiente por referencia)
        # ========================================
        migration_status["current_step"] = "Paso 4/6: Migrando direcciones como colección de referencia..."
        migration_status["progress"] = 60
        
        all_addresses_df = pd.read_sql("""
            SELECT 
                a.AddressID,
                a.AddressLine1,
                a.AddressLine2,
                a.City,
                a.StateProvince,
                a.CountryRegion,
                a.PostalCode,
                a.rowguid,
                a.ModifiedDate
            FROM SalesLT.Address a
        """, conn)
        all_addresses_df = clean_dataframe(all_addresses_df)
        
        if not all_addresses_df.empty:
            db.drop_collection("addresses")
            db["addresses"].insert_many(all_addresses_df.to_dict(orient='records'))
        
        migration_status["steps_completed"].append(
            f"✅ Direcciones: {len(all_addresses_df)} registros migrados (colección de referencia)"
        )
        
        # ========================================
        # PASO 5: Migrar Órdenes de Venta (con detalles embebidos)
        # ========================================
        migration_status["current_step"] = "Paso 5/6: Migrando órdenes de venta con detalles embebidos..."
        migration_status["progress"] = 75
        
        orders_df = pd.read_sql("""
            SELECT 
                soh.SalesOrderID,
                soh.RevisionNumber,
                soh.OrderDate,
                soh.DueDate,
                soh.ShipDate,
                soh.Status,
                soh.OnlineOrderFlag,
                soh.SalesOrderNumber,
                soh.PurchaseOrderNumber,
                soh.AccountNumber,
                soh.CustomerID,
                c.FirstName + ' ' + c.LastName AS CustomerName,
                c.CompanyName,
                soh.ShipToAddressID,
                sa.AddressLine1 AS ShipToAddress,
                sa.City AS ShipToCity,
                sa.StateProvince AS ShipToState,
                sa.PostalCode AS ShipToPostalCode,
                soh.BillToAddressID,
                ba.AddressLine1 AS BillToAddress,
                ba.City AS BillToCity,
                ba.StateProvince AS BillToState,
                ba.PostalCode AS BillToPostalCode,
                soh.ShipMethod,
                soh.CreditCardApprovalCode,
                soh.SubTotal,
                soh.TaxAmt,
                soh.Freight,
                soh.TotalDue,
                soh.Comment,
                soh.rowguid,
                soh.ModifiedDate
            FROM SalesLT.SalesOrderHeader soh
            INNER JOIN SalesLT.Customer c ON soh.CustomerID = c.CustomerID
            LEFT JOIN SalesLT.Address sa ON soh.ShipToAddressID = sa.AddressID
            LEFT JOIN SalesLT.Address ba ON soh.BillToAddressID = ba.AddressID
        """, conn)
        orders_df = clean_dataframe(orders_df)
        
        # Obtener detalles de órdenes con info del producto
        details_df = pd.read_sql("""
            SELECT 
                sod.SalesOrderID,
                sod.SalesOrderDetailID,
                sod.OrderQty,
                sod.ProductID,
                p.Name AS ProductName,
                p.ProductNumber,
                p.Color AS ProductColor,
                sod.UnitPrice,
                sod.UnitPriceDiscount,
                sod.LineTotal,
                sod.rowguid,
                sod.ModifiedDate
            FROM SalesLT.SalesOrderDetail sod
            INNER JOIN SalesLT.Product p ON sod.ProductID = p.ProductID
        """, conn)
        details_df = clean_dataframe(details_df)
        
        # Crear documentos de órdenes con detalles embebidos
        order_docs = []
        for _, order in orders_df.iterrows():
            doc = order.to_dict()
            
            # Embeber dirección de envío como subdocumento
            doc["ship_to"] = {
                "address_id": doc.pop("ShipToAddressID", None),
                "address": doc.pop("ShipToAddress", None),
                "city": doc.pop("ShipToCity", None),
                "state": doc.pop("ShipToState", None),
                "postal_code": doc.pop("ShipToPostalCode", None)
            }
            
            # Embeber dirección de facturación como subdocumento
            doc["bill_to"] = {
                "address_id": doc.pop("BillToAddressID", None),
                "address": doc.pop("BillToAddress", None),
                "city": doc.pop("BillToCity", None),
                "state": doc.pop("BillToState", None),
                "postal_code": doc.pop("BillToPostalCode", None)
            }
            
            # Embeber detalles de la orden
            order_details = details_df[
                details_df["SalesOrderID"] == doc["SalesOrderID"]
            ].drop(columns=["SalesOrderID"]).to_dict(orient='records')
            
            doc["order_details"] = order_details
            doc["items_count"] = len(order_details)
            
            # Información del cliente denormalizada
            doc["customer"] = {
                "id": doc.pop("CustomerID", None),
                "name": doc.pop("CustomerName", None),
                "company": doc.pop("CompanyName", None)
            }
            
            order_docs.append(doc)
        
        if order_docs:
            db.drop_collection("sales_orders")
            db["sales_orders"].insert_many(order_docs)
        
        migration_status["steps_completed"].append(
            f"✅ Órdenes: {len(order_docs)} órdenes migradas (con {len(details_df)} detalles embebidos)"
        )
        
        # ========================================
        # PASO 6: Crear índices en MongoDB
        # ========================================
        migration_status["current_step"] = "Paso 6/6: Creando índices en MongoDB..."
        migration_status["progress"] = 90
        
        # Índices para productos
        db["products"].create_index("ProductID", unique=True)
        db["products"].create_index("ProductNumber")
        db["products"].create_index("category.name")
        db["products"].create_index([("ListPrice", -1)])
        
        # Índices para clientes
        db["customers"].create_index("CustomerID", unique=True)
        db["customers"].create_index("EmailAddress")
        db["customers"].create_index("CompanyName")
        db["customers"].create_index("FullName")
        
        # Índices para órdenes
        db["sales_orders"].create_index("SalesOrderID", unique=True)
        db["sales_orders"].create_index("customer.id")
        db["sales_orders"].create_index("OrderDate")
        db["sales_orders"].create_index("SalesOrderNumber")
        
        # Índices para categorías
        db["product_categories"].create_index("ProductCategoryID", unique=True)
        
        # Índices para direcciones
        db["addresses"].create_index("AddressID", unique=True)
        db["addresses"].create_index("City")
        
        migration_status["steps_completed"].append("✅ Índices creados en todas las colecciones")
        
        conn.close()
        
        # Migración completada
        migration_status.update({
            "is_running": False,
            "progress": 100,
            "current_step": "¡Migración completada exitosamente!",
            "completed_at": datetime.now().isoformat()
        })
        
        return {
            "message": "Migración completada exitosamente",
            "status": migration_status
        }
        
    except Exception as e:
        migration_status.update({
            "is_running": False,
            "current_step": f"Error: {str(e)}",
            "errors": migration_status["errors"] + [str(e)]
        })
        raise HTTPException(status_code=500, detail=f"Error en migración: {str(e)}")


@router.get("/mapping")
async def get_mapping_info():
    """
    Muestra el mapeo de tablas SQL Server → colecciones MongoDB.
    Documenta los patrones DDD y estrategias de migración aplicados.
    """
    return {
        "title": "Mapeo de Migración: SQL Server → MongoDB",
        "strategy": "Domain-Driven Design (DDD) con patrones de Embedding y Referencing",
        "domains": [
            {
                "domain": "Catálogo de Productos",
                "sql_tables": [
                    "SalesLT.Product",
                    "SalesLT.ProductCategory",
                    "SalesLT.ProductModel",
                    "SalesLT.ProductModelProductDescription",
                    "SalesLT.ProductDescription"
                ],
                "mongo_collections": ["products", "product_categories"],
                "pattern": "Embedding",
                "description": "Categoría, modelo y descripciones se incrustan como subdocumentos dentro del producto. Esto elimina JOINs y optimiza lecturas de catálogo."
            },
            {
                "domain": "Clientes",
                "sql_tables": [
                    "SalesLT.Customer",
                    "SalesLT.CustomerAddress",
                    "SalesLT.Address"
                ],
                "mongo_collections": ["customers", "addresses"],
                "pattern": "Embedding + Referencing",
                "description": "Direcciones se incrustan en el documento del cliente (embedding) Y se mantiene una colección independiente de direcciones (referencing) para consultas por ubicación."
            },
            {
                "domain": "Ventas",
                "sql_tables": [
                    "SalesLT.SalesOrderHeader",
                    "SalesLT.SalesOrderDetail"
                ],
                "mongo_collections": ["sales_orders"],
                "pattern": "Embedding + Denormalization",
                "description": "Detalles de la orden, datos del cliente y direcciones se incrustan en el documento de la orden. Se denormalizan nombre del cliente y nombre del producto para evitar lookups adicionales."
            }
        ],
        "patterns_used": {
            "Embedding (Incrustación)": "Datos relacionados 1:N se almacenan como arrays de subdocumentos dentro del documento padre.",
            "Referencing (Referencia)": "Se mantienen IDs originales como referencia para relaciones N:M o datos que se consultan independientemente.",
            "Denormalization (Desnormalización)": "Se copian campos frecuentemente consultados (ej: nombre de cliente en la orden) para evitar lookups adicionales."
        },
        "indexes": {
            "products": ["ProductID (unique)", "ProductNumber", "category.name", "ListPrice (desc)"],
            "customers": ["CustomerID (unique)", "EmailAddress", "CompanyName", "FullName"],
            "sales_orders": ["SalesOrderID (unique)", "customer.id", "OrderDate", "SalesOrderNumber"],
            "product_categories": ["ProductCategoryID (unique)"],
            "addresses": ["AddressID (unique)", "City"]
        }
    }
