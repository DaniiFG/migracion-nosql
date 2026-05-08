# Hoja de Ruta Técnica: Migración a MongoDB Distribuido

**Proyecto:** De Monolito Relacional a MongoDB  
**Fecha:** Mayo 2026  
**Estado:** Validado en entorno simulado

---

## Fase 1 — Evaluación y Análisis

**Objetivo:** Delimitar el alcance y validar la viabilidad de la migración.

| Actividad | Entregable |
|-----------|-----------|
| Inventario de tablas, registros y relaciones FK | Mapa relacional completo |
| Identificar patrones de acceso (queries más frecuentes) | Lista de queries críticas |
| Clasificar tablas por dominio de negocio (DDD) | Bounded contexts definidos |
| Evaluar volumen de datos y tasa de crecimiento | Proyección de capacidad |
| Definir criterios de éxito de la migración | Checklist de validación |

**Riesgos:**
- Tablas con relaciones circulares o M:N complejas
- Datos binarios grandes (imágenes, blobs)
- Dependencias externas a la BD (stored procedures, triggers)

**Gate de salida:** Bounded contexts aprobados, decisión de patrones por dominio documentada.

---

## Fase 2 — Diseño del Modelo NoSQL

**Objetivo:** Definir el esquema MongoDB optimizado para los patrones de acceso identificados.

| Actividad | Entregable |
|-----------|-----------|
| Definir colecciones y estructura de documentos | Esquemas JSON de cada colección |
| Seleccionar patrón por relación (embed vs reference) | Tabla de decisiones documentada |
| Diseñar campos denormalizados | Lista de campos duplicados con justificación |
| Definir índices por colección | Plan de indexación |
| Seleccionar shard keys (si aplica) | Shard keys con análisis de cardinalidad |

**Criterios de decisión embed vs reference:**

| Criterio | Embedding | Referencing |
|----------|-----------|-------------|
| Cardinalidad | 1:pocos (< 100) | 1:muchos (> 100) |
| Acceso | Siempre juntos | Independiente |
| Actualización | Infrecuente | Frecuente |
| Tamaño | < 16 MB por documento | Sin límite |

**Gate de salida:** Blueprint de migración validado por el equipo.

---

## Fase 3 — Implementación del Pipeline ETL

**Objetivo:** Construir el motor de transformación con validación integrada.

| Actividad | Entregable |
|-----------|-----------|
| Implementar conectores SQL Server y MongoDB | Módulo `database.py` |
| Desarrollar transformaciones con Pandas por dominio | Módulo `migration_router.py` |
| Implementar patrón Saga con acciones compensatorias | Clase `SagaOrchestrator` |
| Manejar tipos de datos (datetime, binary, NULL) | Función `clean_dataframe()` |
| Agregar logging de cada paso | Saga log con timestamps |

**Stack tecnológico:**

| Componente | Tecnología |
|-----------|------------|
| Orquestador | FastAPI (Python 3.11) |
| Transformación | Pandas |
| Conector SQL | pyodbc + ODBC Driver 18 |
| Conector Mongo | pymongo |
| Contenerización | Docker + Docker Compose |

**Gate de salida:** Migración ejecuta end-to-end sin errores en entorno de desarrollo.

---

## Fase 4 — Validación de Integridad

**Objetivo:** Garantizar que los datos migrados son correctos y completos.

### Pruebas de sincronización

| Prueba | Método | Resultado esperado |
|--------|--------|-------------------|
| Conteo por entidad | `COUNT(*)` vs `countDocuments()` | Igualdad exacta |
| Verificación de campos clave | Query equivalente lado a lado | Mismos valores |
| Datos embebidos | Contar subdocumentos vs filas hijas | Igualdad exacta |
| Agregaciones | `GROUP BY` vs `$group` | Mismos totales |
| Caso borde: NULLs | Verificar campos opcionales | NULL → `null` |

### Estrategia de rollback

| Escenario | Acción |
|-----------|--------|
| Fallo en paso N de la Saga | Compensación automática: eliminar colecciones de pasos 1 a N-1 |
| Datos incorrectos post-migración | Reset completo + re-ejecución |
| Fallo de conectividad a mitad | Saga detecta excepción → rollback → estado consistente |

**Gate de salida:** Todas las pruebas de sincronización pasan al 100%.

---

## Fase 5 — Despliegue del Cluster

**Objetivo:** Configurar MongoDB con alta disponibilidad y distribución de datos.

| Actividad | Entregable |
|-----------|-----------|
| Configurar Replica Set (3 nodos) | Alta disponibilidad |
| Configurar Config Server | Metadata del sharding |
| Configurar Mongos Router | Punto de entrada unificado |
| Habilitar sharding en colecciones críticas | Distribución horizontal |
| Ejecutar migración contra el cluster | Datos distribuidos |
| Verificar distribución con `sh.status()` | Chunks balanceados |

### Componentes del cluster

| Componente | Nodos | Función |
|-----------|-------|---------|
| Config Server RS | 1 | Almacena metadata de shards y chunks |
| Shard RS | 3 (primary + 2 secondary) | Almacena datos con replicación |
| Mongos | 1 | Rutea queries al shard correcto |

### Pruebas de resiliencia

| Prueba | Procedimiento | Resultado esperado |
|--------|--------------|-------------------|
| Failover de primary | Detener nodo primary del shard | Secondary se promueve automáticamente |
| Lectura durante failover | Consultar durante promoción | Datos disponibles desde secondaries |
| Verificar replicación | Insertar en primary, leer en secondary | Datos consistentes |

**Gate de salida:** Cluster operativo, failover verificado, datos distribuidos y replicados.

---

## Fase 6 — Operación y Monitoreo

**Objetivo:** Asegurar la operabilidad continua post-migración.

| Actividad | Herramienta |
|-----------|------------|
| Monitoreo de replica set | `rs.status()` |
| Monitoreo de sharding | `sh.status()` |
| Verificar balanceo de chunks | `db.printShardingStatus()` |
| Logs de operación | Docker logs |
| Re-ejecución de validación | Endpoints `/api/compare/*` |

### Comandos de operación

```bash
# Estado del replica set
docker exec -it shard1-primary mongosh --port 27018 --eval "rs.status()"

# Estado del sharding
docker exec -it mongos1 mongosh --eval "sh.status()"

# Verificar distribución de datos
docker exec -it mongos1 mongosh --eval "db.getSiblingDB('adventureworks_nosql').sales_orders.getShardDistribution()"
```

---

## Resumen de Fases

| Fase | Duración estimada | Dependencia |
|------|-------------------|------------|
| 1. Evaluación | 1-2 días | — |
| 2. Diseño NoSQL | 1-2 días | Fase 1 |
| 3. Pipeline ETL | 2-3 días | Fase 2 |
| 4. Validación | 1 día | Fase 3 |
| 5. Cluster | 1 día | Fase 4 |
| 6. Operación | Continuo | Fase 5 |

---

## Checklist Final

- [ ] Modelo relacional analizado y documentado
- [ ] Bounded contexts definidos (Productos, Clientes, Ventas)
- [ ] Patrones de migración seleccionados (embed, reference, denorm)
- [ ] Pipeline ETL funcional con Saga y rollback
- [ ] Pruebas de sincronización ejecutadas (100% match)
- [ ] Cluster con réplicas desplegado
- [ ] Sharding configurado y verificado
- [ ] Failover probado
- [ ] Documentación completa (Blueprint + Hoja de Ruta + README)
