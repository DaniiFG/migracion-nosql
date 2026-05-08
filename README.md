# 🔄 Migración de Monolito Relacional a MongoDB Distribuido

> **Taller Práctico** — Bases de Datos Masivas | Séptimo Semestre

Proyecto que demuestra la migración incremental de una base de datos monolítica relacional (SQL Server – AdventureWorksLT) hacia una arquitectura NoSQL con MongoDB, aplicando patrones de Domain-Driven Design (DDD), estrategias de embedding/referencing y validación de integridad post-migración.

---

## 📋 Tabla de Contenidos

- [Arquitectura](#-arquitectura)
- [Tecnologías](#-tecnologías)
- [Prerrequisitos](#-prerrequisitos)
- [Instalación y Ejecución](#-instalación-y-ejecución)
- [Uso del Dashboard](#-uso-del-dashboard)
- [Estrategia de Migración](#-estrategia-de-migración)
- [API Reference](#-api-reference)
- [Estructura del Proyecto](#-estructura-del-proyecto)
- [Validación de Integridad](#-validación-de-integridad)
- [Credenciales](#-credenciales)
- [Troubleshooting](#-troubleshooting)
- [Autores](#-autores)

---

## 🏗 Arquitectura

El sistema se compone de **3 contenedores Docker** orquestados con Docker Compose:

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                        │
│                  (migration_network)                     │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  SQL Server   │  │    Core      │  │   MongoDB    │  │
│  │  (Fuente)     │◄─┤  (FastAPI)   ├─►│  (Destino)   │  │
│  │              │  │              │  │              │  │
│  │ AdventureWorks│  │ Pandas ETL   │  │ adventureworks│  │
│  │ LT2022       │  │ Dashboard    │  │ _nosql       │  │
│  │              │  │              │  │              │  │
│  │ Puerto: 1433  │  │ Puerto: 8000 │  │ Puerto: 27017│  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

| Contenedor | Rol | Imagen Base |
|-----------|-----|-------------|
| `sqlserver_adventureworks` | BD relacional fuente | `mcr.microsoft.com/mssql/server:2022-latest` |
| `core_migration` | Motor ETL + API + Dashboard | `python:3.11-slim` |
| `mongodb_target` | BD NoSQL destino | `mongo:7.0` |

---

## 🛠 Tecnologías

| Componente | Tecnología | Versión |
|-----------|------------|---------|
| Base de datos fuente | Microsoft SQL Server | 2022 Express |
| Base de datos destino | MongoDB | 7.0 |
| Motor de transformación | Python + Pandas | 3.11 / 2.2 |
| API REST | FastAPI | 0.115 |
| Conector SQL Server | pyodbc + ODBC Driver 18 | 5.1 |
| Conector MongoDB | pymongo | 4.8 |
| Contenedores | Docker + Docker Compose | v3.8 |
| Dataset | AdventureWorksLT2022 | — |

---

## ✅ Prerrequisitos

1. **Docker Desktop** instalado y en ejecución
   - [Descargar Docker Desktop para Windows](https://www.docker.com/products/docker-desktop/)
2. Al menos **4 GB de RAM** disponibles para Docker
3. Puertos **1433**, **8000** y **27017** libres

---

## 🚀 Instalación y Ejecución

### 1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd Migracion_nosql
```

### 2. Construir y levantar los contenedores

```bash
docker-compose up --build -d
```

> ⏱ **Primera ejecución:** tarda ~5-10 minutos (descarga imágenes + restaura BD).

### 3. Verificar que todo esté corriendo

```bash
docker-compose ps
```

Los 3 contenedores deben mostrar estado `Up (healthy)`.

### 4. Verificar restauración de SQL Server

```bash
docker-compose logs sqlserver
```

Buscar el mensaje: `Base de datos restaurada exitosamente!`

### 5. Abrir el Dashboard

Navegar a: **http://localhost:8000**

### 6. Ejecutar la migración

En la pestaña **"🔄 Migración"** del dashboard, hacer click en **"🚀 Ejecutar Migración Completa"**.

### 7. Verificar integridad

En la pestaña **"⚖️ Comparación"**, hacer click en **"Comparar"** para validar conteos y ejecutar consultas equivalentes.

---

## 🖥 Uso del Dashboard

| Pestaña | Funcionalidad |
|---------|---------------|
| 📊 **Resumen** | Arquitectura, estrategia DDD, mapeo de dominios |
| 🗄️ **SQL Server** | Explorar tablas, ver datos, ejecutar queries SELECT |
| 🔄 **Migración** | Ejecutar/resetear migración, ver progreso y logs |
| 🍃 **MongoDB** | Explorar colecciones, vista tabla/JSON, queries con filtros |
| ⚖️ **Comparación** | Validar integridad: conteos + 5 consultas equivalentes lado a lado |

---

## 📐 Estrategia de Migración

### Análisis de Dominios (DDD)

La base de datos AdventureWorksLT se descompone en **3 bounded contexts**:

#### 1. Dominio: Catálogo de Productos

| Tablas SQL (5) | → | Colecciones MongoDB (2) | Patrón |
|---------------|---|------------------------|--------|
| `SalesLT.Product` | → | `products` | Embedding |
| `SalesLT.ProductCategory` | → | `product_categories` | Directo |
| `SalesLT.ProductModel` | → | (embebido en `products`) | Embedding |
| `SalesLT.ProductModelProductDescription` | → | (embebido en `products`) | Embedding |
| `SalesLT.ProductDescription` | → | (embebido en `products`) | Embedding |

**Justificación:** Categoría, modelo y descripciones se consultan siempre junto con el producto. Incrustarlos elimina JOINs y optimiza lecturas de catálogo.

```json
// Documento en products
{
  "ProductID": 680,
  "ProductName": "HL Road Frame - Black, 58",
  "ListPrice": 1431.50,
  "category": {
    "id": 18,
    "name": "Road Frames",
    "parent_name": "Components"
  },
  "model": {
    "id": 6,
    "name": "HL Road Frame",
    "descriptions": [
      { "Culture": "en", "Description": "Our lightest and best quality..." }
    ]
  }
}
```

#### 2. Dominio: Clientes

| Tablas SQL (3) | → | Colecciones MongoDB (2) | Patrón |
|---------------|---|------------------------|--------|
| `SalesLT.Customer` | → | `customers` | Embedding + Ref |
| `SalesLT.CustomerAddress` | → | (embebido en `customers`) | Embedding |
| `SalesLT.Address` | → | `addresses` | Referencing |

**Justificación:** Las direcciones se incrustan en el cliente (acceso rápido) Y se mantienen como colección independiente para consultas geográficas.

#### 3. Dominio: Ventas

| Tablas SQL (2) | → | Colecciones MongoDB (1) | Patrón |
|---------------|---|------------------------|--------|
| `SalesLT.SalesOrderHeader` | → | `sales_orders` | Embedding + Denorm |
| `SalesLT.SalesOrderDetail` | → | (embebido en `sales_orders`) | Embedding |

**Justificación:** Una orden siempre se lee con sus detalles. Se denormalizan nombre de cliente y producto para evitar lookups.

### Patrones Aplicados

| Patrón | Descripción | Ejemplo |
|--------|-------------|---------|
| **Embedding** | Datos 1:N como subdocumentos | Detalles de orden dentro de la orden |
| **Referencing** | IDs como referencia entre colecciones | `addresses` como colección separada |
| **Denormalization** | Copiar campos frecuentes | Nombre del cliente en `sales_orders` |

### Índices Creados

```javascript
// Productos
db.products.createIndex({ "ProductID": 1 }, { unique: true })
db.products.createIndex({ "category.name": 1 })
db.products.createIndex({ "ListPrice": -1 })

// Clientes
db.customers.createIndex({ "CustomerID": 1 }, { unique: true })
db.customers.createIndex({ "EmailAddress": 1 })

// Órdenes
db.sales_orders.createIndex({ "SalesOrderID": 1 }, { unique: true })
db.sales_orders.createIndex({ "customer.id": 1 })
db.sales_orders.createIndex({ "OrderDate": 1 })
```

---

## 📡 API Reference

Base URL: `http://localhost:8000`

### SQL Server

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/sql/tables` | Lista todas las tablas con conteo |
| GET | `/api/sql/table/{schema}/{table}?limit=50` | Datos de una tabla |
| GET | `/api/sql/schema/{schema}/{table}` | Esquema y FK de una tabla |
| GET | `/api/sql/query?q=SELECT...` | Ejecutar consulta SELECT |
| GET | `/api/sql/relationships` | Todas las FK de la BD |

### MongoDB

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/mongo/collections` | Lista colecciones con conteo |
| GET | `/api/mongo/collection/{name}?limit=50` | Documentos de una colección |
| GET | `/api/mongo/collection/{name}/schema` | Esquema inferido |
| GET | `/api/mongo/query?collection=...&filter_json={}` | Consulta con filtro |

### Migración

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/migration/execute` | Ejecutar migración completa |
| POST | `/api/migration/reset` | Limpiar MongoDB |
| GET | `/api/migration/status` | Estado de la migración |
| GET | `/api/migration/mapping` | Mapeo de tablas → colecciones |

### Comparación

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/compare/summary` | Conteo SQL vs MongoDB |
| GET | `/api/compare/products` | Top 10 productos caros |
| GET | `/api/compare/customers` | Clientes con más direcciones |
| GET | `/api/compare/sales` | Ventas por cliente |
| GET | `/api/compare/orders-detail` | Detalle de una orden |
| GET | `/api/compare/product-by-category` | Productos por categoría |

### Documentación interactiva (Swagger)

Disponible en: **http://localhost:8000/docs**

---

## 📁 Estructura del Proyecto

```
Migracion_nosql/
├── docker-compose.yml              # Orquestación de servicios
├── .env.example                    # Variables de entorno de ejemplo
├── .gitignore
├── README.md                       # Esta documentación
│
├── sqlserver/                      # Contenedor 1: SQL Server
│   ├── Dockerfile                  # Imagen con AdventureWorksLT
│   ├── setup.sh                    # Script de inicio + restauración
│   └── restore-db.sql              # Comando RESTORE DATABASE
│
└── core/                           # Contenedor 2: FastAPI Core
    ├── Dockerfile                  # Python 3.11 + ODBC drivers
    ├── requirements.txt            # Dependencias Python
    └── app/
        ├── __init__.py
        ├── main.py                 # Punto de entrada FastAPI
        ├── database.py             # Conexiones SQL Server + MongoDB
        ├── routers/
        │   ├── __init__.py
        │   ├── sql_router.py       # Endpoints SQL Server
        │   ├── mongo_router.py     # Endpoints MongoDB
        │   ├── migration_router.py # Lógica de migración (Pandas)
        │   └── compare_router.py   # Validación de integridad
        ├── templates/
        │   └── dashboard.html      # Dashboard web
        └── static/
            ├── styles.css          # Estilos del dashboard
            └── app.js              # Lógica frontend
```

---

## ✔️ Validación de Integridad

Después de la migración, el sistema valida:

1. **Conteo de registros:** cada tabla SQL debe tener el mismo número de documentos en MongoDB
2. **Consultas equivalentes:** 5 consultas se ejecutan en ambas bases y se comparan resultados:
   - Top 10 productos más caros (con categoría)
   - Clientes con más direcciones
   - Total de ventas por cliente
   - Detalle completo de una orden
   - Productos agrupados por categoría (con estadísticas de precio)

---

## 🔐 Credenciales

| Servicio | Usuario | Contraseña |
|----------|---------|------------|
| SQL Server | `sa` | `AdventureWorks2024!` |
| MongoDB | `admin` | `MongoAdmin2024!` |

---

## 🔧 Troubleshooting

| Problema | Solución |
|----------|---------|
| SQL Server no inicia | Verificar que Docker tiene ≥4 GB RAM asignados |
| "Login failed for user 'sa'" | Esperar ~30s más y reintentar; SQL Server aún está iniciando |
| Puerto 1433 ocupado | Cerrar SQL Server local o cambiar puerto en `docker-compose.yml` |
| Migración falla | Verificar que SQL Server muestra `healthy` con `docker-compose ps` |
| Dashboard no carga | Verificar que el contenedor `core_migration` está corriendo |

### Comandos útiles

```bash
# Ver logs en tiempo real
docker-compose logs -f

# Reiniciar un servicio específico
docker-compose restart core

# Reconstruir todo desde cero
docker-compose down -v && docker-compose up --build -d

# Conectarse a SQL Server desde el contenedor
docker exec -it sqlserver_adventureworks /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "AdventureWorks2024!" -C

# Conectarse a MongoDB desde el contenedor
docker exec -it mongodb_target mongosh -u admin -p "MongoAdmin2024!"
```

---

## 🔄 Patrón Saga (Transacciones Distribuidas)

La migración implementa el **patrón Saga de Orquestación** donde FastAPI actúa como coordinador central:

```
Saga Paso 1 → Categorías     ✅ → Registrar acción compensatoria
Saga Paso 2 → Productos      ✅ → Registrar acción compensatoria
Saga Paso 3 → Clientes       ❌ → FALLO!
                                  ↩️ Rollback: Eliminar Productos
                                  ↩️ Rollback: Eliminar Categorías
                                  ✅ MongoDB en estado consistente
```

- Cada paso es una **transacción local** en MongoDB
- Si un paso falla, se ejecutan **acciones compensatorias** en orden inverso
- El `SagaOrchestrator` registra cada paso y su colección asociada
- El dashboard muestra el **Saga Log** con todos los pasos y rollbacks

### Endpoints de Saga

| Endpoint | Descripción |
|----------|-------------|
| `POST /api/migration/execute` | Ejecuta migración con Saga |
| `GET /api/migration/saga-log` | Log detallado de la Saga |
| `POST /api/migration/reset` | Reset completo (rollback manual) |

---

## 🏗️ Cluster MongoDB (Réplicas + Sharding)

El archivo `docker-compose.cluster.yml` despliega un **entorno de producción simulado**:

```
┌──────────────────────────────────────────────────┐
│            Mongos Router (:27017)                │
│         Punto de entrada al cluster              │
└─────────────────────┬────────────────────────────┘
                      │
         ┌────────────┼────────────────┐
         │      Config Server RS       │
         │      configsvr1:27019       │
         └────────────┼────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    │          Shard 1 Replica Set      │
    │  ┌──────────┬──────────┬────────┐ │
    │  │ Primary  │Secondary1│Secondary2│
    │  │  :27018  │  :27018  │ :27018 │ │
    │  └──────────┴──────────┴────────┘ │
    └───────────────────────────────────┘
```

### Ejecutar el cluster

```bash
# Detener el entorno de desarrollo si está corriendo
docker-compose down

# Levantar el cluster de producción
docker-compose -f docker-compose.cluster.yml up --build -d

# Verificar que el cluster se inicializó
docker logs cluster_init

# Abrir dashboard
# http://localhost:8000
```

### Shard Keys configuradas

| Colección | Shard Key | Justificación |
|-----------|-----------|---------------|
| `sales_orders` | `customer.id` | Distribuye órdenes por cliente |
| `customers` | `CustomerID` | Distribuye clientes uniformemente |

### Verificar sharding

```bash
docker exec -it mongos1 mongosh --eval "sh.status()"
```

---

## 👥 Autores

- **[Tu nombre]** — Bases de Datos Masivas, Séptimo Semestre

---

## 📄 Licencia

Proyecto académico. Base de datos AdventureWorks es propiedad de Microsoft y se usa bajo su licencia de ejemplo.
