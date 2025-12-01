#!/usr/bin/env python3
"""
Test script for ETD-Hub Knowledge Graph SPARQL queries
Tests the knowledge graph named 'etd-hub-kg-test' with ID '68f9d2d864294f23fae43471'
"""

import requests
import json
import time
from typing import Dict, Any, Optional

# Configuration
API_BASE_URL = "http://localhost:8000"
CONFIG_ID = "68f9d2d864294f23fae43471"
KG_NAME = "etd-hub-kg-test"

# Ontology prefixes based on ontologies.txt
PREFIXES = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX org: <http://www.w3.org/ns/org#>
PREFIX sioc: <http://rdfs.org/sioc/ns#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX schema: <http://schema.org/>
PREFIX aipo: <https://w3id.org/aipo#>
PREFIX relaieo: <http://www.ontology.audit4sg.org/RelAIEO#>
PREFIX vair: <https://w3id.org/vair#>
PREFIX airo: <https://w3id.org/airo#>
PREFIX hudock: <http://www.semanticweb.org/rhudock/ontologies/2023/6/ai-risk-compliance-ontology#>
PREFIX fmo: <http://purl.org/fairness-metrics-ontology/>
PREFIX dpv: <https://w3id.org/dpv#>
PREFIX bibo: <http://purl.org/ontology/bibo/>
PREFIX odrl: <http://www.w3.org/ns/odrl/2/>
PREFIX oa: <http://www.w3.org/ns/oa#>
PREFIX cnt: <http://www.w3.org/2011/content#>
PREFIX etd: <http://example.org/etd-hub#>
PREFIX onto: <http://example.org/etd-hub/ontology#>
"""


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(success: bool, message: str, details: Optional[Dict] = None):
    """Print formatted test result"""
    status = "✅" if success else "❌"
    print(f"{status} {message}")
    if details:
        for key, value in details.items():
            print(f"   {key}: {value}")


def test_api_health() -> bool:
    """Test if the API is accessible"""
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print_result(True, "API is accessible")
            return True
        else:
            print_result(False, f"API health check failed: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_result(False, f"Could not connect to API at {API_BASE_URL}")
        print("   Please ensure the API server is running")
        return False
    except Exception as e:
        print_result(False, f"API health check error: {e}")
        return False


def get_graphdb_config(config_id: str) -> Optional[Dict]:
    """Get GraphDB configuration by ID"""
    try:
        response = requests.get(f"{API_BASE_URL}/graphdb/configs/{config_id}")
        if response.status_code == 200:
            config = response.json()
            print_result(True, f"Retrieved GraphDB configuration: {config.get('name', 'Unknown')}")
            print(f"   Repository: {config.get('repository_name', 'Unknown')}")
            print(f"   Status: {config.get('status', 'Unknown')}")
            return config
        else:
            print_result(False, f"Failed to get config: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print_result(False, f"Error getting GraphDB config: {e}")
        return None


def test_graphdb_connection(config_id: str) -> bool:
    """Test GraphDB connection"""
    try:
        response = requests.post(f"{API_BASE_URL}/graphdb/configs/{config_id}/test")
        if response.status_code == 200:
            result = response.json()
            success = result.get('success', False)
            print_result(success, "GraphDB connection test")
            if success:
                print(f"   SELECT endpoint: {'✅' if result.get('select_endpoint_accessible') else '❌'}")
                print(f"   UPDATE endpoint: {'✅' if result.get('update_endpoint_accessible') else '❌'}")
                print(f"   Repository exists: {'✅' if result.get('repository_exists') else '❌'}")
                print(f"   Authentication: {'✅' if result.get('authentication_successful') else '❌'}")
            return success
        else:
            print_result(False, f"Connection test failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print_result(False, f"Error testing connection: {e}")
        return False


def execute_sparql_query(config_id: str, query: str, query_type: str = "SELECT", 
                         description: str = "") -> Optional[Dict]:
    """Execute a SPARQL query"""
    try:
        query_data = {
            "config_id": config_id,
            "query": query,
            "query_type": query_type
        }
        
        start_time = time.time()
        response = requests.post(
            f"{API_BASE_URL}/graphdb/query",
            json=query_data,
            timeout=60
        )
        execution_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                data = result.get('data', {})
                bindings = data.get('results', {}).get('bindings', [])
                count = len(bindings)
                
                print_result(True, description or "Query executed successfully")
                print(f"   Execution time: {execution_time:.3f}s")
                print(f"   Results: {count} row(s)")
                
                return result
            else:
                print_result(False, description or "Query execution failed")
                print(f"   Error: {result.get('error', 'Unknown error')}")
                return None
        else:
            print_result(False, f"Query request failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return None
    except Exception as e:
        print_result(False, f"Error executing query: {e}")
        return None


def print_query_results(result: Dict, max_rows: int = 10):
    """Print formatted query results"""
    if not result or not result.get('success'):
        return
    
    data = result.get('data', {})
    bindings = data.get('results', {}).get('bindings', [])
    
    if not bindings:
        print("   No results found")
        return
    
    # Get variable names from the first binding
    if bindings:
        vars_list = list(bindings[0].keys())
        print(f"\n   Columns: {', '.join(vars_list)}")
        print("   " + "-" * 60)
        
        for i, binding in enumerate(bindings[:max_rows]):
            row_values = []
            for var in vars_list:
                value_obj = binding.get(var, {})
                value = value_obj.get('value', 'N/A')
                # Truncate long values
                if len(str(value)) > 50:
                    value = str(value)[:47] + "..."
                row_values.append(f"{var}={value}")
            print(f"   [{i+1}] " + " | ".join(row_values))
        
        if len(bindings) > max_rows:
            print(f"   ... and {len(bindings) - max_rows} more row(s)")


# ============================================================================
# SPARQL QUERY DEFINITIONS
# ============================================================================

def get_basic_queries() -> list:
    """Get basic test queries"""
    return [
        {
            "name": "Count all triples",
            "description": "Count total number of triples in the knowledge graph",
            "query": f"""
{PREFIXES}
SELECT (COUNT(*) AS ?count) WHERE {{
    ?s ?p ?o .
}}
"""
        },
        {
            "name": "Get sample triples",
            "description": "Retrieve a sample of triples from the knowledge graph",
            "query": f"""
{PREFIXES}
SELECT ?s ?p ?o WHERE {{
    ?s ?p ?o .
}}
LIMIT 20
"""
        },
        {
            "name": "Count distinct subjects",
            "description": "Count unique subjects in the knowledge graph",
            "query": f"""
{PREFIXES}
SELECT (COUNT(DISTINCT ?s) AS ?count) WHERE {{
    ?s ?p ?o .
}}
"""
        },
        {
            "name": "Count distinct predicates",
            "description": "Count unique predicates (relationships) in the knowledge graph",
            "query": f"""
{PREFIXES}
SELECT (COUNT(DISTINCT ?p) AS ?count) WHERE {{
    ?s ?p ?o .
}}
"""
        }
    ]


def get_entity_type_queries() -> list:
    """Get queries for different entity types"""
    return [
        {
            "name": "Find all Organizations",
            "description": "Find entities classified as Organizations (foaf:Organization, org:Organization)",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?entity ?name ?type WHERE {{
    ?entity a/rdfs:subClassOf* foaf:Organization .
    OPTIONAL {{ ?entity rdfs:label ?name . }}
    OPTIONAL {{ ?entity rdf:type ?type . }}
}}
LIMIT 50
"""
        },
        {
            "name": "Find all Datasets",
            "description": "Find entities classified as Datasets (dcat:Dataset, airo:Dataset, schema:Dataset)",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?entity ?name ?type WHERE {{
    ?entity a/rdfs:subClassOf* dcat:Dataset .
    OPTIONAL {{ ?entity rdfs:label ?name . }}
    OPTIONAL {{ ?entity rdf:type ?type . }}
}}
LIMIT 50
"""
        },
        {
            "name": "Find all Documents",
            "description": "Find entities classified as Documents (foaf:Document, bibo:Document)",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?entity ?name ?type WHERE {{
    ?entity a/rdfs:subClassOf* foaf:Document .
    OPTIONAL {{ ?entity rdfs:label ?name . }}
    OPTIONAL {{ ?entity rdf:type ?type . }}
}}
LIMIT 50
"""
        },
        {
            "name": "Find all Providers",
            "description": "Find entities classified as Providers (vair:Provider)",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?entity ?name WHERE {{
    ?entity a/rdfs:subClassOf* vair:Provider .
    OPTIONAL {{ ?entity rdfs:label ?name . }}
}}
LIMIT 50
"""
        }
    ]


def get_vair_domain_queries() -> list:
    """Get queries for VAIR domains"""
    return [
        {
            "name": "Entities in Justice Domain",
            "description": "Find all entities in the Justice domain",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?entity ?name ?type WHERE {{
    ?entity vair:hasDomain vair:JusticeDomain .
    OPTIONAL {{ ?entity rdfs:label ?name . }}
    OPTIONAL {{ ?entity rdf:type ?type . }}
}}
LIMIT 50
"""
        },
        {
            "name": "Entities in Finance Domain",
            "description": "Find all entities in the Finance domain",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?entity ?name ?type WHERE {{
    ?entity vair:hasDomain vair:FinanceDomain .
    OPTIONAL {{ ?entity rdfs:label ?name . }}
    OPTIONAL {{ ?entity rdf:type ?type . }}
}}
LIMIT 50
"""
        },
        {
            "name": "Entities in Education Domain",
            "description": "Find all entities in the Education domain",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?entity ?name ?type WHERE {{
    ?entity vair:hasDomain vair:EducationDomain .
    OPTIONAL {{ ?entity rdfs:label ?name . }}
    OPTIONAL {{ ?entity rdf:type ?type . }}
}}
LIMIT 50
"""
        },
        {
            "name": "Count entities by domain",
            "description": "Count entities grouped by VAIR domain",
            "query": f"""
{PREFIXES}
SELECT ?domain (COUNT(DISTINCT ?entity) AS ?count) WHERE {{
    ?entity vair:hasDomain ?domain .
}}
GROUP BY ?domain
ORDER BY DESC(?count)
"""
        }
    ]


def get_ontology_class_queries() -> list:
    """Get queries for ontology classes"""
    return [
        {
            "name": "All entity types",
            "description": "List all distinct entity types (rdf:type) in the knowledge graph",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?type (COUNT(?entity) AS ?count) WHERE {{
    ?entity a ?type .
}}
GROUP BY ?type
ORDER BY DESC(?count)
LIMIT 30
"""
        },
        {
            "name": "Entities with multiple ontology classes",
            "description": "Find entities that have multiple ontology class assignments",
            "query": f"""
{PREFIXES}
SELECT ?entity (COUNT(DISTINCT ?type) AS ?typeCount) WHERE {{
    ?entity a ?type .
}}
GROUP BY ?entity
HAVING (COUNT(DISTINCT ?type) > 1)
ORDER BY DESC(?typeCount)
LIMIT 20
"""
        }
    ]


def get_relationship_queries() -> list:
    """Get queries for relationships and connections"""
    return [
        {
            "name": "All relationships",
            "description": "Find all unique predicate relationships",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?predicate (COUNT(*) AS ?usageCount) WHERE {{
    ?s ?predicate ?o .
}}
GROUP BY ?predicate
ORDER BY DESC(?usageCount)
LIMIT 30
"""
        },
        {
            "name": "Entity connections",
            "description": "Find entities and their connections to other entities",
            "query": f"""
{PREFIXES}
SELECT ?entity1 ?predicate ?entity2 WHERE {{
    ?entity1 ?predicate ?entity2 .
    FILTER (isURI(?entity1) && isURI(?entity2))
}}
LIMIT 30
"""
        }
    ]


def get_complex_queries() -> list:
    """Get complex analytical queries"""
    return [
        {
            "name": "Organizations by domain",
            "description": "Find organizations grouped by their VAIR domain",
            "query": f"""
{PREFIXES}
SELECT ?domain ?orgName (COUNT(*) AS ?entityCount) WHERE {{
    ?entity a/rdfs:subClassOf* foaf:Organization .
    ?entity vair:hasDomain ?domain .
    OPTIONAL {{ ?entity rdfs:label ?orgName . }}
}}
GROUP BY ?domain ?orgName
ORDER BY ?domain DESC(?entityCount)
LIMIT 30
"""
        },
        {
            "name": "Datasets with providers",
            "description": "Find datasets and their associated providers",
            "query": f"""
{PREFIXES}
SELECT ?dataset ?datasetName ?provider ?providerName WHERE {{
    ?dataset a/rdfs:subClassOf* dcat:Dataset .
    ?provider a/rdfs:subClassOf* vair:Provider .
    OPTIONAL {{ ?dataset rdfs:label ?datasetName . }}
    OPTIONAL {{ ?provider rdfs:label ?providerName . }}
    OPTIONAL {{ ?dataset dcat:distributor ?provider . }}
    OPTIONAL {{ ?dataset dcterms:publisher ?provider . }}
}}
LIMIT 30
"""
        },
        {
            "name": "Entity statistics",
            "description": "Get comprehensive statistics about entities",
            "query": f"""
{PREFIXES}
SELECT 
    (COUNT(DISTINCT ?entity) AS ?totalEntities)
    (COUNT(DISTINCT ?type) AS ?totalTypes)
    (COUNT(DISTINCT ?domain) AS ?totalDomains)
WHERE {{
    ?entity a ?type .
    OPTIONAL {{ ?entity vair:hasDomain ?domain . }}
}}
"""
        }
    ]


def get_etd_hub_queries() -> list:
    """Get queries specific to ETD-Hub structure"""
    return [
        {
            "name": "ETD-Hub Themes",
            "description": "Find all themes in the ETD-Hub knowledge graph",
            "query": f"""
{PREFIXES}
SELECT ?theme ?title ?category WHERE {{
    ?theme a etd:Theme .
    OPTIONAL {{ ?theme dc:title ?title . }}
    OPTIONAL {{ ?theme etd:problemCategory ?category . }}
}}
LIMIT 50
"""
        },
        {
            "name": "ETD-Hub Questions",
            "description": "Find all questions in the ETD-Hub knowledge graph",
            "query": f"""
{PREFIXES}
SELECT ?question ?title ?theme WHERE {{
    ?question a etd:Question .
    OPTIONAL {{ ?question dc:title ?title . }}
    OPTIONAL {{ ?question etd:belongsToTheme ?theme . }}
}}
LIMIT 50
"""
        },
        {
            "name": "ETD-Hub Answers",
            "description": "Find all answers in the ETD-Hub knowledge graph",
            "query": f"""
{PREFIXES}
SELECT ?answer ?description ?question WHERE {{
    ?answer a etd:Answer .
    OPTIONAL {{ ?answer dc:description ?description . }}
    OPTIONAL {{ ?answer etd:answersQuestion ?question . }}
}}
LIMIT 50
"""
        },
        {
            "name": "Theme-Question-Answer relationships",
            "description": "Find relationships between themes, questions, and answers",
            "query": f"""
{PREFIXES}
SELECT ?theme ?question ?answer WHERE {{
    ?theme a etd:Theme .
    ?question a etd:Question .
    ?answer a etd:Answer .
    ?question etd:belongsToTheme ?theme .
    ?answer etd:answersQuestion ?question .
}}
LIMIT 30
"""
        }
    ]


def get_discovery_queries() -> list:
    """Get queries to discover the actual structure of the knowledge graph"""
    return [
        {
            "name": "Discover entity URIs",
            "description": "Find sample entity URIs to understand naming patterns",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?entity WHERE {{
    ?entity ?p ?o .
    FILTER (isURI(?entity))
}}
LIMIT 20
"""
        },
        {
            "name": "Discover predicates",
            "description": "Find all predicates used in the knowledge graph",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?predicate (COUNT(*) AS ?usageCount) WHERE {{
    ?s ?predicate ?o .
}}
GROUP BY ?predicate
ORDER BY DESC(?usageCount)
LIMIT 50
"""
        },
        {
            "name": "Discover entity types",
            "description": "Find all rdf:type assignments",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?type (COUNT(DISTINCT ?entity) AS ?entityCount) WHERE {{
    ?entity a ?type .
}}
GROUP BY ?type
ORDER BY DESC(?entityCount)
LIMIT 50
"""
        },
        {
            "name": "Discover namespaces",
            "description": "Find all namespaces used in entity URIs",
            "query": f"""
{PREFIXES}
SELECT DISTINCT ?namespace (COUNT(DISTINCT ?entity) AS ?count) WHERE {{
    ?entity ?p ?o .
    FILTER (isURI(?entity))
    BIND (REPLACE(STR(?entity), "/[^/]*$", "") AS ?namespace)
}}
GROUP BY ?namespace
ORDER BY DESC(?count)
LIMIT 20
"""
        },
        {
            "name": "Discover literal properties",
            "description": "Find entities with literal values (names, labels, etc.)",
            "query": f"""
{PREFIXES}
SELECT ?entity ?predicate ?value WHERE {{
    ?entity ?predicate ?value .
    FILTER (isLiteral(?value))
}}
LIMIT 30
"""
        }
    ]


# ============================================================================
# MAIN TEST EXECUTION
# ============================================================================

def run_test_suite(config_id: str):
    """Run the complete test suite"""
    print_section(f"Testing Knowledge Graph: {KG_NAME}")
    print(f"Configuration ID: {config_id}")
    
    # Test 1: API Health
    print_section("1. API Health Check")
    if not test_api_health():
        print("\n❌ Cannot proceed without API access. Please start the API server.")
        return
    
    # Test 2: Get Configuration
    print_section("2. GraphDB Configuration")
    config = get_graphdb_config(config_id)
    if not config:
        print("\n❌ Cannot proceed without valid configuration.")
        return
    
    # Test 3: Connection Test
    print_section("3. GraphDB Connection Test")
    connection_ok = test_graphdb_connection(config_id)
    if not connection_ok:
        print("\n⚠️  Connection test failed, but continuing with queries...")
    
    # Test 4: Basic Queries
    print_section("4. Basic Knowledge Graph Queries")
    for query_def in get_basic_queries():
        result = execute_sparql_query(
            config_id,
            query_def["query"],
            "SELECT",
            query_def["description"]
        )
        if result:
            print_query_results(result, max_rows=5)
        print()
    
    # Test 5: Entity Type Queries
    print_section("5. Entity Type Queries")
    for query_def in get_entity_type_queries():
        result = execute_sparql_query(
            config_id,
            query_def["query"],
            "SELECT",
            query_def["description"]
        )
        if result:
            print_query_results(result, max_rows=10)
        print()
    
    # Test 6: VAIR Domain Queries
    print_section("6. VAIR Domain Queries")
    for query_def in get_vair_domain_queries():
        result = execute_sparql_query(
            config_id,
            query_def["query"],
            "SELECT",
            query_def["description"]
        )
        if result:
            print_query_results(result, max_rows=10)
        print()
    
    # Test 7: Ontology Class Queries
    print_section("7. Ontology Class Queries")
    for query_def in get_ontology_class_queries():
        result = execute_sparql_query(
            config_id,
            query_def["query"],
            "SELECT",
            query_def["description"]
        )
        if result:
            print_query_results(result, max_rows=15)
        print()
    
    # Test 8: Relationship Queries
    print_section("8. Relationship Queries")
    for query_def in get_relationship_queries():
        result = execute_sparql_query(
            config_id,
            query_def["query"],
            "SELECT",
            query_def["description"]
        )
        if result:
            print_query_results(result, max_rows=10)
        print()
    
    # Test 9: Complex Analytical Queries
    print_section("9. Complex Analytical Queries")
    for query_def in get_complex_queries():
        result = execute_sparql_query(
            config_id,
            query_def["query"],
            "SELECT",
            query_def["description"]
        )
        if result:
            print_query_results(result, max_rows=10)
        print()
    
    # Test 10: ETD-Hub Specific Queries
    print_section("10. ETD-Hub Specific Queries")
    for query_def in get_etd_hub_queries():
        result = execute_sparql_query(
            config_id,
            query_def["query"],
            "SELECT",
            query_def["description"]
        )
        if result:
            print_query_results(result, max_rows=10)
        print()
    
    # Test 11: Discovery Queries (to understand actual structure)
    print_section("11. Knowledge Graph Discovery Queries")
    print("   (Use these to understand the actual structure of your data)")
    for query_def in get_discovery_queries():
        result = execute_sparql_query(
            config_id,
            query_def["query"],
            "SELECT",
            query_def["description"]
        )
        if result:
            print_query_results(result, max_rows=15)
        print()
    
    # Summary
    print_section("Test Suite Complete")
    print("✅ All test queries have been executed")
    print(f"\nTo run individual queries, use the execute_sparql_query function")
    print(f"with config_id: {config_id}")
    print("\n💡 Tip: Review the Discovery Queries section to understand")
    print("   the actual structure of your knowledge graph data.")


def main():
    """Main entry point"""
    try:
        run_test_suite(CONFIG_ID)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

