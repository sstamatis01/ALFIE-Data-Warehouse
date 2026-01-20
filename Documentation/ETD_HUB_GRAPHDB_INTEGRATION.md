<<<<<<< HEAD
# ETD-Hub to GraphDB Integration Guide

This document explains how to use GraphDB to store and query semantic knowledge graph output from processed ETD-Hub data.

## 🎯 Overview

GraphDB serves as the semantic storage layer for ETD-Hub data, enabling:
- **Semantic Relationships**: Model complex relationships between themes, questions, answers, and experts
- **Advanced Queries**: Use SPARQL to perform sophisticated queries across the knowledge graph
- **Integration**: Connect with other semantic data sources and tools
- **Reasoning**: Leverage semantic reasoning capabilities

## 🔄 Complete Workflow

```
ETD-Hub Forum Data → Semantic Processing → RDF Triples → GraphDB → CASPAR Service
     ↓                    ↓                    ↓           ↓           ↓
Raw Forum Data    AI/ML Processing    Knowledge Graph  Storage    Querying
```

## 📊 Data Transformation

### ETD-Hub Raw Data → RDF Triples

**Original ETD-Hub Structure:**
```json
{
  "Theme": [
    {
      "id": 6,
      "name": "Criminal Justice: COMPAS Recidivism Prediction",
      "description": "The COMPAS system...",
      "expert_id": 5,
      "problem_category": "AI_BIAS"
    }
  ],
  "Question": [
    {
      "id": 14,
      "title": "Example Question",
      "body": "Can a predictive system...",
      "theme_id": 6,
      "expert_id": 5
    }
  ]
}
```

**Transformed to RDF:**
```turtle
@prefix etd: <http://example.org/etd-hub#> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix dc: <http://purl.org/dc/elements/1.1/> .

# Theme as a concept
etd:theme-6 a etd:Theme ;
    dc:title "Criminal Justice: COMPAS Recidivism Prediction" ;
    dc:description "The COMPAS system..." ;
    etd:hasExpert etd:expert-5 ;
    etd:problemCategory "AI_BIAS" .

# Question as a discussion
etd:question-14 a etd:Question ;
    dc:title "Example Question" ;
    dc:description "Can a predictive system..." ;
    etd:belongsToTheme etd:theme-6 ;
    etd:askedBy etd:expert-5 .
```

## 🏗️ ETD-Hub Ontology

### Core Classes
- **etd:Theme**: Case studies and ethical AI topics
- **etd:Question**: Forum discussions and questions
- **etd:Answer**: Expert responses and answers
- **etd:Expert**: User profiles with expertise areas
- **etd:Vote**: Community voting and feedback

### Key Properties
- **etd:hasExpert**: Links themes to experts
- **etd:belongsToTheme**: Links questions to themes
- **etd:answersQuestion**: Links answers to questions
- **etd:askedBy**: Links questions to experts
- **etd:providedBy**: Links answers to experts
- **etd:votedOn**: Links votes to answers

## 🧪 Example Queries

### 1. Get All Themes with Their Categories
```sparql
PREFIX etd: <http://example.org/etd-hub#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT ?theme ?title ?category WHERE {
    ?theme a etd:Theme ;
           dc:title ?title ;
           etd:problemCategory ?category .
}
```

### 2. Find Questions and Their Answers
```sparql
PREFIX etd: <http://example.org/etd-hub#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT ?question ?answer ?questionTitle ?answerText WHERE {
    ?question a etd:Question ;
              dc:title ?questionTitle .
    ?answer a etd:Answer ;
            etd:answersQuestion ?question ;
            dc:description ?answerText .
}
```

### 3. Expert Contribution Analysis
```sparql
PREFIX etd: <http://example.org/etd-hub#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>

SELECT ?expert ?name ?expertise (COUNT(?answer) AS ?answerCount) WHERE {
    ?expert a etd:Expert ;
            foaf:name ?name ;
            etd:areaOfExpertise ?expertise .
    ?answer etd:providedBy ?expert .
}
GROUP BY ?expert ?name ?expertise
ORDER BY DESC(?answerCount)
```

### 4. Voting Patterns Analysis
```sparql
PREFIX etd: <http://example.org/etd-hub#>

SELECT ?answer (AVG(?voteValue) AS ?avgVote) (COUNT(?vote) AS ?voteCount) WHERE {
    ?vote a etd:Vote ;
          etd:votedOn ?answer ;
          etd:voteValue ?voteValue .
}
GROUP BY ?answer
ORDER BY DESC(?avgVote)
```

### 5. Theme Popularity Analysis
```sparql
PREFIX etd: <http://example.org/etd-hub#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT ?theme ?title (COUNT(?question) AS ?questionCount) WHERE {
    ?theme a etd:Theme ;
           dc:title ?title .
    ?question etd:belongsToTheme ?theme .
}
GROUP BY ?theme ?title
ORDER BY DESC(?questionCount)
```

## 🛠️ Implementation Steps

### 1. Create ETD-Hub Repository
```bash
# Using Data Warehouse API
curl -X POST "http://localhost:8000/graphdb/configs?created_by=etd_hub_user" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ETD-Hub Knowledge Graph",
    "description": "Repository for ETD-Hub semantic data",
    "select_endpoint": "http://graphdb:7200/repositories/etd-hub-kg",
    "update_endpoint": "http://graphdb:7200/repositories/etd-hub-kg/statements",
    "username": "admin",
    "password": "admin",
    "repository_name": "etd-hub-kg"
  }'
```

### 2. Insert Ontology
```python
# Using the Data Warehouse API
ontology = """
@prefix etd: <http://example.org/etd-hub#> .
# ... ontology definition ...
"""

query_data = {
    "config_id": "your-config-id",
    "query": ontology,
    "query_type": "INSERT"
}

response = requests.post(
    "http://localhost:8000/graphdb/query",
    json=query_data
)
```

### 3. Insert ETD-Hub Data
```python
# Convert ETD-Hub JSON to RDF
rdf_data = convert_etd_hub_to_rdf(etd_hub_json)

query_data = {
    "config_id": "your-config-id",
    "query": rdf_data,
    "query_type": "INSERT"
}

response = requests.post(
    "http://localhost:8000/graphdb/query",
    json=query_data
)
```

## 🔗 Integration with CASPAR Service

The CASPAR service can now query the ETD-Hub knowledge graph:

```python
# CASPAR service querying ETD-Hub data
def get_related_themes(theme_id):
    query = f"""
    PREFIX etd: <http://example.org/etd-hub#>
    
    SELECT ?relatedTheme ?title WHERE {{
        etd:theme-{theme_id} etd:relatedTo ?relatedTheme .
        ?relatedTheme dc:title ?title .
    }}
    """
    
    response = requests.post(
        "http://localhost:8000/graphdb/query",
        json={
            "config_id": "etd-hub-config-id",
            "query": query,
            "query_type": "SELECT"
        }
    )
    
    return response.json()
```

## 📈 Benefits of GraphDB for ETD-Hub

### 1. **Semantic Relationships**
- Model complex relationships between concepts
- Enable reasoning and inference
- Support for transitive relationships

### 2. **Advanced Querying**
- SPARQL queries across the entire knowledge graph
- Complex joins and aggregations
- Pattern matching and graph traversal

### 3. **Integration Capabilities**
- Connect with other semantic data sources
- Support for linked data principles
- Standard RDF/SPARQL ecosystem

### 4. **Scalability**
- Handle large knowledge graphs
- Efficient storage and retrieval
- Support for distributed queries

### 5. **Analytics and Insights**
- Community analysis (expert contributions, voting patterns)
- Content analysis (theme popularity, question trends)
- Relationship analysis (expert networks, topic connections)

## 🧪 Testing the Integration

Run the example script to test the complete workflow:

```bash
python etd_hub_to_graphdb_example.py
```

This will:
1. Create the ETD-Hub ontology
2. Insert sample data
3. Execute various SPARQL queries
4. Demonstrate the knowledge graph capabilities

## 🎯 Use Cases

### 1. **Content Recommendation**
- Find related themes based on semantic similarity
- Recommend questions to experts based on expertise
- Suggest answers based on voting patterns

### 2. **Community Analysis**
- Identify key experts in specific domains
- Analyze voting patterns and community consensus
- Track knowledge evolution over time

### 3. **Research Support**
- Find all discussions related to a specific AI ethics topic
- Analyze expert opinions across different themes
- Identify knowledge gaps in the community

### 4. **Integration with External Systems**
- Connect with academic databases
- Link to external knowledge bases
- Support for federated queries

## 🔧 Configuration

### GraphDB Configuration
- **Repository**: `etd-hub-kg`
- **Endpoint**: `http://graphdb:7200/repositories/etd-hub-kg`
- **Authentication**: Basic auth (admin/admin)

### Data Warehouse API
- **Config ID**: Use the configuration created for ETD-Hub
- **Query Endpoint**: `/graphdb/query`
- **Test Endpoint**: `/graphdb/configs/{id}/test`

## 📚 Additional Resources

- [GraphDB Documentation](https://www.ontotext.com/products/graphdb/)
- [SPARQL Tutorial](https://www.w3.org/TR/sparql11-query/)
- [RDF Primer](https://www.w3.org/TR/rdf-primer/)
- [ETD-Hub API Documentation](./ETD_HUB_README.md)
- [GraphDB API Documentation](./GRAPHDB_README.md)
=======
# ETD-Hub to GraphDB Integration Guide

This document explains how to use GraphDB to store and query semantic knowledge graph output from processed ETD-Hub data.

## 🎯 Overview

GraphDB serves as the semantic storage layer for ETD-Hub data, enabling:
- **Semantic Relationships**: Model complex relationships between themes, questions, answers, and experts
- **Advanced Queries**: Use SPARQL to perform sophisticated queries across the knowledge graph
- **Integration**: Connect with other semantic data sources and tools
- **Reasoning**: Leverage semantic reasoning capabilities

## 🔄 Complete Workflow

```
ETD-Hub Forum Data → Semantic Processing → RDF Triples → GraphDB → CASPAR Service
     ↓                    ↓                    ↓           ↓           ↓
Raw Forum Data    AI/ML Processing    Knowledge Graph  Storage    Querying
```

## 📊 Data Transformation

### ETD-Hub Raw Data → RDF Triples

**Original ETD-Hub Structure:**
```json
{
  "Theme": [
    {
      "id": 6,
      "name": "Criminal Justice: COMPAS Recidivism Prediction",
      "description": "The COMPAS system...",
      "expert_id": 5,
      "problem_category": "AI_BIAS"
    }
  ],
  "Question": [
    {
      "id": 14,
      "title": "Example Question",
      "body": "Can a predictive system...",
      "theme_id": 6,
      "expert_id": 5
    }
  ]
}
```

**Transformed to RDF:**
```turtle
@prefix etd: <http://example.org/etd-hub#> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix dc: <http://purl.org/dc/elements/1.1/> .

# Theme as a concept
etd:theme-6 a etd:Theme ;
    dc:title "Criminal Justice: COMPAS Recidivism Prediction" ;
    dc:description "The COMPAS system..." ;
    etd:hasExpert etd:expert-5 ;
    etd:problemCategory "AI_BIAS" .

# Question as a discussion
etd:question-14 a etd:Question ;
    dc:title "Example Question" ;
    dc:description "Can a predictive system..." ;
    etd:belongsToTheme etd:theme-6 ;
    etd:askedBy etd:expert-5 .
```

## 🏗️ ETD-Hub Ontology

### Core Classes
- **etd:Theme**: Case studies and ethical AI topics
- **etd:Question**: Forum discussions and questions
- **etd:Answer**: Expert responses and answers
- **etd:Expert**: User profiles with expertise areas
- **etd:Vote**: Community voting and feedback

### Key Properties
- **etd:hasExpert**: Links themes to experts
- **etd:belongsToTheme**: Links questions to themes
- **etd:answersQuestion**: Links answers to questions
- **etd:askedBy**: Links questions to experts
- **etd:providedBy**: Links answers to experts
- **etd:votedOn**: Links votes to answers

## 🧪 Example Queries

### 1. Get All Themes with Their Categories
```sparql
PREFIX etd: <http://example.org/etd-hub#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT ?theme ?title ?category WHERE {
    ?theme a etd:Theme ;
           dc:title ?title ;
           etd:problemCategory ?category .
}
```

### 2. Find Questions and Their Answers
```sparql
PREFIX etd: <http://example.org/etd-hub#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT ?question ?answer ?questionTitle ?answerText WHERE {
    ?question a etd:Question ;
              dc:title ?questionTitle .
    ?answer a etd:Answer ;
            etd:answersQuestion ?question ;
            dc:description ?answerText .
}
```

### 3. Expert Contribution Analysis
```sparql
PREFIX etd: <http://example.org/etd-hub#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>

SELECT ?expert ?name ?expertise (COUNT(?answer) AS ?answerCount) WHERE {
    ?expert a etd:Expert ;
            foaf:name ?name ;
            etd:areaOfExpertise ?expertise .
    ?answer etd:providedBy ?expert .
}
GROUP BY ?expert ?name ?expertise
ORDER BY DESC(?answerCount)
```

### 4. Voting Patterns Analysis
```sparql
PREFIX etd: <http://example.org/etd-hub#>

SELECT ?answer (AVG(?voteValue) AS ?avgVote) (COUNT(?vote) AS ?voteCount) WHERE {
    ?vote a etd:Vote ;
          etd:votedOn ?answer ;
          etd:voteValue ?voteValue .
}
GROUP BY ?answer
ORDER BY DESC(?avgVote)
```

### 5. Theme Popularity Analysis
```sparql
PREFIX etd: <http://example.org/etd-hub#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>

SELECT ?theme ?title (COUNT(?question) AS ?questionCount) WHERE {
    ?theme a etd:Theme ;
           dc:title ?title .
    ?question etd:belongsToTheme ?theme .
}
GROUP BY ?theme ?title
ORDER BY DESC(?questionCount)
```

## 🛠️ Implementation Steps

### 1. Create ETD-Hub Repository
```bash
# Using Data Warehouse API
curl -X POST "http://localhost:8000/graphdb/configs?created_by=etd_hub_user" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ETD-Hub Knowledge Graph",
    "description": "Repository for ETD-Hub semantic data",
    "select_endpoint": "http://graphdb:7200/repositories/etd-hub-kg",
    "update_endpoint": "http://graphdb:7200/repositories/etd-hub-kg/statements",
    "username": "admin",
    "password": "admin",
    "repository_name": "etd-hub-kg"
  }'
```

### 2. Insert Ontology
```python
# Using the Data Warehouse API
ontology = """
@prefix etd: <http://example.org/etd-hub#> .
# ... ontology definition ...
"""

query_data = {
    "config_id": "your-config-id",
    "query": ontology,
    "query_type": "INSERT"
}

response = requests.post(
    "http://localhost:8000/graphdb/query",
    json=query_data
)
```

### 3. Insert ETD-Hub Data
```python
# Convert ETD-Hub JSON to RDF
rdf_data = convert_etd_hub_to_rdf(etd_hub_json)

query_data = {
    "config_id": "your-config-id",
    "query": rdf_data,
    "query_type": "INSERT"
}

response = requests.post(
    "http://localhost:8000/graphdb/query",
    json=query_data
)
```

## 🔗 Integration with CASPAR Service

The CASPAR service can now query the ETD-Hub knowledge graph:

```python
# CASPAR service querying ETD-Hub data
def get_related_themes(theme_id):
    query = f"""
    PREFIX etd: <http://example.org/etd-hub#>
    
    SELECT ?relatedTheme ?title WHERE {{
        etd:theme-{theme_id} etd:relatedTo ?relatedTheme .
        ?relatedTheme dc:title ?title .
    }}
    """
    
    response = requests.post(
        "http://localhost:8000/graphdb/query",
        json={
            "config_id": "etd-hub-config-id",
            "query": query,
            "query_type": "SELECT"
        }
    )
    
    return response.json()
```

## 📈 Benefits of GraphDB for ETD-Hub

### 1. **Semantic Relationships**
- Model complex relationships between concepts
- Enable reasoning and inference
- Support for transitive relationships

### 2. **Advanced Querying**
- SPARQL queries across the entire knowledge graph
- Complex joins and aggregations
- Pattern matching and graph traversal

### 3. **Integration Capabilities**
- Connect with other semantic data sources
- Support for linked data principles
- Standard RDF/SPARQL ecosystem

### 4. **Scalability**
- Handle large knowledge graphs
- Efficient storage and retrieval
- Support for distributed queries

### 5. **Analytics and Insights**
- Community analysis (expert contributions, voting patterns)
- Content analysis (theme popularity, question trends)
- Relationship analysis (expert networks, topic connections)

## 🧪 Testing the Integration

Run the example script to test the complete workflow:

```bash
python etd_hub_to_graphdb_example.py
```

This will:
1. Create the ETD-Hub ontology
2. Insert sample data
3. Execute various SPARQL queries
4. Demonstrate the knowledge graph capabilities

## 🎯 Use Cases

### 1. **Content Recommendation**
- Find related themes based on semantic similarity
- Recommend questions to experts based on expertise
- Suggest answers based on voting patterns

### 2. **Community Analysis**
- Identify key experts in specific domains
- Analyze voting patterns and community consensus
- Track knowledge evolution over time

### 3. **Research Support**
- Find all discussions related to a specific AI ethics topic
- Analyze expert opinions across different themes
- Identify knowledge gaps in the community

### 4. **Integration with External Systems**
- Connect with academic databases
- Link to external knowledge bases
- Support for federated queries

## 🔧 Configuration

### GraphDB Configuration
- **Repository**: `etd-hub-kg`
- **Endpoint**: `http://graphdb:7200/repositories/etd-hub-kg`
- **Authentication**: Basic auth (admin/admin)

### Data Warehouse API
- **Config ID**: Use the configuration created for ETD-Hub
- **Query Endpoint**: `/graphdb/query`
- **Test Endpoint**: `/graphdb/configs/{id}/test`

## 📚 Additional Resources

- [GraphDB Documentation](https://www.ontotext.com/products/graphdb/)
- [SPARQL Tutorial](https://www.w3.org/TR/sparql11-query/)
- [RDF Primer](https://www.w3.org/TR/rdf-primer/)
- [ETD-Hub API Documentation](./ETD_HUB_README.md)
- [GraphDB API Documentation](./GRAPHDB_README.md)
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
