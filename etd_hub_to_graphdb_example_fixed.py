#!/usr/bin/env python3
"""
Example script showing how to store ETD-Hub semantic knowledge graph data in GraphDB
"""

import requests
import json
from datetime import datetime

API_BASE_URL = "http://localhost:8000"
GRAPHDB_CONFIG_ID = "68f75db5ebc917f006e16fb9"  # ETD-Hub Knowledge Graph config

def create_etd_hub_ontology():
    """Create the ETD-Hub ontology in GraphDB"""
    
    # Define the ETD-Hub ontology using SPARQL INSERT DATA syntax
    ontology = """
    PREFIX etd: <http://example.org/etd-hub#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    INSERT DATA {
        # ETD-Hub Ontology Classes
        etd:Theme rdf:type owl:Class ;
            rdfs:label "Theme" ;
            rdfs:comment "A case study or ethical AI topic" .

        etd:Question rdf:type owl:Class ;
            rdfs:label "Question" ;
            rdfs:comment "A question posed in the forum" .

        etd:Answer rdf:type owl:Class ;
            rdfs:label "Answer" ;
            rdfs:comment "An answer provided by an expert" .

        etd:Expert rdf:type owl:Class ;
            rdfs:label "Expert" ;
            rdfs:comment "An expert user in the forum" .

        etd:Vote rdf:type owl:Class ;
            rdfs:label "Vote" ;
            rdfs:comment "A vote on an answer" .

        # Properties
        etd:hasExpert rdf:type owl:ObjectProperty ;
            rdfs:label "has expert" ;
            rdfs:domain etd:Theme ;
            rdfs:range etd:Expert .

        etd:belongsToTheme rdf:type owl:ObjectProperty ;
            rdfs:label "belongs to theme" ;
            rdfs:domain etd:Question ;
            rdfs:range etd:Theme .

        etd:answersQuestion rdf:type owl:ObjectProperty ;
            rdfs:label "answers question" ;
            rdfs:domain etd:Answer ;
            rdfs:range etd:Question .

        etd:askedBy rdf:type owl:ObjectProperty ;
            rdfs:label "asked by" ;
            rdfs:domain etd:Question ;
            rdfs:range etd:Expert .

        etd:providedBy rdf:type owl:ObjectProperty ;
            rdfs:label "provided by" ;
            rdfs:domain etd:Answer ;
            rdfs:range etd:Expert .

        etd:votedOn rdf:type owl:ObjectProperty ;
            rdfs:label "voted on" ;
            rdfs:domain etd:Vote ;
            rdfs:range etd:Answer .

        etd:votedBy rdf:type owl:ObjectProperty ;
            rdfs:label "voted by" ;
            rdfs:domain etd:Vote ;
            rdfs:range etd:Expert .

        # Data properties
        etd:name rdf:type owl:DatatypeProperty ;
            rdfs:label "name" ;
            rdfs:domain etd:Theme ;
            rdfs:range rdfs:Literal .

        etd:description rdf:type owl:DatatypeProperty ;
            rdfs:label "description" ;
            rdfs:domain etd:Theme ;
            rdfs:range rdfs:Literal .

        etd:title rdf:type owl:DatatypeProperty ;
            rdfs:label "title" ;
            rdfs:domain etd:Question ;
            rdfs:range rdfs:Literal .

        etd:views rdf:type owl:DatatypeProperty ;
            rdfs:label "views" ;
            rdfs:domain etd:Theme ;
            rdfs:range xsd:integer .

        etd:voteValue rdf:type owl:DatatypeProperty ;
            rdfs:label "vote value" ;
            rdfs:domain etd:Vote ;
            rdfs:range xsd:integer .

        etd:createdAt rdf:type owl:DatatypeProperty ;
            rdfs:label "created at" ;
            rdfs:domain etd:Theme ;
            rdfs:range xsd:dateTime .

        etd:problemCategory rdf:type owl:DatatypeProperty ;
            rdfs:label "problem category" ;
            rdfs:domain etd:Theme ;
            rdfs:range rdfs:Literal .

        etd:modelCategory rdf:type owl:DatatypeProperty ;
            rdfs:label "model category" ;
            rdfs:domain etd:Theme ;
            rdfs:range rdfs:Literal .

        etd:areaOfExpertise rdf:type owl:DatatypeProperty ;
            rdfs:label "area of expertise" ;
            rdfs:domain etd:Expert ;
            rdfs:range rdfs:Literal .
    }
    """
    
    return ontology

def insert_etd_hub_data():
    """Insert sample ETD-Hub data as RDF triples"""
    
    # Sample ETD-Hub data converted to RDF using SPARQL INSERT DATA
    sample_data = """
    PREFIX etd: <http://example.org/etd-hub#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    INSERT DATA {
        # Sample Theme
        etd:theme1 rdf:type etd:Theme ;
            etd:name "Criminal Justice: COMPAS Recidivism Prediction" ;
            etd:description "The COMPAS system by Northpointe is used by U.S. courts to assess defendant recidivism probability." ;
            etd:views 0 ;
            etd:problemCategory "AI BIAS" ;
            etd:modelCategory "Machine Learning" ;
            etd:createdAt "2025-07-20T08:34:34Z"^^xsd:dateTime ;
            etd:hasExpert etd:expert1 .

        # Sample Expert
        etd:expert1 rdf:type etd:Expert ;
            etd:areaOfExpertise "NGO" ;
            rdfs:label "Expert 1" .

        # Sample Question
        etd:question1 rdf:type etd:Question ;
            etd:title "Example Question" ;
            etd:description "Can a predictive system used in life-altering decisions ever be considered 'fair'?" ;
            etd:views 123 ;
            etd:createdAt "2025-07-21T00:23:20.272Z"^^xsd:dateTime ;
            etd:belongsToTheme etd:theme1 ;
            etd:askedBy etd:expert1 .

        # Sample Answer
        etd:answer1 rdf:type etd:Answer ;
            etd:description "A predictive system like COMPAS cannot truly be considered fair if it lacks transparency and exhibits systemic racial disparities." ;
            etd:createdAt "2025-07-21T00:25:14.275Z"^^xsd:dateTime ;
            etd:answersQuestion etd:question1 ;
            etd:providedBy etd:expert1 .

        # Sample Vote
        etd:vote1 rdf:type etd:Vote ;
            etd:voteValue 1 ;
            etd:createdAt "2025-07-21T16:49:39.950Z"^^xsd:dateTime ;
            etd:votedOn etd:answer1 ;
            etd:votedBy etd:expert1 .
    }
    """
    
    return sample_data

def execute_sparql_query(query, query_type="SELECT"):
    """Execute a SPARQL query against GraphDB"""
    try:
        query_data = {
            "config_id": GRAPHDB_CONFIG_ID,
            "query": query,
            "query_type": query_type
        }
        
        print(f"🔍 Executing {query_type} query...")
        print(f"   Config ID: {GRAPHDB_CONFIG_ID}")
        print(f"   Query length: {len(query)} characters")
        
        response = requests.post(
            f"{API_BASE_URL}/graphdb/query",
            json=query_data
        )
        
        print(f"   Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   Success: {result.get('success', 'Unknown')}")
            if result.get('error'):
                print(f"   Error: {result['error']}")
            return result
        else:
            print(f"❌ Query failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error executing query: {e}")
        import traceback
        traceback.print_exc()
        return None

def query_etd_hub_data():
    """Query the ETD-Hub data from GraphDB"""
    
    # Query 1: Get all themes
    themes_query = """
    PREFIX etd: <http://example.org/etd-hub#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    
    SELECT ?theme ?name ?description ?views WHERE {
        ?theme rdf:type etd:Theme .
        ?theme etd:name ?name .
        ?theme etd:description ?description .
        ?theme etd:views ?views .
    }
    """
    
    # Query 2: Get questions with their themes
    questions_query = """
    PREFIX etd: <http://example.org/etd-hub#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    
    SELECT ?question ?title ?themeName WHERE {
        ?question rdf:type etd:Question .
        ?question etd:title ?title .
        ?question etd:belongsToTheme ?theme .
        ?theme etd:name ?themeName .
    }
    """
    
    # Query 3: Get answers with their questions and experts
    answers_query = """
    PREFIX etd: <http://example.org/etd-hub#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    
    SELECT ?answer ?description ?questionTitle ?expertArea WHERE {
        ?answer rdf:type etd:Answer .
        ?answer etd:description ?description .
        ?answer etd:answersQuestion ?question .
        ?question etd:title ?questionTitle .
        ?answer etd:providedBy ?expert .
        ?expert etd:areaOfExpertise ?expertArea .
    }
    """
    
    print("\n📊 Querying ETD-Hub Data from GraphDB...")
    print("=" * 50)
    
    # Execute queries
    print("\n1. Themes:")
    themes_result = execute_sparql_query(themes_query, "SELECT")
    if themes_result and themes_result.get('success'):
        bindings = themes_result.get('data', {}).get('results', {}).get('bindings', [])
        for binding in bindings:
            name = binding.get('name', {}).get('value', 'Unknown')
            views = binding.get('views', {}).get('value', '0')
            print(f"   • {name} (Views: {views})")
    
    print("\n2. Questions:")
    questions_result = execute_sparql_query(questions_query, "SELECT")
    if questions_result and questions_result.get('success'):
        bindings = questions_result.get('data', {}).get('results', {}).get('bindings', [])
        for binding in bindings:
            title = binding.get('title', {}).get('value', 'Unknown')
            theme = binding.get('themeName', {}).get('value', 'Unknown')
            print(f"   • {title} (Theme: {theme})")
    
    print("\n3. Answers:")
    answers_result = execute_sparql_query(answers_query, "SELECT")
    if answers_result and answers_result.get('success'):
        bindings = answers_result.get('data', {}).get('results', {}).get('bindings', [])
        for binding in bindings:
            question = binding.get('questionTitle', {}).get('value', 'Unknown')
            expert = binding.get('expertArea', {}).get('value', 'Unknown')
            print(f"   • Answer to '{question}' by {expert} expert")

def main():
    """Main function to demonstrate ETD-Hub to GraphDB integration"""
    
    print("ETD-Hub to GraphDB Semantic Knowledge Graph Example")
    print("=" * 60)
    
    # Step 1: Create ontology
    print("\n1. Creating ETD-Hub Ontology...")
    ontology = create_etd_hub_ontology()
    result = execute_sparql_query(ontology, "INSERT")
    
    if result and result.get('success'):
        print("✅ Ontology created successfully")
    else:
        print("❌ Failed to create ontology")
        return
    
    # Step 2: Insert sample data
    print("\n2. Inserting ETD-Hub Data...")
    sample_data = insert_etd_hub_data()
    result = execute_sparql_query(sample_data, "INSERT")
    
    if result and result.get('success'):
        print("✅ ETD-Hub data inserted successfully")
    else:
        print("❌ Failed to insert ETD-Hub data")
        return
    
    # Step 3: Query the data
    print("\n3. Querying ETD-Hub Data...")
    query_etd_hub_data()
    
    print("\n🎉 ETD-Hub to GraphDB integration completed successfully!")
    print("\nYou can now:")
    print("• Query the semantic knowledge graph using SPARQL")
    print("• Explore relationships between themes, questions, answers, and experts")
    print("• Build AI applications on top of the structured knowledge")

if __name__ == "__main__":
    main()
