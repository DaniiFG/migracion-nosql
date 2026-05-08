"""
Router de Migración: Transforma datos de SQL Server a MongoDB usando Pandas.

PATRÓN SAGA (Orquestación):
Cada paso de la migración es una transacción local. Si un paso falla,
se ejecutan acciones compensatorias (rollback) para deshacer los pasos
anteriores, garantizando consistencia eventual.

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
import hashlib
import json
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
    "saga_log": [],
    "rollback_log": [],
    "started_at": None,
    "completed_at": None
}


# ================================================================
# SAGA: Registro de pasos y acciones compensatorias
# ================================================================

class SagaOrchestrator:
    """
    Orquestador del patrón Saga para la migración.
    Registra cada paso ejecutado y su acción compensatoria.
    Si un paso falla, ejecuta rollback en orden inverso.
    """

    def __init__(self, db):
        self.db = db
        self.executed_steps = []  # [(nombre, colección_creada)]
        self.log = []

    def register_step(self, step_name: str, collection_name: str):
        """Registra un paso completado exitosamente."""
        self.executed_steps.append({
            "step": step_name,
            "collection": collection_name,
            "timestamp": datetime.now().isoformat(),
            "status": "completed"
        })
        self.log.append(f"✅ SAGA: Paso '{step_name}' completado → colección '{collection_name}'")

    def compensate(self) -> list:
        """
        Ejecuta acciones compensatorias en orden inverso (rollback).
        Elimina las colecciones creadas por los pasos que ya se ejecutaron.
        """
        rollback_log = []
        rollback_log.append(f"⚠️ SAGA: Iniciando rollback de {len(self.executed_steps)} pasos...")

        for step in reversed(self.executed_steps):
            try:
                collection = step["collection"]
                count = self.db[collection].count_documents({})
                self.db.drop_collection(collection)
                step["status"] = "rolled_back"
                msg = f"↩️ ROLLBACK: Eliminada colección '{collection}' ({count} documentos) del paso '{step['step']}'"
                rollback_log.append(msg)
                self.log.append(msg)
            except Exception as e:
                msg = f"❌ ROLLBACK FALLÓ: colección '{step['collection']}' → {str(e)}"
                rollback_log.append(msg)
                self.log.append(msg)

        rollback_log.append("🔄 SAGA: Rollback completado. MongoDB en estado consistente.")
        return rollback_log

    def get_log(self) -> list:
        return self.log

    def get_steps(self) -> list:
        return self.executed_steps


# ================================================================
# Utilidades
# ================================================================

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


def compute_checksum(data_list: list) -> str:
    """Calcula un checksum MD5 de una lista de diccionarios para validación."""
    serialized = json.dumps(data_list, sort_keys=True, default=str)
    return hashlib.md5(serialized.encode()).hexdigest()


# ================================================================
# Endpoints
# ================================================================

@router.get("/status")
async def get_migration_status():
    """Obtiene el estado actual de la migración, incluyendo log de la Saga."""
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
            "saga_log": [],
            "rollback_log": [],
            "started_at": None,
            "completed_at": None
        })

        return {"message": "MongoDB limpiado y migración reseteada"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al resetear: {str(e)}")


@router.post("/execute")
async def execute_full_migration():
    """
    Ejecuta la migración completa usando el PATRÓN SAGA.

    Cada paso es una transacción local. Si cualquier paso falla,
    se ejecutan acciones compensatorias (rollback) para deshacer
    todos los pasos anteriores, dejando MongoDB en estado consistente.

    Dominios migrados:
    1. Categorías de Producto
    2. Productos (con categorías, modelos y descripciones embebidas)
    3. Clientes (con direcciones embebidas)
    4. Direcciones (colección de referencia)
    5. Órdenes de Venta (con detalles y datos denormalizados)
    6. Índices
    """
    global migration_status

    if migration_status["is_running"]:
        raise HTTPException(status_code=409, detail="Ya hay una migración en progreso")

    migration_status.update({
        "is_running": True,
        "progress": 0,
        "current_step": "Iniciando migración con Saga...",
        "steps_completed": [],
        "errors": [],
        "saga_log": [],
        "rollback_log": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": None
    })

    conn = None
    try:
        conn = get_sql_connection()
        db = get_mongo_db()
        saga = SagaOrchestrator(db)

        # ========================================
        # SAGA PASO 1: Migrar Categorías
        # ========================================
        migration_status["current_step"] = "Saga Paso 1/6: Migrando categorías de producto..."
        migration_status["progress"] = 10

        try:
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

            saga.register_step("Categorías de Producto", "product_categories")
            migration_status["steps_completed"].append(
                f"✅ Categorías: {len(categories_df)} registros migrados"
            )
        except Exception as e:
            migration_status["rollback_log"] = saga.compensate()
            raise Exception(f"Fallo en Paso 1 (Categorías): {str(e)}")

        # ========================================
        # SAGA PASO 2: Migrar Productos (embedding)
        # ========================================
        migration_status["current_step"] = "Saga Paso 2/6: Migrando productos..."
        migration_status["progress"] = 25

        try:
            products_df = pd.read_sql("""
                SELECT 
                    p.ProductID, p.Name AS ProductName, p.ProductNumber,
                    p.Color, p.StandardCost, p.ListPrice, p.Size, p.Weight,
                    p.ProductCategoryID, pc.Name AS CategoryName,
                    parent_pc.Name AS ParentCategoryName,
                    p.ProductModelID, pm.Name AS ModelName,
                    p.SellStartDate, p.SellEndDate, p.DiscontinuedDate,
                    p.ThumbNailPhoto, p.ThumbnailPhotoFileName,
                    p.rowguid, p.ModifiedDate
                FROM SalesLT.Product p
                LEFT JOIN SalesLT.ProductCategory pc ON p.ProductCategoryID = pc.ProductCategoryID
                LEFT JOIN SalesLT.ProductCategory parent_pc ON pc.ParentProductCategoryID = parent_pc.ProductCategoryID
                LEFT JOIN SalesLT.ProductModel pm ON p.ProductModelID = pm.ProductModelID
            """, conn)
            products_df = clean_dataframe(products_df)

            descriptions_df = pd.read_sql("""
                SELECT pmpd.ProductModelID, pd.ProductDescriptionID,
                       pd.Description, pmpd.Culture
                FROM SalesLT.ProductModelProductDescription pmpd
                INNER JOIN SalesLT.ProductDescription pd 
                    ON pmpd.ProductDescriptionID = pd.ProductDescriptionID
            """, conn)
            descriptions_df = clean_dataframe(descriptions_df)

            product_docs = []
            for _, prod in products_df.iterrows():
                doc = prod.to_dict()
                doc["category"] = {
                    "id": doc.pop("ProductCategoryID", None),
                    "name": doc.pop("CategoryName", None),
                    "parent_name": doc.pop("ParentCategoryName", None)
                }
                model_id = doc.pop("ProductModelID", None)
                model_name = doc.pop("ModelName", None)
                model_descs = descriptions_df[
                    descriptions_df["ProductModelID"] == model_id
                ].to_dict(orient='records') if model_id else []
                doc["model"] = {"id": model_id, "name": model_name, "descriptions": model_descs}
                doc.pop("ThumbNailPhoto", None)
                product_docs.append(doc)

            if product_docs:
                db.drop_collection("products")
                db["products"].insert_many(product_docs)

            saga.register_step("Productos (con embedding)", "products")
            migration_status["steps_completed"].append(
                f"✅ Productos: {len(product_docs)} registros migrados (con categorías y descripciones embebidas)"
            )
        except Exception as e:
            migration_status["rollback_log"] = saga.compensate()
            raise Exception(f"Fallo en Paso 2 (Productos): {str(e)}")

        # ========================================
        # SAGA PASO 3: Migrar Clientes (embedding)
        # ========================================
        migration_status["current_step"] = "Saga Paso 3/6: Migrando clientes..."
        migration_status["progress"] = 45

        try:
            customers_df = pd.read_sql("""
                SELECT c.CustomerID, c.NameStyle, c.Title, c.FirstName,
                       c.MiddleName, c.LastName, c.Suffix, c.CompanyName,
                       c.SalesPerson, c.EmailAddress, c.Phone,
                       c.PasswordHash, c.PasswordSalt, c.rowguid, c.ModifiedDate
                FROM SalesLT.Customer c
            """, conn)
            customers_df = clean_dataframe(customers_df)

            addresses_df = pd.read_sql("""
                SELECT ca.CustomerID, ca.AddressType, a.AddressID,
                       a.AddressLine1, a.AddressLine2, a.City,
                       a.StateProvince, a.CountryRegion, a.PostalCode,
                       a.rowguid AS address_rowguid, a.ModifiedDate AS address_modified
                FROM SalesLT.CustomerAddress ca
                INNER JOIN SalesLT.Address a ON ca.AddressID = a.AddressID
            """, conn)
            addresses_df = clean_dataframe(addresses_df)

            customer_docs = []
            for _, cust in customers_df.iterrows():
                doc = cust.to_dict()
                name_parts = [doc.get("FirstName", "")]
                if doc.get("MiddleName"):
                    name_parts.append(doc["MiddleName"])
                name_parts.append(doc.get("LastName", ""))
                doc["FullName"] = " ".join(name_parts)
                cust_addresses = addresses_df[
                    addresses_df["CustomerID"] == doc["CustomerID"]
                ].drop(columns=["CustomerID"]).to_dict(orient='records')
                doc["addresses"] = cust_addresses
                doc["address_count"] = len(cust_addresses)
                customer_docs.append(doc)

            if customer_docs:
                db.drop_collection("customers")
                db["customers"].insert_many(customer_docs)

            saga.register_step("Clientes (con direcciones embebidas)", "customers")
            migration_status["steps_completed"].append(
                f"✅ Clientes: {len(customer_docs)} registros (con {len(addresses_df)} direcciones embebidas)"
            )
        except Exception as e:
            migration_status["rollback_log"] = saga.compensate()
            raise Exception(f"Fallo en Paso 3 (Clientes): {str(e)}")

        # ========================================
        # SAGA PASO 4: Migrar Direcciones (referencia)
        # ========================================
        migration_status["current_step"] = "Saga Paso 4/6: Migrando direcciones..."
        migration_status["progress"] = 60

        try:
            all_addresses_df = pd.read_sql("""
                SELECT a.AddressID, a.AddressLine1, a.AddressLine2, a.City,
                       a.StateProvince, a.CountryRegion, a.PostalCode,
                       a.rowguid, a.ModifiedDate
                FROM SalesLT.Address a
            """, conn)
            all_addresses_df = clean_dataframe(all_addresses_df)

            if not all_addresses_df.empty:
                db.drop_collection("addresses")
                db["addresses"].insert_many(all_addresses_df.to_dict(orient='records'))

            saga.register_step("Direcciones (referencia)", "addresses")
            migration_status["steps_completed"].append(
                f"✅ Direcciones: {len(all_addresses_df)} registros migrados"
            )
        except Exception as e:
            migration_status["rollback_log"] = saga.compensate()
            raise Exception(f"Fallo en Paso 4 (Direcciones): {str(e)}")

        # ========================================
        # SAGA PASO 5: Migrar Órdenes (embedding + denorm)
        # ========================================
        migration_status["current_step"] = "Saga Paso 5/6: Migrando órdenes de venta..."
        migration_status["progress"] = 75

        try:
            orders_df = pd.read_sql("""
                SELECT soh.SalesOrderID, soh.RevisionNumber, soh.OrderDate,
                    soh.DueDate, soh.ShipDate, soh.Status, soh.OnlineOrderFlag,
                    soh.SalesOrderNumber, soh.PurchaseOrderNumber, soh.AccountNumber,
                    soh.CustomerID, c.FirstName + ' ' + c.LastName AS CustomerName,
                    c.CompanyName,
                    soh.ShipToAddressID, sa.AddressLine1 AS ShipToAddress,
                    sa.City AS ShipToCity, sa.StateProvince AS ShipToState,
                    sa.PostalCode AS ShipToPostalCode,
                    soh.BillToAddressID, ba.AddressLine1 AS BillToAddress,
                    ba.City AS BillToCity, ba.StateProvince AS BillToState,
                    ba.PostalCode AS BillToPostalCode,
                    soh.ShipMethod, soh.CreditCardApprovalCode,
                    soh.SubTotal, soh.TaxAmt, soh.Freight, soh.TotalDue,
                    soh.Comment, soh.rowguid, soh.ModifiedDate
                FROM SalesLT.SalesOrderHeader soh
                INNER JOIN SalesLT.Customer c ON soh.CustomerID = c.CustomerID
                LEFT JOIN SalesLT.Address sa ON soh.ShipToAddressID = sa.AddressID
                LEFT JOIN SalesLT.Address ba ON soh.BillToAddressID = ba.AddressID
            """, conn)
            orders_df = clean_dataframe(orders_df)

            details_df = pd.read_sql("""
                SELECT sod.SalesOrderID, sod.SalesOrderDetailID, sod.OrderQty,
                    sod.ProductID, p.Name AS ProductName, p.ProductNumber,
                    p.Color AS ProductColor, sod.UnitPrice, sod.UnitPriceDiscount,
                    sod.LineTotal, sod.rowguid, sod.ModifiedDate
                FROM SalesLT.SalesOrderDetail sod
                INNER JOIN SalesLT.Product p ON sod.ProductID = p.ProductID
            """, conn)
            details_df = clean_dataframe(details_df)

            order_docs = []
            for _, order in orders_df.iterrows():
                doc = order.to_dict()
                doc["ship_to"] = {
                    "address_id": doc.pop("ShipToAddressID", None),
                    "address": doc.pop("ShipToAddress", None),
                    "city": doc.pop("ShipToCity", None),
                    "state": doc.pop("ShipToState", None),
                    "postal_code": doc.pop("ShipToPostalCode", None)
                }
                doc["bill_to"] = {
                    "address_id": doc.pop("BillToAddressID", None),
                    "address": doc.pop("BillToAddress", None),
                    "city": doc.pop("BillToCity", None),
                    "state": doc.pop("BillToState", None),
                    "postal_code": doc.pop("BillToPostalCode", None)
                }
                order_details = details_df[
                    details_df["SalesOrderID"] == doc["SalesOrderID"]
                ].drop(columns=["SalesOrderID"]).to_dict(orient='records')
                doc["order_details"] = order_details
                doc["items_count"] = len(order_details)
                doc["customer"] = {
                    "id": doc.pop("CustomerID", None),
                    "name": doc.pop("CustomerName", None),
                    "company": doc.pop("CompanyName", None)
                }
                order_docs.append(doc)

            if order_docs:
                db.drop_collection("sales_orders")
                db["sales_orders"].insert_many(order_docs)

            saga.register_step("Órdenes de Venta (embedding + denorm)", "sales_orders")
            migration_status["steps_completed"].append(
                f"✅ Órdenes: {len(order_docs)} órdenes (con {len(details_df)} detalles embebidos)"
            )
        except Exception as e:
            migration_status["rollback_log"] = saga.compensate()
            raise Exception(f"Fallo en Paso 5 (Órdenes): {str(e)}")

        # ========================================
        # SAGA PASO 6: Crear índices
        # ========================================
        migration_status["current_step"] = "Saga Paso 6/6: Creando índices..."
        migration_status["progress"] = 90

        try:
            db["products"].create_index("ProductID", unique=True)
            db["products"].create_index("ProductNumber")
            db["products"].create_index("category.name")
            db["products"].create_index([("ListPrice", -1)])
            db["customers"].create_index("CustomerID", unique=True)
            db["customers"].create_index("EmailAddress")
            db["customers"].create_index("CompanyName")
            db["customers"].create_index("FullName")
            db["sales_orders"].create_index("SalesOrderID", unique=True)
            db["sales_orders"].create_index("customer.id")
            db["sales_orders"].create_index("OrderDate")
            db["sales_orders"].create_index("SalesOrderNumber")
            db["product_categories"].create_index("ProductCategoryID", unique=True)
            db["addresses"].create_index("AddressID", unique=True)
            db["addresses"].create_index("City")

            saga.register_step("Índices creados", "_indexes")
            migration_status["steps_completed"].append("✅ Índices creados en todas las colecciones")
        except Exception as e:
            migration_status["rollback_log"] = saga.compensate()
            raise Exception(f"Fallo en Paso 6 (Índices): {str(e)}")

        conn.close()

        # SAGA completada exitosamente
        migration_status.update({
            "is_running": False,
            "progress": 100,
            "current_step": "¡Saga completada exitosamente! Todos los pasos migraron sin errores.",
            "saga_log": saga.get_log(),
            "completed_at": datetime.now().isoformat()
        })

        return {
            "message": "Migración completada exitosamente (Saga sin rollback necesario)",
            "saga_steps": saga.get_steps(),
            "status": migration_status
        }

    except Exception as e:
        if conn:
            conn.close()
        migration_status.update({
            "is_running": False,
            "current_step": f"❌ Saga falló: {str(e)}",
            "errors": migration_status["errors"] + [str(e)],
            "saga_log": migration_status.get("saga_log", []) + [f"❌ SAGA ABORTADA: {str(e)}"],
            "completed_at": datetime.now().isoformat()
        })
        raise HTTPException(status_code=500, detail=f"Saga falló con rollback: {str(e)}")


@router.get("/saga-log")
async def get_saga_log():
    """Obtiene el log detallado de la Saga (pasos ejecutados y rollbacks)."""
    return {
        "saga_log": migration_status.get("saga_log", []),
        "rollback_log": migration_status.get("rollback_log", []),
        "steps_completed": migration_status.get("steps_completed", []),
        "errors": migration_status.get("errors", [])
    }


@router.get("/mapping")
async def get_mapping_info():
    """
    Muestra el mapeo de tablas SQL Server → colecciones MongoDB.
    Documenta los patrones DDD y estrategias de migración aplicados.
    """
    return {
        "title": "Mapeo de Migración: SQL Server → MongoDB",
        "strategy": "Domain-Driven Design (DDD) con patrones de Embedding y Referencing",
        "migration_pattern": "Saga (Orquestación) con acciones compensatorias",
        "domains": [
            {
                "domain": "Catálogo de Productos",
                "sql_tables": [
                    "SalesLT.Product", "SalesLT.ProductCategory",
                    "SalesLT.ProductModel", "SalesLT.ProductModelProductDescription",
                    "SalesLT.ProductDescription"
                ],
                "mongo_collections": ["products", "product_categories"],
                "pattern": "Embedding",
                "description": "Categoría, modelo y descripciones se incrustan como subdocumentos dentro del producto."
            },
            {
                "domain": "Clientes",
                "sql_tables": [
                    "SalesLT.Customer", "SalesLT.CustomerAddress", "SalesLT.Address"
                ],
                "mongo_collections": ["customers", "addresses"],
                "pattern": "Embedding + Referencing",
                "description": "Direcciones se incrustan en el cliente Y se mantiene colección independiente para consultas geográficas."
            },
            {
                "domain": "Ventas",
                "sql_tables": [
                    "SalesLT.SalesOrderHeader", "SalesLT.SalesOrderDetail"
                ],
                "mongo_collections": ["sales_orders"],
                "pattern": "Embedding + Denormalization",
                "description": "Detalles de la orden, datos del cliente y direcciones se incrustan y denormalizan."
            }
        ],
        "patterns_used": {
            "Embedding (Incrustación)": "Datos relacionados 1:N se almacenan como arrays de subdocumentos.",
            "Referencing (Referencia)": "IDs originales como referencia para relaciones N:M.",
            "Denormalization (Desnormalización)": "Campos frecuentes se copian para evitar lookups.",
            "Saga (Orquestación)": "Cada paso es transacción local con acción compensatoria si falla."
        },
        "indexes": {
            "products": ["ProductID (unique)", "ProductNumber", "category.name", "ListPrice (desc)"],
            "customers": ["CustomerID (unique)", "EmailAddress", "CompanyName", "FullName"],
            "sales_orders": ["SalesOrderID (unique)", "customer.id", "OrderDate", "SalesOrderNumber"],
            "product_categories": ["ProductCategoryID (unique)"],
            "addresses": ["AddressID (unique)", "City"]
        }
    }
