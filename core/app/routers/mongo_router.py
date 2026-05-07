"""
Router para consultar datos de MongoDB (base destino).
Permite listar colecciones, ver documentos y ejecutar consultas.
"""

from fastapi import APIRouter, HTTPException, Query
from app.database import get_mongo_db
import json
from bson import json_util, ObjectId

router = APIRouter()


def serialize_mongo(doc):
    """Serializa un documento MongoDB para JSON."""
    if isinstance(doc, dict):
        return {k: serialize_mongo(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_mongo(item) for item in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    elif hasattr(doc, 'isoformat'):
        return doc.isoformat()
    elif isinstance(doc, bytes):
        return str(doc)
    return doc


@router.get("/collections")
async def list_collections():
    """Lista todas las colecciones en MongoDB con conteo de documentos."""
    try:
        db = get_mongo_db()
        collections = db.list_collection_names()
        
        result = []
        total_docs = 0
        for col_name in sorted(collections):
            count = db[col_name].count_documents({})
            total_docs += count
            result.append({
                "collection": col_name,
                "document_count": count
            })
        
        return {
            "total_collections": len(result),
            "total_documents": total_docs,
            "collections": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al conectar con MongoDB: {str(e)}")


@router.get("/collection/{collection_name}")
async def get_collection_data(
    collection_name: str,
    limit: int = Query(default=50, le=1000),
    skip: int = Query(default=0, ge=0)
):
    """Obtiene documentos de una colección MongoDB."""
    try:
        db = get_mongo_db()
        
        if collection_name not in db.list_collection_names():
            raise HTTPException(status_code=404, detail=f"Colección '{collection_name}' no encontrada")
        
        collection = db[collection_name]
        total = collection.count_documents({})
        
        docs = list(collection.find().skip(skip).limit(limit))
        docs_serialized = [serialize_mongo(doc) for doc in docs]
        
        # Obtener campos del primer documento
        fields = list(docs_serialized[0].keys()) if docs_serialized else []
        
        return {
            "collection": collection_name,
            "total_documents": total,
            "skip": skip,
            "limit": limit,
            "fields": fields,
            "data": docs_serialized
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener datos: {str(e)}")


@router.get("/collection/{collection_name}/schema")
async def get_collection_schema(collection_name: str):
    """Analiza el esquema de una colección MongoDB (inferido de documentos)."""
    try:
        db = get_mongo_db()
        
        if collection_name not in db.list_collection_names():
            raise HTTPException(status_code=404, detail=f"Colección '{collection_name}' no encontrada")
        
        collection = db[collection_name]
        
        # Analizar primeros 100 documentos para inferir esquema
        docs = list(collection.find().limit(100))
        
        field_info = {}
        for doc in docs:
            _analyze_fields(doc, field_info, "")
        
        return {
            "collection": collection_name,
            "sample_size": len(docs),
            "fields": field_info
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al analizar esquema: {str(e)}")


def _analyze_fields(doc, field_info, prefix):
    """Analiza recursivamente los campos de un documento."""
    for key, value in doc.items():
        full_key = f"{prefix}.{key}" if prefix else key
        
        if full_key not in field_info:
            field_info[full_key] = {
                "types": set(),
                "count": 0,
                "is_array": False,
                "is_embedded": False
            }
        
        field_info[full_key]["count"] += 1
        field_info[full_key]["types"].add(type(value).__name__)
        
        if isinstance(value, list):
            field_info[full_key]["is_array"] = True
            if value and isinstance(value[0], dict):
                field_info[full_key]["is_embedded"] = True
                for item in value[:5]:
                    _analyze_fields(item, field_info, full_key)
        elif isinstance(value, dict):
            field_info[full_key]["is_embedded"] = True
            _analyze_fields(value, field_info, full_key)
    
    # Convertir sets a listas para serialización
    for key in field_info:
        if isinstance(field_info[key]["types"], set):
            field_info[key]["types"] = list(field_info[key]["types"])


@router.get("/query")
async def execute_mongo_query(
    collection: str = Query(..., description="Nombre de la colección"),
    filter_json: str = Query(default="{}", description="Filtro MongoDB en JSON"),
    limit: int = Query(default=50, le=1000)
):
    """Ejecuta una consulta en MongoDB con filtro JSON."""
    try:
        db = get_mongo_db()
        
        if collection not in db.list_collection_names():
            raise HTTPException(status_code=404, detail=f"Colección '{collection}' no encontrada")
        
        filter_dict = json.loads(filter_json)
        
        col = db[collection]
        total = col.count_documents(filter_dict)
        docs = list(col.find(filter_dict).limit(limit))
        docs_serialized = [serialize_mongo(doc) for doc in docs]
        
        return {
            "collection": collection,
            "filter": filter_dict,
            "total_matches": total,
            "returned": len(docs_serialized),
            "data": docs_serialized
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON de filtro inválido")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en consulta MongoDB: {str(e)}")
