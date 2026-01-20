<<<<<<< HEAD
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Path
from fastapi.responses import JSONResponse
import logging

from ..models.graphdb import (
    GraphDBConfigCreate, GraphDBConfigUpdate, GraphDBConfigResponse,
    SPARQLQueryRequest, SPARQLQueryResponse, GraphDBTestResponse
)
from ..services.graphdb_service import graphdb_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graphdb", tags=["graphdb"])


@router.post("/configs", response_model=GraphDBConfigResponse)
async def create_graphdb_config(
    config_data: GraphDBConfigCreate,
    created_by: str = Query(..., description="User creating the configuration")
):
    """Create a new GraphDB configuration"""
    try:
        config = await graphdb_service.create_config(config_data, created_by)
        logger.info(f"Created GraphDB configuration: {config.name}")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating GraphDB configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to create GraphDB configuration")


@router.get("/configs", response_model=List[GraphDBConfigResponse])
async def get_graphdb_configs(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return")
):
    """Get all GraphDB configurations"""
    try:
        configs = await graphdb_service.get_configs(skip=skip, limit=limit)
        return configs
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting GraphDB configurations: {e}")
        raise HTTPException(status_code=500, detail="Failed to get GraphDB configurations")


@router.get("/configs/{config_id}", response_model=GraphDBConfigResponse)
async def get_graphdb_config(
    config_id: str = Path(..., description="GraphDB configuration ID")
):
    """Get GraphDB configuration by ID"""
    try:
        config = await graphdb_service.get_config(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="GraphDB configuration not found")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting GraphDB configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to get GraphDB configuration")


@router.put("/configs/{config_id}", response_model=GraphDBConfigResponse)
async def update_graphdb_config(
    config_id: str = Path(..., description="GraphDB configuration ID"),
    update_data: GraphDBConfigUpdate = None
):
    """Update GraphDB configuration"""
    try:
        config = await graphdb_service.update_config(config_id, update_data)
        if not config:
            raise HTTPException(status_code=404, detail="GraphDB configuration not found")
        logger.info(f"Updated GraphDB configuration: {config.name}")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating GraphDB configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to update GraphDB configuration")


@router.delete("/configs/{config_id}")
async def delete_graphdb_config(
    config_id: str = Path(..., description="GraphDB configuration ID")
):
    """Delete GraphDB configuration"""
    try:
        deleted = await graphdb_service.delete_config(config_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="GraphDB configuration not found")
        logger.info(f"Deleted GraphDB configuration: {config_id}")
        return {"message": f"GraphDB configuration {config_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting GraphDB configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete GraphDB configuration")


@router.post("/configs/{config_id}/test", response_model=GraphDBTestResponse)
async def test_graphdb_connection(
    config_id: str = Path(..., description="GraphDB configuration ID")
):
    """Test GraphDB connection and endpoints"""
    try:
        test_result = await graphdb_service.test_connection(config_id)
        logger.info(f"GraphDB connection test completed for config {config_id}: {test_result.success}")
        return test_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing GraphDB connection: {e}")
        raise HTTPException(status_code=500, detail="Failed to test GraphDB connection")


@router.post("/query", response_model=SPARQLQueryResponse)
async def execute_sparql_query(query_request: SPARQLQueryRequest):
    """Execute SPARQL query against GraphDB"""
    try:
        result = await graphdb_service.execute_sparql_query(query_request)
        logger.info(f"SPARQL query executed: {query_request.query_type} on config {query_request.config_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing SPARQL query: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute SPARQL query")


@router.get("/configs/{config_id}/query-examples")
async def get_query_examples(
    config_id: str = Path(..., description="GraphDB configuration ID")
):
    """Get example SPARQL queries for the GraphDB configuration"""
    try:
        config = await graphdb_service.get_config(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="GraphDB configuration not found")
        
        examples = {
            "select_examples": [
                {
                    "name": "Get all triples",
                    "query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10",
                    "description": "Retrieve all triples in the repository (limited to 10)"
                },
                {
                    "name": "Count all triples",
                    "query": "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }",
                    "description": "Count the total number of triples in the repository"
                },
                {
                    "name": "Get all subjects",
                    "query": "SELECT DISTINCT ?s WHERE { ?s ?p ?o } LIMIT 20",
                    "description": "Get all unique subjects in the repository"
                }
            ],
            "update_examples": [
                {
                    "name": "Insert a triple",
                    "query": "INSERT DATA { <http://example.org/subject> <http://example.org/predicate> <http://example.org/object> }",
                    "description": "Insert a single triple into the repository"
                },
                {
                    "name": "Delete a triple",
                    "query": "DELETE DATA { <http://example.org/subject> <http://example.org/predicate> <http://example.org/object> }",
                    "description": "Delete a specific triple from the repository"
                },
                {
                    "name": "Clear all data",
                    "query": "DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
                    "description": "Delete all triples from the repository (use with caution!)"
                }
            ],
            "repository_info": {
                "name": config.repository_name,
                "select_endpoint": config.select_endpoint,
                "update_endpoint": config.update_endpoint
            }
        }
        
        return examples
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting query examples: {e}")
        raise HTTPException(status_code=500, detail="Failed to get query examples")


@router.get("/health")
async def graphdb_health_check():
    """Health check for GraphDB service"""
    try:
        # Check if service is initialized
        if graphdb_service.collection is None:
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "message": "GraphDB service not initialized"}
            )
        
        # Try to get collection stats
        try:
            stats = await graphdb_service.collection.count_documents({})
        except Exception as e:
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "message": f"Database connection error: {str(e)}"}
            )
        
        return {
            "status": "healthy",
            "message": "GraphDB service is operational",
            "total_configurations": stats
        }
        
    except Exception as e:
        logger.error(f"GraphDB health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "message": f"GraphDB service error: {str(e)}"}
        )
=======
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Path
from fastapi.responses import JSONResponse
import logging

from ..models.graphdb import (
    GraphDBConfigCreate, GraphDBConfigUpdate, GraphDBConfigResponse,
    SPARQLQueryRequest, SPARQLQueryResponse, GraphDBTestResponse
)
from ..services.graphdb_service import graphdb_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graphdb", tags=["graphdb"])


@router.post("/configs", response_model=GraphDBConfigResponse)
async def create_graphdb_config(
    config_data: GraphDBConfigCreate,
    created_by: str = Query(..., description="User creating the configuration")
):
    """Create a new GraphDB configuration"""
    try:
        config = await graphdb_service.create_config(config_data, created_by)
        logger.info(f"Created GraphDB configuration: {config.name}")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating GraphDB configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to create GraphDB configuration")


@router.get("/configs", response_model=List[GraphDBConfigResponse])
async def get_graphdb_configs(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return")
):
    """Get all GraphDB configurations"""
    try:
        configs = await graphdb_service.get_configs(skip=skip, limit=limit)
        return configs
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting GraphDB configurations: {e}")
        raise HTTPException(status_code=500, detail="Failed to get GraphDB configurations")


@router.get("/configs/{config_id}", response_model=GraphDBConfigResponse)
async def get_graphdb_config(
    config_id: str = Path(..., description="GraphDB configuration ID")
):
    """Get GraphDB configuration by ID"""
    try:
        config = await graphdb_service.get_config(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="GraphDB configuration not found")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting GraphDB configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to get GraphDB configuration")


@router.put("/configs/{config_id}", response_model=GraphDBConfigResponse)
async def update_graphdb_config(
    config_id: str = Path(..., description="GraphDB configuration ID"),
    update_data: GraphDBConfigUpdate = None
):
    """Update GraphDB configuration"""
    try:
        config = await graphdb_service.update_config(config_id, update_data)
        if not config:
            raise HTTPException(status_code=404, detail="GraphDB configuration not found")
        logger.info(f"Updated GraphDB configuration: {config.name}")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating GraphDB configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to update GraphDB configuration")


@router.delete("/configs/{config_id}")
async def delete_graphdb_config(
    config_id: str = Path(..., description="GraphDB configuration ID")
):
    """Delete GraphDB configuration"""
    try:
        deleted = await graphdb_service.delete_config(config_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="GraphDB configuration not found")
        logger.info(f"Deleted GraphDB configuration: {config_id}")
        return {"message": f"GraphDB configuration {config_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting GraphDB configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete GraphDB configuration")


@router.post("/configs/{config_id}/test", response_model=GraphDBTestResponse)
async def test_graphdb_connection(
    config_id: str = Path(..., description="GraphDB configuration ID")
):
    """Test GraphDB connection and endpoints"""
    try:
        test_result = await graphdb_service.test_connection(config_id)
        logger.info(f"GraphDB connection test completed for config {config_id}: {test_result.success}")
        return test_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing GraphDB connection: {e}")
        raise HTTPException(status_code=500, detail="Failed to test GraphDB connection")


@router.post("/query", response_model=SPARQLQueryResponse)
async def execute_sparql_query(query_request: SPARQLQueryRequest):
    """Execute SPARQL query against GraphDB"""
    try:
        result = await graphdb_service.execute_sparql_query(query_request)
        logger.info(f"SPARQL query executed: {query_request.query_type} on config {query_request.config_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing SPARQL query: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute SPARQL query")


@router.get("/configs/{config_id}/query-examples")
async def get_query_examples(
    config_id: str = Path(..., description="GraphDB configuration ID")
):
    """Get example SPARQL queries for the GraphDB configuration"""
    try:
        config = await graphdb_service.get_config(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="GraphDB configuration not found")
        
        examples = {
            "select_examples": [
                {
                    "name": "Get all triples",
                    "query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10",
                    "description": "Retrieve all triples in the repository (limited to 10)"
                },
                {
                    "name": "Count all triples",
                    "query": "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }",
                    "description": "Count the total number of triples in the repository"
                },
                {
                    "name": "Get all subjects",
                    "query": "SELECT DISTINCT ?s WHERE { ?s ?p ?o } LIMIT 20",
                    "description": "Get all unique subjects in the repository"
                }
            ],
            "update_examples": [
                {
                    "name": "Insert a triple",
                    "query": "INSERT DATA { <http://example.org/subject> <http://example.org/predicate> <http://example.org/object> }",
                    "description": "Insert a single triple into the repository"
                },
                {
                    "name": "Delete a triple",
                    "query": "DELETE DATA { <http://example.org/subject> <http://example.org/predicate> <http://example.org/object> }",
                    "description": "Delete a specific triple from the repository"
                },
                {
                    "name": "Clear all data",
                    "query": "DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
                    "description": "Delete all triples from the repository (use with caution!)"
                }
            ],
            "repository_info": {
                "name": config.repository_name,
                "select_endpoint": config.select_endpoint,
                "update_endpoint": config.update_endpoint
            }
        }
        
        return examples
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting query examples: {e}")
        raise HTTPException(status_code=500, detail="Failed to get query examples")


@router.get("/health")
async def graphdb_health_check():
    """Health check for GraphDB service"""
    try:
        # Check if service is initialized
        if graphdb_service.collection is None:
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "message": "GraphDB service not initialized"}
            )
        
        # Try to get collection stats
        try:
            stats = await graphdb_service.collection.count_documents({})
        except Exception as e:
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "message": f"Database connection error: {str(e)}"}
            )
        
        return {
            "status": "healthy",
            "message": "GraphDB service is operational",
            "total_configurations": stats
        }
        
    except Exception as e:
        logger.error(f"GraphDB health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "message": f"GraphDB service error: {str(e)}"}
        )
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
