<<<<<<< HEAD
# GraphDB Integration for Data Warehouse

This document describes the GraphDB integration features added to the Data Warehouse API, enabling support for semantic knowledge graphs and SPARQL querying.

## Overview

The GraphDB integration provides:
- **SPARQL Endpoint Management**: Configure and manage connections to GraphDB repositories
- **Query Execution**: Execute SELECT and UPDATE SPARQL queries
- **Connection Testing**: Validate GraphDB connections and repository access
- **Authentication**: Secure credential management for GraphDB access

## Features

### 1. GraphDB Configuration Management
- Create, read, update, and delete GraphDB configurations
- Store connection details for SPARQL endpoints
- Manage authentication credentials
- Track configuration status and health

### 2. SPARQL Query Support
- **SELECT Queries**: Retrieve data from the knowledge graph
- **UPDATE Queries**: Insert, delete, and modify triples
- **Query Examples**: Built-in examples for common operations
- **Execution Monitoring**: Track query performance and results

### 3. Connection Testing
- Validate SPARQL endpoint accessibility
- Test authentication credentials
- Verify repository existence
- Monitor connection health

## API Endpoints

### Configuration Management

#### Create GraphDB Configuration
```http
POST /graphdb/configs?created_by={user_id}
Content-Type: application/json

{
  "name": "Production GraphDB",
  "description": "Main GraphDB instance for production",
  "select_endpoint": "http://graphdb.example.com:7200/repositories/production",
  "update_endpoint": "http://graphdb.example.com:7200/repositories/production/statements",
  "username": "admin",
  "password": "secure_password",
  "repository_name": "production",
  "timeout": 30,
  "max_retries": 3
}
```

#### Get All Configurations
```http
GET /graphdb/configs?skip=0&limit=100
```

#### Get Configuration by ID
```http
GET /graphdb/configs/{config_id}
```

#### Update Configuration
```http
PUT /graphdb/configs/{config_id}
Content-Type: application/json

{
  "name": "Updated GraphDB Config",
  "timeout": 60
}
```

#### Delete Configuration
```http
DELETE /graphdb/configs/{config_id}
```

### Connection Testing

#### Test GraphDB Connection
```http
POST /graphdb/configs/{config_id}/test
```

Response:
```json
{
  "success": true,
  "message": "All tests passed successfully",
  "select_endpoint_accessible": true,
  "update_endpoint_accessible": true,
  "repository_exists": true,
  "authentication_successful": true,
  "test_time": "2025-01-21T10:30:00Z"
}
```

### SPARQL Query Execution

#### Execute SPARQL Query
```http
POST /graphdb/query
Content-Type: application/json

{
  "config_id": "config_id_here",
  "query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10",
  "query_type": "SELECT",
  "timeout": 30
}
```

Response:
```json
{
  "success": true,
  "data": {
    "head": {
      "vars": ["s", "p", "o"]
    },
    "results": {
      "bindings": [
        {
          "s": {"type": "uri", "value": "http://example.org/subject"},
          "p": {"type": "uri", "value": "http://example.org/predicate"},
          "o": {"type": "literal", "value": "object"}
        }
      ]
    }
  },
  "execution_time": 0.123,
  "query_type": "SELECT",
  "config_id": "config_id_here"
}
```

### Query Examples

#### Get Query Examples
```http
GET /graphdb/configs/{config_id}/query-examples
```

Response:
```json
{
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
    }
  ],
  "update_examples": [
    {
      "name": "Insert a triple",
      "query": "INSERT DATA { <http://example.org/subject> <http://example.org/predicate> <http://example.org/object> }",
      "description": "Insert a single triple into the repository"
    }
  ],
  "repository_info": {
    "name": "production",
    "select_endpoint": "http://graphdb.example.com:7200/repositories/production",
    "update_endpoint": "http://graphdb.example.com:7200/repositories/production/statements"
  }
}
```

### Health Monitoring

#### GraphDB Service Health
```http
GET /graphdb/health
```

Response:
```json
{
  "status": "healthy",
  "message": "GraphDB service is operational",
  "total_configurations": 5
}
```

## Configuration Details

### GraphDB Configuration Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Configuration name |
| `description` | string | No | Configuration description |
| `select_endpoint` | string | Yes | SPARQL SELECT endpoint URL |
| `update_endpoint` | string | Yes | SPARQL UPDATE endpoint URL |
| `username` | string | Yes | GraphDB username |
| `password` | string | Yes | GraphDB password |
| `repository_name` | string | Yes | GraphDB repository name |
| `timeout` | integer | No | Request timeout in seconds (default: 30) |
| `max_retries` | integer | No | Maximum retry attempts (default: 3) |

### Endpoint URL Formats

#### SELECT Endpoint
```
http://<IP>:<PORT>/repositories/<REPOSITORY_NAME>
```

#### UPDATE Endpoint
```
http://<IP>:<PORT>/repositories/<REPOSITORY_NAME>/statements
```

### Example Endpoints
- **SELECT**: `http://localhost:7200/repositories/my-repo`
- **UPDATE**: `http://localhost:7200/repositories/my-repo/statements`

## Usage Examples

### 1. Setting Up GraphDB Configuration

```python
import requests

# Create GraphDB configuration
config_data = {
    "name": "My GraphDB",
    "description": "Local GraphDB instance",
    "select_endpoint": "http://localhost:7200/repositories/my-repo",
    "update_endpoint": "http://localhost:7200/repositories/my-repo/statements",
    "username": "admin",
    "password": "admin",
    "repository_name": "my-repo"
}

response = requests.post(
    "http://localhost:8000/graphdb/configs?created_by=user123",
    json=config_data
)

config_id = response.json()["id"]
```

### 2. Testing Connection

```python
# Test the connection
response = requests.post(f"http://localhost:8000/graphdb/configs/{config_id}/test")
result = response.json()

if result["success"]:
    print("✅ GraphDB connection successful!")
else:
    print("❌ Connection failed:", result["message"])
```

### 3. Executing SPARQL Queries

```python
# Execute a SELECT query
select_query = {
    "config_id": config_id,
    "query": "SELECT * WHERE { ?s ?p ?o } LIMIT 5",
    "query_type": "SELECT"
}

response = requests.post(
    "http://localhost:8000/graphdb/query",
    json=select_query
)

result = response.json()
print("Query results:", result["data"])

# Execute an UPDATE query
update_query = {
    "config_id": config_id,
    "query": "INSERT DATA { <http://example.org/test> <http://example.org/type> <http://example.org/Test> }",
    "query_type": "INSERT"
}

response = requests.post(
    "http://localhost:8000/graphdb/query",
    json=update_query
)

result = response.json()
print("Update result:", result["success"])
```

## Integration with ETD-Hub

The GraphDB integration is designed to work with the ETD-Hub semantic knowledge graph processing:

1. **ETD-Hub Data Processing**: ETD-Hub data can be processed by semantic knowledge graph services
2. **CASPAR Service Integration**: The CASPAR service can use GraphDB configurations to create triple stores
3. **SPARQL Querying**: Both services can query the knowledge graph using the configured SPARQL endpoints

## Security Considerations

1. **Credential Storage**: Passwords are stored in the database and should be encrypted in production
2. **Access Control**: Consider implementing user-based access control for configurations
3. **Network Security**: Ensure GraphDB endpoints are properly secured and accessible only from authorized sources
4. **Query Validation**: Consider implementing query validation to prevent malicious SPARQL queries

## Error Handling

The API provides comprehensive error handling:

- **404**: Configuration not found
- **400**: Invalid request data or inactive configuration
- **409**: Configuration name already exists
- **500**: Internal server errors

## Testing

Use the provided test script to verify GraphDB functionality:

```bash
python test_graphdb_api.py
```

## Dependencies

The GraphDB integration requires:
- `aiohttp`: For asynchronous HTTP requests to SPARQL endpoints
- `pymongo`: For MongoDB operations (already included)
- `fastapi`: For API endpoints (already included)

## Future Enhancements

Potential future improvements:
1. **Query Caching**: Cache frequently used SPARQL queries
2. **Query Templates**: Predefined query templates for common operations
3. **Batch Operations**: Support for batch SPARQL operations
4. **Query History**: Track and log all executed queries
5. **Performance Monitoring**: Detailed performance metrics for queries
6. **Graph Visualization**: Integration with graph visualization tools

## Troubleshooting

### Common Issues

1. **Connection Timeout**: Increase the timeout value in configuration
2. **Authentication Failed**: Verify username and password
3. **Repository Not Found**: Ensure the repository exists in GraphDB
4. **Endpoint Not Accessible**: Check network connectivity and GraphDB status

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger("app.services.graphdb_service").setLevel(logging.DEBUG)
```

## Support

For issues or questions regarding the GraphDB integration:
1. Check the API logs for detailed error messages
2. Use the connection test endpoint to diagnose issues
3. Verify GraphDB instance is running and accessible
4. Review the configuration parameters for accuracy
=======
# GraphDB Integration for Data Warehouse

This document describes the GraphDB integration features added to the Data Warehouse API, enabling support for semantic knowledge graphs and SPARQL querying.

## Overview

The GraphDB integration provides:
- **SPARQL Endpoint Management**: Configure and manage connections to GraphDB repositories
- **Query Execution**: Execute SELECT and UPDATE SPARQL queries
- **Connection Testing**: Validate GraphDB connections and repository access
- **Authentication**: Secure credential management for GraphDB access

## Features

### 1. GraphDB Configuration Management
- Create, read, update, and delete GraphDB configurations
- Store connection details for SPARQL endpoints
- Manage authentication credentials
- Track configuration status and health

### 2. SPARQL Query Support
- **SELECT Queries**: Retrieve data from the knowledge graph
- **UPDATE Queries**: Insert, delete, and modify triples
- **Query Examples**: Built-in examples for common operations
- **Execution Monitoring**: Track query performance and results

### 3. Connection Testing
- Validate SPARQL endpoint accessibility
- Test authentication credentials
- Verify repository existence
- Monitor connection health

## API Endpoints

### Configuration Management

#### Create GraphDB Configuration
```http
POST /graphdb/configs?created_by={user_id}
Content-Type: application/json

{
  "name": "Production GraphDB",
  "description": "Main GraphDB instance for production",
  "select_endpoint": "http://graphdb.example.com:7200/repositories/production",
  "update_endpoint": "http://graphdb.example.com:7200/repositories/production/statements",
  "username": "admin",
  "password": "secure_password",
  "repository_name": "production",
  "timeout": 30,
  "max_retries": 3
}
```

#### Get All Configurations
```http
GET /graphdb/configs?skip=0&limit=100
```

#### Get Configuration by ID
```http
GET /graphdb/configs/{config_id}
```

#### Update Configuration
```http
PUT /graphdb/configs/{config_id}
Content-Type: application/json

{
  "name": "Updated GraphDB Config",
  "timeout": 60
}
```

#### Delete Configuration
```http
DELETE /graphdb/configs/{config_id}
```

### Connection Testing

#### Test GraphDB Connection
```http
POST /graphdb/configs/{config_id}/test
```

Response:
```json
{
  "success": true,
  "message": "All tests passed successfully",
  "select_endpoint_accessible": true,
  "update_endpoint_accessible": true,
  "repository_exists": true,
  "authentication_successful": true,
  "test_time": "2025-01-21T10:30:00Z"
}
```

### SPARQL Query Execution

#### Execute SPARQL Query
```http
POST /graphdb/query
Content-Type: application/json

{
  "config_id": "config_id_here",
  "query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10",
  "query_type": "SELECT",
  "timeout": 30
}
```

Response:
```json
{
  "success": true,
  "data": {
    "head": {
      "vars": ["s", "p", "o"]
    },
    "results": {
      "bindings": [
        {
          "s": {"type": "uri", "value": "http://example.org/subject"},
          "p": {"type": "uri", "value": "http://example.org/predicate"},
          "o": {"type": "literal", "value": "object"}
        }
      ]
    }
  },
  "execution_time": 0.123,
  "query_type": "SELECT",
  "config_id": "config_id_here"
}
```

### Query Examples

#### Get Query Examples
```http
GET /graphdb/configs/{config_id}/query-examples
```

Response:
```json
{
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
    }
  ],
  "update_examples": [
    {
      "name": "Insert a triple",
      "query": "INSERT DATA { <http://example.org/subject> <http://example.org/predicate> <http://example.org/object> }",
      "description": "Insert a single triple into the repository"
    }
  ],
  "repository_info": {
    "name": "production",
    "select_endpoint": "http://graphdb.example.com:7200/repositories/production",
    "update_endpoint": "http://graphdb.example.com:7200/repositories/production/statements"
  }
}
```

### Health Monitoring

#### GraphDB Service Health
```http
GET /graphdb/health
```

Response:
```json
{
  "status": "healthy",
  "message": "GraphDB service is operational",
  "total_configurations": 5
}
```

## Configuration Details

### GraphDB Configuration Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Configuration name |
| `description` | string | No | Configuration description |
| `select_endpoint` | string | Yes | SPARQL SELECT endpoint URL |
| `update_endpoint` | string | Yes | SPARQL UPDATE endpoint URL |
| `username` | string | Yes | GraphDB username |
| `password` | string | Yes | GraphDB password |
| `repository_name` | string | Yes | GraphDB repository name |
| `timeout` | integer | No | Request timeout in seconds (default: 30) |
| `max_retries` | integer | No | Maximum retry attempts (default: 3) |

### Endpoint URL Formats

#### SELECT Endpoint
```
http://<IP>:<PORT>/repositories/<REPOSITORY_NAME>
```

#### UPDATE Endpoint
```
http://<IP>:<PORT>/repositories/<REPOSITORY_NAME>/statements
```

### Example Endpoints
- **SELECT**: `http://localhost:7200/repositories/my-repo`
- **UPDATE**: `http://localhost:7200/repositories/my-repo/statements`

## Usage Examples

### 1. Setting Up GraphDB Configuration

```python
import requests

# Create GraphDB configuration
config_data = {
    "name": "My GraphDB",
    "description": "Local GraphDB instance",
    "select_endpoint": "http://localhost:7200/repositories/my-repo",
    "update_endpoint": "http://localhost:7200/repositories/my-repo/statements",
    "username": "admin",
    "password": "admin",
    "repository_name": "my-repo"
}

response = requests.post(
    "http://localhost:8000/graphdb/configs?created_by=user123",
    json=config_data
)

config_id = response.json()["id"]
```

### 2. Testing Connection

```python
# Test the connection
response = requests.post(f"http://localhost:8000/graphdb/configs/{config_id}/test")
result = response.json()

if result["success"]:
    print("✅ GraphDB connection successful!")
else:
    print("❌ Connection failed:", result["message"])
```

### 3. Executing SPARQL Queries

```python
# Execute a SELECT query
select_query = {
    "config_id": config_id,
    "query": "SELECT * WHERE { ?s ?p ?o } LIMIT 5",
    "query_type": "SELECT"
}

response = requests.post(
    "http://localhost:8000/graphdb/query",
    json=select_query
)

result = response.json()
print("Query results:", result["data"])

# Execute an UPDATE query
update_query = {
    "config_id": config_id,
    "query": "INSERT DATA { <http://example.org/test> <http://example.org/type> <http://example.org/Test> }",
    "query_type": "INSERT"
}

response = requests.post(
    "http://localhost:8000/graphdb/query",
    json=update_query
)

result = response.json()
print("Update result:", result["success"])
```

## Integration with ETD-Hub

The GraphDB integration is designed to work with the ETD-Hub semantic knowledge graph processing:

1. **ETD-Hub Data Processing**: ETD-Hub data can be processed by semantic knowledge graph services
2. **CASPAR Service Integration**: The CASPAR service can use GraphDB configurations to create triple stores
3. **SPARQL Querying**: Both services can query the knowledge graph using the configured SPARQL endpoints

## Security Considerations

1. **Credential Storage**: Passwords are stored in the database and should be encrypted in production
2. **Access Control**: Consider implementing user-based access control for configurations
3. **Network Security**: Ensure GraphDB endpoints are properly secured and accessible only from authorized sources
4. **Query Validation**: Consider implementing query validation to prevent malicious SPARQL queries

## Error Handling

The API provides comprehensive error handling:

- **404**: Configuration not found
- **400**: Invalid request data or inactive configuration
- **409**: Configuration name already exists
- **500**: Internal server errors

## Testing

Use the provided test script to verify GraphDB functionality:

```bash
python test_graphdb_api.py
```

## Dependencies

The GraphDB integration requires:
- `aiohttp`: For asynchronous HTTP requests to SPARQL endpoints
- `pymongo`: For MongoDB operations (already included)
- `fastapi`: For API endpoints (already included)

## Future Enhancements

Potential future improvements:
1. **Query Caching**: Cache frequently used SPARQL queries
2. **Query Templates**: Predefined query templates for common operations
3. **Batch Operations**: Support for batch SPARQL operations
4. **Query History**: Track and log all executed queries
5. **Performance Monitoring**: Detailed performance metrics for queries
6. **Graph Visualization**: Integration with graph visualization tools

## Troubleshooting

### Common Issues

1. **Connection Timeout**: Increase the timeout value in configuration
2. **Authentication Failed**: Verify username and password
3. **Repository Not Found**: Ensure the repository exists in GraphDB
4. **Endpoint Not Accessible**: Check network connectivity and GraphDB status

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger("app.services.graphdb_service").setLevel(logging.DEBUG)
```

## Support

For issues or questions regarding the GraphDB integration:
1. Check the API logs for detailed error messages
2. Use the connection test endpoint to diagnose issues
3. Verify GraphDB instance is running and accessible
4. Review the configuration parameters for accuracy
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
