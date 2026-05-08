# Blueprint de Migración: AdventureWorksLT → MongoDB

**Proyecto:** Migración de Monolito Relacional a MongoDB Distribuido  
**Base de datos origen:** AdventureWorksLT2022 (SQL Server 2022)  
**Base de datos destino:** MongoDB 7.0  
**Fecha:** Mayo 2026

---

## 1. Análisis del Modelo Relacional

### Tablas origen (AdventureWorksLT)

| # | Esquema.Tabla | Registros | Rol |
|---|--------------|-----------|-----|
| 1 | SalesLT.Product | 295 | Catálogo de productos |
| 2 | SalesLT.ProductCategory | 41 | Categorías jerárquicas |
| 3 | SalesLT.ProductModel | 128 | Modelos de producto |
| 4 | SalesLT.ProductDescription | 762 | Descripciones multilenguaje |
| 5 | SalesLT.ProductModelProductDescription | 762 | Relación modelo-descripción |
| 6 | SalesLT.Customer | 847 | Clientes |
| 7 | SalesLT.Address | 450 | Direcciones |
| 8 | SalesLT.CustomerAddress | 417 | Relación cliente-dirección |
| 9 | SalesLT.SalesOrderHeader | 32 | Cabeceras de orden |
| 10 | SalesLT.SalesOrderDetail | 542 | Líneas de detalle |

**Total:** 10 tablas principales, ~4,276 registros, 15 relaciones FK.

### Relaciones identificadas

| FK | Tabla padre | Tabla hija | Cardinalidad |
|----|------------|------------|-------------|
| ProductCategoryID | ProductCategory | Product | 1:N |
| ParentProductCategoryID | ProductCategory | ProductCategory | 1:N (autoreferencia) |
| ProductModelID | ProductModel | Product | 1:N |
| ProductModelID | ProductModel | ProductModelProductDescription | 1:N |
| ProductDescriptionID | ProductDescription | ProductModelProductDescription | 1:N |
| CustomerID | Customer | CustomerAddress | 1:N |
| AddressID | Address | CustomerAddress | 1:N |
| CustomerID | Customer | SalesOrderHeader | 1:N |
| ShipToAddressID | Address | SalesOrderHeader | 1:N |
| BillToAddressID | Address | SalesOrderHeader | 1:N |
| SalesOrderID | SalesOrderHeader | SalesOrderDetail | 1:N |
| ProductID | Product | SalesOrderDetail | 1:N |

---

## 2. Descomposición por Dominios (DDD)

### Bounded Context 1: Catálogo de Productos

**Tablas involucradas:** Product, ProductCategory, ProductModel, ProductModelProductDescription, ProductDescription

**Decisión de diseño:** Las categorías, modelos y descripciones siempre se consultan junto con el producto. No existen consultas independientes frecuentes sobre descripciones o modelos sin el contexto del producto.

**Patrón:** Embedding total — categoría, modelo y descripciones como subdocumentos. Se mantiene `product_categories` como colección separada para navegación jerárquica.

**Resultado:** 5 tablas → 2 colecciones (`products`, `product_categories`)

### Bounded Context 2: Clientes

**Tablas involucradas:** Customer, CustomerAddress, Address

**Decisión de diseño:** Las direcciones se consultan frecuentemente junto con el cliente (perfil), pero también de forma independiente para análisis geográfico y logística.

**Patrón:** Embedding + Referencing — direcciones embebidas en el cliente para acceso rápido, y colección `addresses` independiente para consultas geográficas.

**Resultado:** 3 tablas → 2 colecciones (`customers`, `addresses`)

### Bounded Context 3: Ventas

**Tablas involucradas:** SalesOrderHeader, SalesOrderDetail

**Decisión de diseño:** Una orden siempre se lee completa (cabecera + líneas). Se denormalizan nombre de cliente, nombre de producto y direcciones para eliminar lookups.

**Patrón:** Embedding + Denormalization — detalles como array de subdocumentos, datos del cliente y direcciones embebidos.

**Resultado:** 2 tablas → 1 colección (`sales_orders`)

---

## 3. Modelo MongoDB Destino

### Colección: `products`

```json
{
  "ProductID": 680,
  "ProductName": "HL Road Frame - Black, 58",
  "ProductNumber": "FR-R92B-58",
  "Color": "Black",
  "StandardCost": 868.6342,
  "ListPrice": 1431.50,
  "Size": "58",
  "Weight": 1016.04,
  "category": {
    "id": 18,
    "name": "Road Frames",
    "parent_name": "Components"
  },
  "model": {
    "id": 6,
    "name": "HL Road Frame",
    "descriptions": [
      {"Culture": "en", "Description": "Our lightest..."},
      {"Culture": "fr", "Description": "Notre plus léger..."}
    ]
  },
  "SellStartDate": "2002-06-01T00:00:00",
  "rowguid": "43dd68d6-14a4-461f-9069-55309d90ea7e",
  "ModifiedDate": "2014-02-08T10:01:36.827000"
}
```

### Colección: `customers`

```json
{
  "CustomerID": 29485,
  "FirstName": "Catherine",
  "LastName": "Abel",
  "FullName": "Catherine Abel",
  "CompanyName": "Professional Sales and Service",
  "EmailAddress": "catherine0@adventure-works.com",
  "Phone": "747-555-0171",
  "addresses": [
    {
      "AddressType": "Main Office",
      "AddressID": 1086,
      "AddressLine1": "123 Riverside Drive",
      "City": "Renton",
      "StateProvince": "Washington",
      "CountryRegion": "United States",
      "PostalCode": "98055"
    }
  ],
  "address_count": 1
}
```

### Colección: `sales_orders`

```json
{
  "SalesOrderID": 71774,
  "SalesOrderNumber": "SO71774",
  "OrderDate": "2008-06-01T00:00:00",
  "Status": 5,
  "SubTotal": 880.35,
  "TaxAmt": 70.43,
  "TotalDue": 985.02,
  "customer": {
    "id": 29847,
    "name": "David Campbell",
    "company": "Extreme Riding Supplies"
  },
  "ship_to": {
    "address_id": 1092,
    "address": "456 Main St",
    "city": "Dallas",
    "state": "Texas"
  },
  "bill_to": { "..." },
  "order_details": [
    {
      "SalesOrderDetailID": 110562,
      "ProductID": 836,
      "ProductName": "ML Road Frame-W - Yellow, 40",
      "OrderQty": 1,
      "UnitPrice": 356.898,
      "LineTotal": 356.898
    }
  ],
  "items_count": 3
}
```

---

## 4. Estrategia de Indexación

| Colección | Índice | Tipo | Justificación |
|-----------|--------|------|---------------|
| products | ProductID | Unique | Lookup por ID |
| products | ProductNumber | Standard | Búsqueda por número |
| products | category.name | Standard | Filtrado por categoría |
| products | ListPrice (desc) | Standard | Ordenamiento por precio |
| customers | CustomerID | Unique | Lookup por ID |
| customers | EmailAddress | Standard | Búsqueda por email |
| customers | CompanyName | Standard | Búsqueda por empresa |
| sales_orders | SalesOrderID | Unique | Lookup por ID |
| sales_orders | customer.id | Standard | Órdenes por cliente + shard key |
| sales_orders | OrderDate | Standard | Consultas por rango de fecha |

---

## 5. Patrón de Migración: Saga (Orquestación)

| Paso | Operación | Compensación (rollback) |
|------|-----------|------------------------|
| 1 | Insertar `product_categories` | Eliminar `product_categories` |
| 2 | Insertar `products` | Eliminar `products` + paso 1 |
| 3 | Insertar `customers` | Eliminar `customers` + pasos 1-2 |
| 4 | Insertar `addresses` | Eliminar `addresses` + pasos 1-3 |
| 5 | Insertar `sales_orders` | Eliminar `sales_orders` + pasos 1-4 |
| 6 | Crear índices | Eliminar todo |

Coordinador: FastAPI (`SagaOrchestrator`). Si cualquier paso falla, se ejecutan compensaciones en orden inverso.

---

## 6. Validación de Integridad Post-Migración

| Validación | Método | Criterio de éxito |
|-----------|--------|-------------------|
| Conteo de registros | `COUNT(*)` SQL vs `countDocuments()` Mongo | Igualdad exacta |
| Top 10 productos caros | Query equivalente en ambas bases | Mismos registros y valores |
| Clientes con direcciones | JOIN SQL vs subdocumento Mongo | Mismos conteos por cliente |
| Ventas por cliente | GROUP BY SQL vs `$group` Mongo | Mismos totales |
| Detalle de orden | JOIN SQL vs documento embebido | Mismo número de líneas |
| Productos por categoría | GROUP BY SQL vs `$group` Mongo | Mismas estadísticas |

---

## 7. Configuración del Cluster (Producción)

| Componente | Cantidad | Puerto | Función |
|-----------|----------|--------|---------|
| Config Server | 1 (replica set) | 27019 | Metadata del cluster |
| Shard 1 | 3 (replica set) | 27018 | Almacenamiento de datos |
| Mongos Router | 1 | 27017 | Punto de entrada |

### Shard Keys

| Colección | Shard Key | Tipo | Justificación |
|-----------|-----------|------|---------------|
| sales_orders | `customer.id` | Ranged | Distribuye órdenes uniformemente por cliente |
| customers | `CustomerID` | Ranged | Distribución uniforme de clientes |
