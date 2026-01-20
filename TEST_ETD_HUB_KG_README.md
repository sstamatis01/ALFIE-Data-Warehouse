<<<<<<< HEAD
# ETD-Hub Knowledge Graph SPARQL Test Script

This script tests the ETD-Hub knowledge graph (`etd-hub-kg-test`) stored in GraphDB using SPARQL queries.

## Configuration

- **Knowledge Graph Name**: `etd-hub-kg-test`
- **Configuration ID**: `68f9d2d864294f23fae43471`
- **API Base URL**: `http://localhost:8000` (default)

## Prerequisites

1. **Data Warehouse API** must be running
   ```bash
   docker-compose up
   # or
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **GraphDB** must be accessible and the knowledge graph must be loaded

3. **Python dependencies**:
   ```bash
   pip install requests
   ```

## Usage

### Run the complete test suite

```bash
python test_etd_hub_kg_sparql.py
```

The script will:
1. Test API connectivity
2. Verify GraphDB configuration
3. Test GraphDB connection
4. Execute a comprehensive set of SPARQL queries covering:
   - Basic knowledge graph statistics
   - Entity type queries (Organizations, Datasets, Documents, Providers)
   - VAIR domain queries (Justice, Finance, Education)
   - Ontology class analysis
   - Relationship exploration
   - Complex analytical queries
   - ETD-Hub specific queries

### Modify Configuration

If you need to test a different knowledge graph, edit the constants at the top of the script:

```python
API_BASE_URL = "http://localhost:8000"  # Change if API is on different host/port
CONFIG_ID = "68f9d2d864294f23fae43471"  # Your GraphDB config ID
KG_NAME = "etd-hub-kg-test"              # Your knowledge graph name
```

## Test Categories

### 1. Basic Queries
- Count all triples
- Sample triples
- Count distinct subjects/predicates

### 2. Entity Type Queries
- Organizations (foaf:Organization, org:Organization)
- Datasets (dcat:Dataset, airo:Dataset, schema:Dataset)
- Documents (foaf:Document, bibo:Document)
- Providers (vair:Provider)

### 3. VAIR Domain Queries
- Entities in Justice Domain
- Entities in Finance Domain
- Entities in Education Domain
- Count entities by domain

### 4. Ontology Class Queries
- All entity types with counts
- Entities with multiple ontology classes

### 5. Relationship Queries
- All unique predicates
- Entity-to-entity connections

### 6. Complex Analytical Queries
- Organizations grouped by domain
- Datasets with providers
- Comprehensive entity statistics

### 7. ETD-Hub Specific Queries
- Themes
- Questions
- Answers
- Theme-Question-Answer relationships

## Ontology Prefixes

The script uses all ontology prefixes defined in `ontologies.txt`:
- RDF/RDFS/OWL (W3C standards)
- DC/DCTerms (Dublin Core)
- FOAF (Friend of a Friend)
- ORG (Organization)
- DCAT (Data Catalog)
- Schema.org
- VAIR (AI Risk)
- AIRO (AI Risk Ontology)
- ETD-Hub custom ontologies
- And more...

## Output Format

The script provides:
- ✅/❌ Status indicators for each test
- Execution times for queries
- Result counts
- Sample data rows (limited to prevent overwhelming output)
- Detailed error messages if queries fail

## Troubleshooting

### API Connection Issues
```
❌ Could not connect to API at http://localhost:8000
```
**Solution**: Ensure the API server is running and accessible.

### Configuration Not Found
```
❌ Failed to get config: 404
```
**Solution**: Verify the `CONFIG_ID` is correct. You can list all configs using:
```bash
curl http://localhost:8000/graphdb/configs
```

### Connection Test Fails
```
❌ Connection test failed
```
**Solution**: 
- Verify GraphDB is running
- Check the repository name matches
- Verify authentication credentials
- Ensure network connectivity

### Query Returns No Results
```
No results found
```
**Possible reasons**:
- Knowledge graph is empty
- Query structure doesn't match the actual data structure
- Entity URIs or predicates use different namespaces
- Data hasn't been imported yet

**Solution**: 
- Check if data exists: `SELECT * WHERE { ?s ?p ?o } LIMIT 10`
- Inspect actual data structure
- Adjust queries based on actual ontology usage

## Custom Queries

You can add custom queries by modifying the query functions in the script:

```python
def get_custom_queries() -> list:
    return [
        {
            "name": "My Custom Query",
            "description": "Description of what this query does",
            "query": f"""
{PREFIXES}
SELECT ?entity ?property ?value WHERE {{
    ?entity ?property ?value .
    # Your query conditions here
}}
LIMIT 50
"""
        }
    ]
```

Then add it to the test suite in `run_test_suite()`:

```python
# Test X: Custom Queries
print_section("X. Custom Queries")
for query_def in get_custom_queries():
    result = execute_sparql_query(...)
```

## Integration with CASPAR Service

The `SemKG_annotations.json` file is intended for use with a CASPAR service that will be added later. This test script focuses on testing the knowledge graph structure and data that has already been loaded into GraphDB.

## Related Files

- `ontologies.txt` - Ontology prefix definitions
- `SemKG_annotations.json` - Annotated JSON for CASPAR service (future use)
- `test_graphdb_api.py` - General GraphDB API test script
- `etd_hub_to_graphdb_example.py` - Example of importing ETD-Hub data to GraphDB

## Notes

- The script limits result display to prevent overwhelming output (typically 10-15 rows per query)
- Execution times are reported for performance monitoring
- All queries use SELECT type (read-only) to avoid modifying data
- The script gracefully handles errors and continues with remaining tests

=======
# ETD-Hub Knowledge Graph SPARQL Test Script

This script tests the ETD-Hub knowledge graph (`etd-hub-kg-test`) stored in GraphDB using SPARQL queries.

## Configuration

- **Knowledge Graph Name**: `etd-hub-kg-test`
- **Configuration ID**: `68f9d2d864294f23fae43471`
- **API Base URL**: `http://localhost:8000` (default)

## Prerequisites

1. **Data Warehouse API** must be running
   ```bash
   docker-compose up
   # or
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. **GraphDB** must be accessible and the knowledge graph must be loaded

3. **Python dependencies**:
   ```bash
   pip install requests
   ```

## Usage

### Run the complete test suite

```bash
python test_etd_hub_kg_sparql.py
```

The script will:
1. Test API connectivity
2. Verify GraphDB configuration
3. Test GraphDB connection
4. Execute a comprehensive set of SPARQL queries covering:
   - Basic knowledge graph statistics
   - Entity type queries (Organizations, Datasets, Documents, Providers)
   - VAIR domain queries (Justice, Finance, Education)
   - Ontology class analysis
   - Relationship exploration
   - Complex analytical queries
   - ETD-Hub specific queries

### Modify Configuration

If you need to test a different knowledge graph, edit the constants at the top of the script:

```python
API_BASE_URL = "http://localhost:8000"  # Change if API is on different host/port
CONFIG_ID = "68f9d2d864294f23fae43471"  # Your GraphDB config ID
KG_NAME = "etd-hub-kg-test"              # Your knowledge graph name
```

## Test Categories

### 1. Basic Queries
- Count all triples
- Sample triples
- Count distinct subjects/predicates

### 2. Entity Type Queries
- Organizations (foaf:Organization, org:Organization)
- Datasets (dcat:Dataset, airo:Dataset, schema:Dataset)
- Documents (foaf:Document, bibo:Document)
- Providers (vair:Provider)

### 3. VAIR Domain Queries
- Entities in Justice Domain
- Entities in Finance Domain
- Entities in Education Domain
- Count entities by domain

### 4. Ontology Class Queries
- All entity types with counts
- Entities with multiple ontology classes

### 5. Relationship Queries
- All unique predicates
- Entity-to-entity connections

### 6. Complex Analytical Queries
- Organizations grouped by domain
- Datasets with providers
- Comprehensive entity statistics

### 7. ETD-Hub Specific Queries
- Themes
- Questions
- Answers
- Theme-Question-Answer relationships

## Ontology Prefixes

The script uses all ontology prefixes defined in `ontologies.txt`:
- RDF/RDFS/OWL (W3C standards)
- DC/DCTerms (Dublin Core)
- FOAF (Friend of a Friend)
- ORG (Organization)
- DCAT (Data Catalog)
- Schema.org
- VAIR (AI Risk)
- AIRO (AI Risk Ontology)
- ETD-Hub custom ontologies
- And more...

## Output Format

The script provides:
- ✅/❌ Status indicators for each test
- Execution times for queries
- Result counts
- Sample data rows (limited to prevent overwhelming output)
- Detailed error messages if queries fail

## Troubleshooting

### API Connection Issues
```
❌ Could not connect to API at http://localhost:8000
```
**Solution**: Ensure the API server is running and accessible.

### Configuration Not Found
```
❌ Failed to get config: 404
```
**Solution**: Verify the `CONFIG_ID` is correct. You can list all configs using:
```bash
curl http://localhost:8000/graphdb/configs
```

### Connection Test Fails
```
❌ Connection test failed
```
**Solution**: 
- Verify GraphDB is running
- Check the repository name matches
- Verify authentication credentials
- Ensure network connectivity

### Query Returns No Results
```
No results found
```
**Possible reasons**:
- Knowledge graph is empty
- Query structure doesn't match the actual data structure
- Entity URIs or predicates use different namespaces
- Data hasn't been imported yet

**Solution**: 
- Check if data exists: `SELECT * WHERE { ?s ?p ?o } LIMIT 10`
- Inspect actual data structure
- Adjust queries based on actual ontology usage

## Custom Queries

You can add custom queries by modifying the query functions in the script:

```python
def get_custom_queries() -> list:
    return [
        {
            "name": "My Custom Query",
            "description": "Description of what this query does",
            "query": f"""
{PREFIXES}
SELECT ?entity ?property ?value WHERE {{
    ?entity ?property ?value .
    # Your query conditions here
}}
LIMIT 50
"""
        }
    ]
```

Then add it to the test suite in `run_test_suite()`:

```python
# Test X: Custom Queries
print_section("X. Custom Queries")
for query_def in get_custom_queries():
    result = execute_sparql_query(...)
```

## Integration with CASPAR Service

The `SemKG_annotations.json` file is intended for use with a CASPAR service that will be added later. This test script focuses on testing the knowledge graph structure and data that has already been loaded into GraphDB.

## Related Files

- `ontologies.txt` - Ontology prefix definitions
- `SemKG_annotations.json` - Annotated JSON for CASPAR service (future use)
- `test_graphdb_api.py` - General GraphDB API test script
- `etd_hub_to_graphdb_example.py` - Example of importing ETD-Hub data to GraphDB

## Notes

- The script limits result display to prevent overwhelming output (typically 10-15 rows per query)
- Execution times are reported for performance monitoring
- All queries use SELECT type (read-only) to avoid modifying data
- The script gracefully handles errors and continues with remaining tests

>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
