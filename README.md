# Migración de Monolito Relacional a MongoDB Distribuido

**Taller Práctico** — Bases de Datos Masivas | Séptimo Semestre

Proyecto que implementa la migración de una base de datos monolítica relacional (SQL Server – AdventureWorksLT) hacia MongoDB, aplicando Domain-Driven Design, patrones de embedding/referencing, patrón Saga con rollback, y despliegue de cluster con réplicas y sharding.

---

## Tabla de Contenidos

- [Arquitectura](#arquitectura)
- [Tecnologías](#tecnologías)
- [Prerrequisitos](#prerrequisitos)
- [Instalación y Ejecución](#instalación-y-ejecución)
- [Uso del Dashboard](#uso-del-dashboard)
- [Estrategia de Migración (DDD)](#estrategia-de-migración-ddd)
- [Patrón Saga y Rollback](#patrón-saga-y-rollback)
- [Cluster MongoDB (Réplicas + Sharding)](#cluster-mongodb-réplicas--sharding)
- [API Reference](#api-reference)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Validación de Integridad](#validación-de-integridad)
- [Documentación Complementaria](#documentación-complementaria)
- [Credenciales](#credenciales)
- [Troubleshooting](#troubleshooting)
- [Autores](#autores)

---

## Arquitectura

El sistema se compone de **3 contenedores Docker** orquestados con Docker Compose:

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                       │
│                  (migration_network)                    │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  SQL Server   │  │    Core      │  │   MongoDB    │  │
│  │  (Fuente)     │◄─┤  (FastAPI)   ├─►│  (Destino)   │  │
│  │              │  │              │  │              │  │
│  │ AdventureWorks│  │ Pandas ETL   │  │ adventureworks│  │
│  │ LT2022       │  │ Saga Engine  │  │ _nosql       │  │
│  │              │  │ Dashboard    │  │              │  │
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

## Tecnologías

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

## Prerrequisitos

1. **Docker Desktop** instalado y en ejecución
2. Al menos **4 GB de RAM** disponibles para Docker
3. Puertos **1433**, **8000** y **27017** libres
4. Conexión a internet (primera ejecución)

---

## Instalación y Ejecución

### 1. Clonar el repositorio

```bash
git clone https://github.com/DaniiFG/migracion-nosql.git
cd migracion-nosql
```

### 2. Construir y levantar los contenedores

```bash
docker-compose up --build -d
```

> La primera ejecución tarda ~5-10 minutos (descarga de imágenes y restauración de la BD).

### 3. Verificar estado

```bash
docker-compose ps
```

Los 3 contenedores deben mostrar estado `Up (healthy)`.

### 4. Verificar restauración de SQL Server

```bash
docker-compose logs sqlserver
```

Esperar el mensaje: `Base de datos restaurada exitosamente!`

### 5. Acceder al Dashboard

Abrir en el navegador: **http://localhost:8000**

### 6. Ejecutar la migración

En la pestaña **Migración** del dashboard, presionar **Ejecutar Migración Completa**.

### 7. Validar integridad

En la pestaña **Comparación**, presionar **Comparar** para verificar conteos y ejecutar consultas equivalentes.

---

## Uso del Dashboard

| Pestaña | Funcionalidad |
|---------|---------------|
| **Resumen** | Arquitectura, estrategia DDD, mapeo de dominios |
| **SQL Server** | Explorar tablas, ver datos, ejecutar queries SELECT |
| **Migración** | Ejecutar/resetear migración con Saga, ver progreso y logs de rollback |
| **MongoDB** | Explorar colecciones en vista tabla o JSON, consultas con filtros |
| **Comparación** | Validar integridad: conteos y 5 consultas equivalentes lado a lado |

Documentación interactiva (Swagger): **http://localhost:8000/docs**

---

## Estrategia de Migración (DDD)

La base de datos se descompone en 3 bounded contexts:

### Dominio: Catálogo de Productos

| Tablas SQL (5) | Colecciones MongoDB (2) | Patrón |
|---------------|------------------------|--------|
| Product, ProductCategory, ProductModel, ProductModelProductDescription, ProductDescription | `products`, `product_categories` | Embedding |

Categoría, modelo y descripciones se incrustan como subdocumentos dentro del producto.

### Dominio: Clientes

| Tablas SQL (3) | Colecciones MongoDB (2) | Patrón |
|---------------|------------------------|--------|
| Customer, CustomerAddress, Address | `customers`, `addresses` | Embedding + Referencing |

Direcciones embebidas en el cliente para acceso rápido; colección independiente para consultas geográficas.

### Dominio: Ventas

| Tablas SQL (2) | Colecciones MongoDB (1) | Patrón |
|---------------|------------------------|--------|
| SalesOrderHeader, SalesOrderDetail | `sales_orders` | Embedding + Denormalization |

Detalles de orden embebidos. Nombre de cliente y producto denormalizados para evitar lookups.

### Índices

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

## Patrón Saga y Rollback

La migración implementa el **patrón Saga de Orquestación** con FastAPI como coordinador central.

### Flujo de la Saga

```
Paso 1 → Migrar categorías      → Registrar acción compensatoria
Paso 2 → Migrar productos       → Registrar acción compensatoria
Paso 3 → Migrar clientes        → Registrar acción compensatoria
Paso 4 → Migrar direcciones     → Registrar acción compensatoria
Paso 5 → Migrar órdenes         → Registrar acción compensatoria
Paso 6 → Crear índices          → Registrar acción compensatoria
```

Si cualquier paso falla, se ejecutan las compensaciones en **orden inverso**, eliminando las colecciones ya creadas y dejando MongoDB en estado consistente.

### Estrategias de Rollback

| Estrategia | Descripción |
|-----------|-------------|
| Compensación automática | La Saga deshace pasos previos si uno falla |
| Reset manual | Endpoint `POST /api/migration/reset` elimina todas las colecciones |
| Visibilidad | Dashboard muestra Saga Log y Rollback Log en tiempo real |

### Endpoints de Saga

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/api/migration/execute` | POST | Ejecutar migración con Saga |
| `/api/migration/saga-log` | GET | Log detallado de pasos y rollbacks |
| `/api/migration/status` | GET | Estado actual de la migración |
| `/api/migration/reset` | POST | Reset completo de MongoDB |

---

## Cluster MongoDB (Réplicas + Sharding)

El archivo `docker-compose.cluster.yml` despliega un entorno de producción simulado.

### Componentes

| Componente | Nodos | Puerto | Función |
|-----------|-------|--------|---------|
| Config Server | 1 (replica set) | 27019 | Metadata del cluster |
| Shard 1 | 3 (primary + 2 secondary) | 27018 | Almacenamiento con replicación |
| Mongos Router | 1 | 27017 | Punto de entrada al cluster |

### Ejecución del Cluster

```bash
# Detener entorno de desarrollo
docker-compose down

# Levantar cluster de producción
docker-compose -f docker-compose.cluster.yml up --build -d

# Verificar inicialización
docker logs cluster_init

# Dashboard disponible en http://localhost:8000
```

### Shard Keys

| Colección | Shard Key | Justificación |
|-----------|-----------|---------------|
| `sales_orders` | `customer.id` | Distribución uniforme de órdenes por cliente |
| `customers` | `CustomerID` | Distribución uniforme de clientes |

### Verificar estado del cluster

```bash
docker exec -it mongos1 mongosh --eval "sh.status()"
```

---

## API Reference

Base URL: `http://localhost:8000`

### SQL Server

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/sql/tables` | Lista tablas con conteo |
| GET | `/api/sql/table/{schema}/{table}` | Datos de una tabla |
| GET | `/api/sql/schema/{schema}/{table}` | Esquema y FK |
| GET | `/api/sql/query?q=SELECT...` | Ejecutar consulta SELECT |
| GET | `/api/sql/relationships` | Todas las FK de la BD |

### MongoDB

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/mongo/collections` | Lista colecciones con conteo |
| GET | `/api/mongo/collection/{name}` | Documentos de una colección |
| GET | `/api/mongo/collection/{name}/schema` | Esquema inferido |
| GET | `/api/mongo/query?collection=...&filter_json={}` | Consulta con filtro |

### Migración

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/migration/execute` | Ejecutar migración (Saga) |
| POST | `/api/migration/reset` | Limpiar MongoDB |
| GET | `/api/migration/status` | Estado de la migración |
| GET | `/api/migration/saga-log` | Log de la Saga |
| GET | `/api/migration/mapping` | Mapeo de tablas a colecciones |

### Comparación

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/compare/summary` | Conteo SQL vs MongoDB |
| GET | `/api/compare/products` | Top 10 productos caros |
| GET | `/api/compare/customers` | Clientes con más direcciones |
| GET | `/api/compare/sales` | Ventas por cliente |
| GET | `/api/compare/orders-detail` | Detalle de una orden |
| GET | `/api/compare/product-by-category` | Productos por categoría |

---

## Estructura del Proyecto

```
Migracion_nosql/
├── docker-compose.yml              # Orquestación (desarrollo)
├── docker-compose.cluster.yml      # Orquestación (cluster producción)
├── .env.example                    # Variables de entorno
├── BLUEPRINT_MIGRACION.md          # Blueprint de migración validado
├── HOJA_DE_RUTA.md                 # Hoja de ruta técnica
├── README.md
│
├── sqlserver/
│   ├── Dockerfile                  # SQL Server + AdventureWorksLT
│   ├── setup.sh                    # Inicio + restauración automática
│   └── restore-db.sql              # RESTORE DATABASE
│
└── core/
    ├── Dockerfile                  # Python 3.11 + ODBC
    ├── requirements.txt
    └── app/
        ├── main.py                 # FastAPI app
        ├── database.py             # Conexiones SQL Server + MongoDB
        ├── routers/
        │   ├── sql_router.py       # Endpoints SQL Server
        │   ├── mongo_router.py     # Endpoints MongoDB
        │   ├── migration_router.py # Saga + transformación Pandas
        │   └── compare_router.py   # Validación de integridad
        ├── templates/
        │   └── dashboard.html
        └── static/
            ├── styles.css
            └── app.js
```

---

## Validación de Integridad

Después de la migración, el sistema ejecuta las siguientes validaciones:

| Validación | Método |
|-----------|--------|
| Conteo por entidad | `COUNT(*)` SQL vs `countDocuments()` MongoDB |
| Top 10 productos caros | Query equivalente en ambas bases |
| Clientes con direcciones | JOIN SQL vs subdocumento MongoDB |
| Ventas por cliente | `GROUP BY` SQL vs `$group` MongoDB |
| Detalle de orden | JOIN SQL vs documento embebido |
| Productos por categoría | Agregación en ambas bases |

---

## Documentación Complementaria

| Documento | Descripción |
|----------|-------------|
| `BLUEPRINT_MIGRACION.md` | Análisis relacional, bounded contexts, modelo MongoDB, indexación y patrones |
| `HOJA_DE_RUTA.md` | Plan de ejecución en 6 fases con gates de salida y checklist |

---

## Credenciales

| Servicio | Usuario | Contraseña |
|----------|---------|------------|
| SQL Server | `sa` | `AdventureWorks2024!` |
| MongoDB | `admin` | `MongoAdmin2024!` |

---

## Troubleshooting

| Problema | Solución |
|----------|---------|
| SQL Server no inicia | Verificar que Docker tiene al menos 4 GB de RAM |
| Login failed for user 'sa' | Esperar ~30s; SQL Server aún está iniciando |
| Puerto 1433 ocupado | Cerrar SQL Server local o cambiar puerto en docker-compose.yml |
| Migración falla | Verificar que SQL Server muestra `healthy` con `docker-compose ps` |
| Dashboard no carga | Verificar que el contenedor `core_migration` está corriendo |

### Comandos útiles

```bash
# Ver logs en tiempo real
docker-compose logs -f

# Reiniciar un servicio
docker-compose restart core

# Reconstruir desde cero
docker-compose down -v
docker-compose up --build -d

# Conectarse a SQL Server
docker exec -it sqlserver_adventureworks /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "AdventureWorks2024!" -C

# Conectarse a MongoDB
docker exec -it mongodb_target mongosh -u admin -p "MongoAdmin2024!"
```

---

## Autores

- Daniel García, Nicolas Gutierrez, Brayan Guerrero — Bases de Datos Masivas, Séptimo Semestre
