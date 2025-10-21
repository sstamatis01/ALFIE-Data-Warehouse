import asyncio
import aiohttp
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import HTTPException
from bson import ObjectId

from ..models.graphdb import (
    GraphDBConfig, GraphDBConfigCreate, GraphDBConfigUpdate, GraphDBConfigResponse,
    GraphDBStatus, SPARQLQueryRequest, SPARQLQueryResponse, GraphDBTestResponse
)
from ..core.database import get_database

logger = logging.getLogger(__name__)


class GraphDBService:
    """Service for managing GraphDB configurations and SPARQL queries"""
    
    def __init__(self):
        self.db = None
        self.collection = None

    async def initialize(self):
        """Initialize the GraphDB service"""
        self.db = get_database()
        self.collection = self.db.graphdb_configs

    async def create_config(self, config_data: GraphDBConfigCreate, created_by: str) -> GraphDBConfigResponse:
        """Create a new GraphDB configuration"""
        try:
            # Check if config with this name already exists
            existing_config = await self.collection.find_one({"name": config_data.name})
            if existing_config:
                raise HTTPException(
                    status_code=409,
                    detail=f"GraphDB configuration with name '{config_data.name}' already exists"
                )
            
            # Create configuration
            config = GraphDBConfig(
                **config_data.dict(),
                created_by=created_by
            )
            
            result = await self.collection.insert_one(config.dict(by_alias=True, exclude={'id'}))
            created_config = await self.collection.find_one({"_id": result.inserted_id})
            
            logger.info(f"Created GraphDB configuration: {config_data.name}")
            return self._to_response(created_config)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating GraphDB configuration: {e}")
            raise HTTPException(status_code=500, detail="Failed to create GraphDB configuration")

    async def get_config(self, config_id: str) -> Optional[GraphDBConfigResponse]:
        """Get GraphDB configuration by ID"""
        try:
            config = await self.collection.find_one({"_id": ObjectId(config_id)})
            if config:
                return self._to_response(config)
            return None
        except Exception as e:
            logger.error(f"Error getting GraphDB configuration: {e}")
            raise HTTPException(status_code=500, detail="Failed to get GraphDB configuration")

    async def get_configs(self, skip: int = 0, limit: int = 100) -> List[GraphDBConfigResponse]:
        """Get all GraphDB configurations"""
        try:
            cursor = self.collection.find().skip(skip).limit(limit).sort("created_at", -1)
            configs = await cursor.to_list(length=limit)
            return [self._to_response(config) for config in configs]
        except Exception as e:
            logger.error(f"Error getting GraphDB configurations: {e}")
            raise HTTPException(status_code=500, detail="Failed to get GraphDB configurations")

    async def update_config(self, config_id: str, update_data: GraphDBConfigUpdate) -> Optional[GraphDBConfigResponse]:
        """Update GraphDB configuration"""
        try:
            update_dict = update_data.dict(exclude_unset=True)
            if not update_dict:
                return await self.get_config(config_id)
            
            update_dict["updated_at"] = datetime.utcnow()
            
            result = await self.collection.update_one(
                {"_id": ObjectId(config_id)},
                {"$set": update_dict}
            )
            
            if result.modified_count > 0:
                return await self.get_config(config_id)
            return None
            
        except Exception as e:
            logger.error(f"Error updating GraphDB configuration: {e}")
            raise HTTPException(status_code=500, detail="Failed to update GraphDB configuration")

    async def delete_config(self, config_id: str) -> bool:
        """Delete GraphDB configuration"""
        try:
            result = await self.collection.delete_one({"_id": ObjectId(config_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting GraphDB configuration: {e}")
            raise HTTPException(status_code=500, detail="Failed to delete GraphDB configuration")

    async def test_connection(self, config_id: str) -> GraphDBTestResponse:
        """Test GraphDB connection and endpoints"""
        try:
            config = await self.collection.find_one({"_id": ObjectId(config_id)})
            if not config:
                raise HTTPException(status_code=404, detail="GraphDB configuration not found")
            
            test_result = GraphDBTestResponse(
                success=False,
                message="",
                select_endpoint_accessible=False,
                update_endpoint_accessible=False,
                repository_exists=False,
                authentication_successful=False,
                test_time=datetime.utcnow()
            )
            
            # Test SELECT endpoint
            try:
                select_success = await self._test_endpoint(
                    config["select_endpoint"],
                    config["username"],
                    config["password"],
                    "SELECT"
                )
                test_result.select_endpoint_accessible = select_success
            except Exception as e:
                logger.warning(f"SELECT endpoint test failed: {e}")
            
            # Test UPDATE endpoint
            try:
                update_success = await self._test_endpoint(
                    config["update_endpoint"],
                    config["username"],
                    config["password"],
                    "UPDATE"
                )
                test_result.update_endpoint_accessible = update_success
            except Exception as e:
                logger.warning(f"UPDATE endpoint test failed: {e}")
            
            # Test repository existence
            try:
                repo_exists = await self._test_repository(config)
                test_result.repository_exists = repo_exists
            except Exception as e:
                logger.warning(f"Repository test failed: {e}")
            
            # Overall success
            test_result.success = (
                test_result.select_endpoint_accessible and
                test_result.update_endpoint_accessible and
                test_result.repository_exists
            )
            
            if test_result.success:
                test_result.message = "All tests passed successfully"
                # Update config status
                await self.collection.update_one(
                    {"_id": ObjectId(config_id)},
                    {"$set": {"status": GraphDBStatus.ACTIVE, "updated_at": datetime.utcnow()}}
                )
            else:
                test_result.message = "Some tests failed - check individual endpoint status"
                await self.collection.update_one(
                    {"_id": ObjectId(config_id)},
                    {"$set": {"status": GraphDBStatus.ERROR, "updated_at": datetime.utcnow()}}
                )
            
            return test_result
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error testing GraphDB connection: {e}")
            raise HTTPException(status_code=500, detail="Failed to test GraphDB connection")

    async def execute_sparql_query(self, query_request: SPARQLQueryRequest) -> SPARQLQueryResponse:
        """Execute SPARQL query"""
        try:
            config = await self.collection.find_one({"_id": ObjectId(query_request.config_id)})
            if not config:
                raise HTTPException(status_code=404, detail="GraphDB configuration not found")
            
            if config["status"] != GraphDBStatus.ACTIVE:
                raise HTTPException(status_code=400, detail="GraphDB configuration is not active")
            
            start_time = datetime.utcnow()
            
            # Determine endpoint based on query type
            if query_request.query_type.upper() in ["SELECT", "ASK", "CONSTRUCT", "DESCRIBE"]:
                endpoint = config["select_endpoint"]
            else:
                endpoint = config["update_endpoint"]
            
            # Execute query
            result = await self._execute_query(
                endpoint,
                config["username"],
                config["password"],
                query_request.query,
                query_request.query_type,
                query_request.timeout or config["timeout"]
            )
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            return SPARQLQueryResponse(
                success=True,
                data=result,
                execution_time=execution_time,
                query_type=query_request.query_type,
                config_id=query_request.config_id
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error executing SPARQL query: {e}")
            return SPARQLQueryResponse(
                success=False,
                error=str(e),
                execution_time=0,
                query_type=query_request.query_type,
                config_id=query_request.config_id
            )

    async def _test_endpoint(self, endpoint: str, username: str, password: str, query_type: str) -> bool:
        """Test if an endpoint is accessible"""
        try:
            if query_type == "SELECT":
                test_query = "SELECT * WHERE { ?s ?p ?o } LIMIT 1"
            else:
                test_query = "INSERT DATA { <http://test> <http://test> <http://test> }"
            
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(username, password)
                
                if query_type == "SELECT":
                    # Use URL parameters for SELECT queries
                    params = {'query': test_query}
                    headers = {'Accept': 'application/json'}
                    async with session.get(
                        endpoint,
                        params=params,
                        headers=headers,
                        auth=auth,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        return response.status in [200, 201, 204]
                else:
                    # Use raw query data with proper content type for UPDATE queries
                    headers = {'Content-Type': 'application/sparql-update'}
                    async with session.post(
                        endpoint,
                        data=test_query,
                        headers=headers,
                        auth=auth,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        return response.status in [200, 201, 204]
                    
        except Exception as e:
            logger.warning(f"Endpoint test failed for {endpoint}: {e}")
            return False

    async def _test_repository(self, config: Dict[str, Any]) -> bool:
        """Test if repository exists"""
        try:
            # Try to list repositories or query repository info
            test_query = "SELECT ?repo WHERE { ?repo a <http://www.openrdf.org/config/repository#> } LIMIT 1"
            
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(config["username"], config["password"])
                
                # Use URL parameters for SELECT queries
                params = {'query': test_query}
                headers = {'Accept': 'application/json'}
                async with session.get(
                    config["select_endpoint"],
                    params=params,
                    headers=headers,
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
                    
        except Exception as e:
            logger.warning(f"Repository test failed: {e}")
            return False

    async def _execute_query(self, endpoint: str, username: str, password: str, 
                           query: str, query_type: str, timeout: int) -> Dict[str, Any]:
        """Execute SPARQL query against endpoint"""
        try:
            async with aiohttp.ClientSession() as session:
                auth = aiohttp.BasicAuth(username, password)
                
                # For GraphDB, use URL parameters for SELECT queries, form data for UPDATE queries
                if query_type.upper() in ["SELECT", "ASK", "CONSTRUCT", "DESCRIBE"]:
                    # Use URL parameters for SELECT queries
                    params = {'query': query}
                    headers = {'Accept': 'application/json'}
                    async with session.get(
                        endpoint,
                        params=params,
                        headers=headers,
                        auth=auth,
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as response:
                        if response.status not in [200, 201, 204]:
                            raise Exception(f"SPARQL query failed with status {response.status}: {await response.text()}")
                        return await response.json()
                else:
                    # Use raw query data with proper content type for UPDATE queries
                    headers = {'Content-Type': 'application/sparql-update'}
                    async with session.post(
                        endpoint,
                        data=query,
                        headers=headers,
                        auth=auth,
                        timeout=aiohttp.ClientTimeout(total=timeout)
                    ) as response:
                        if response.status not in [200, 201, 204]:
                            raise Exception(f"SPARQL query failed with status {response.status}: {await response.text()}")
                        return {"message": "Query executed successfully", "status": response.status}
                        
        except Exception as e:
            logger.error(f"SPARQL query execution failed: {e}")
            raise

    def _to_response(self, config: Dict[str, Any]) -> GraphDBConfigResponse:
        """Convert database document to response model"""
        return GraphDBConfigResponse(
            id=str(config["_id"]),
            name=config["name"],
            description=config.get("description"),
            select_endpoint=config["select_endpoint"],
            update_endpoint=config["update_endpoint"],
            username=config["username"],
            repository_name=config["repository_name"],
            status=config["status"],
            created_at=config["created_at"],
            updated_at=config["updated_at"],
            created_by=config["created_by"],
            timeout=config.get("timeout", 30),
            max_retries=config.get("max_retries", 3)
        )


# Global service instance
graphdb_service = GraphDBService()
