<<<<<<< HEAD
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, HttpUrl
from bson import ObjectId
from enum import Enum


class GraphDBStatus(str, Enum):
    """GraphDB connection status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    CONFIGURING = "configuring"


class GraphDBConfig(BaseModel):
    """GraphDB configuration model"""
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    name: str = Field(..., description="Configuration name")
    description: Optional[str] = Field(None, description="Configuration description")
    
    # SPARQL Endpoints
    select_endpoint: str = Field(..., description="SPARQL SELECT endpoint URL")
    update_endpoint: str = Field(..., description="SPARQL UPDATE endpoint URL")
    
    # Authentication
    username: str = Field(..., description="GraphDB username")
    password: str = Field(..., description="GraphDB password")
    
    # Repository details
    repository_name: str = Field(..., description="GraphDB repository name")
    
    # Status and metadata
    status: GraphDBStatus = Field(default=GraphDBStatus.CONFIGURING, description="Configuration status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    created_by: str = Field(..., description="User who created this configuration")
    
    # Optional settings
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class GraphDBConfigCreate(BaseModel):
    """Model for creating GraphDB configuration"""
    name: str
    description: Optional[str] = None
    select_endpoint: str
    update_endpoint: str
    username: str
    password: str
    repository_name: str
    timeout: int = 30
    max_retries: int = 3


class GraphDBConfigUpdate(BaseModel):
    """Model for updating GraphDB configuration"""
    name: Optional[str] = None
    description: Optional[str] = None
    select_endpoint: Optional[str] = None
    update_endpoint: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    repository_name: Optional[str] = None
    status: Optional[GraphDBStatus] = None
    timeout: Optional[int] = None
    max_retries: Optional[int] = None


class GraphDBConfigResponse(BaseModel):
    """Response model for GraphDB configuration (without password)"""
    id: str
    name: str
    description: Optional[str] = None
    select_endpoint: str
    update_endpoint: str
    username: str
    repository_name: str
    status: GraphDBStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
    timeout: int
    max_retries: int


class SPARQLQueryRequest(BaseModel):
    """Model for SPARQL query requests"""
    config_id: str = Field(..., description="GraphDB configuration ID")
    query: str = Field(..., description="SPARQL query")
    query_type: str = Field(..., description="Query type: SELECT, INSERT, DELETE, UPDATE")
    timeout: Optional[int] = Field(None, description="Custom timeout for this query")


class SPARQLQueryResponse(BaseModel):
    """Model for SPARQL query responses"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float
    query_type: str
    config_id: str


class GraphDBTestResponse(BaseModel):
    """Model for GraphDB connection test response"""
    success: bool
    message: str
    select_endpoint_accessible: bool
    update_endpoint_accessible: bool
    repository_exists: bool
    authentication_successful: bool
    test_time: datetime
=======
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, HttpUrl
from bson import ObjectId
from enum import Enum


class GraphDBStatus(str, Enum):
    """GraphDB connection status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    CONFIGURING = "configuring"


class GraphDBConfig(BaseModel):
    """GraphDB configuration model"""
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    name: str = Field(..., description="Configuration name")
    description: Optional[str] = Field(None, description="Configuration description")
    
    # SPARQL Endpoints
    select_endpoint: str = Field(..., description="SPARQL SELECT endpoint URL")
    update_endpoint: str = Field(..., description="SPARQL UPDATE endpoint URL")
    
    # Authentication
    username: str = Field(..., description="GraphDB username")
    password: str = Field(..., description="GraphDB password")
    
    # Repository details
    repository_name: str = Field(..., description="GraphDB repository name")
    
    # Status and metadata
    status: GraphDBStatus = Field(default=GraphDBStatus.CONFIGURING, description="Configuration status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(..., description="User who created this configuration")
    
    # Optional settings
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class GraphDBConfigCreate(BaseModel):
    """Model for creating GraphDB configuration"""
    name: str
    description: Optional[str] = None
    select_endpoint: str
    update_endpoint: str
    username: str
    password: str
    repository_name: str
    timeout: int = 30
    max_retries: int = 3


class GraphDBConfigUpdate(BaseModel):
    """Model for updating GraphDB configuration"""
    name: Optional[str] = None
    description: Optional[str] = None
    select_endpoint: Optional[str] = None
    update_endpoint: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    repository_name: Optional[str] = None
    status: Optional[GraphDBStatus] = None
    timeout: Optional[int] = None
    max_retries: Optional[int] = None


class GraphDBConfigResponse(BaseModel):
    """Response model for GraphDB configuration (without password)"""
    id: str
    name: str
    description: Optional[str] = None
    select_endpoint: str
    update_endpoint: str
    username: str
    repository_name: str
    status: GraphDBStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
    timeout: int
    max_retries: int


class SPARQLQueryRequest(BaseModel):
    """Model for SPARQL query requests"""
    config_id: str = Field(..., description="GraphDB configuration ID")
    query: str = Field(..., description="SPARQL query")
    query_type: str = Field(..., description="Query type: SELECT, INSERT, DELETE, UPDATE")
    timeout: Optional[int] = Field(None, description="Custom timeout for this query")


class SPARQLQueryResponse(BaseModel):
    """Model for SPARQL query responses"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float
    query_type: str
    config_id: str


class GraphDBTestResponse(BaseModel):
    """Model for GraphDB connection test response"""
    success: bool
    message: str
    select_endpoint_accessible: bool
    update_endpoint_accessible: bool
    repository_exists: bool
    authentication_successful: bool
    test_time: datetime
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
