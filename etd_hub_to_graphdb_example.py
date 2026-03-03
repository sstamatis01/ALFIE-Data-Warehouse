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
    
    # Define the ETD-Hub ontology
    ontology = """
    @prefix etd: <http://example.org/etd-hub#> .
    @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix foaf: <http://xmlns.com/foaf/0.1/> .
    @prefix dc: <http://purl.org/dc/elements/1.1/> .
    @prefix schema: <http://schema.org/> .

    # ETD-Hub Ontology
    etd:Theme a owl:Class ;
        rdfs:label "Theme" ;
        rdfs:comment "A case study or ethical AI topic" .

    etd:Question a owl:Class ;
        rdfs:label "Question" ;
        rdfs:comment "A question posed in the forum" .

    etd:Answer a owl:Class ;
        rdfs:label "Answer" ;
        rdfs:comment "An answer provided by an expert" .

    etd:Expert a owl:Class ;
        rdfs:label "Expert" ;
        rdfs:comment "An expert user in the forum" .

    etd:Vote a owl:Class ;
        rdfs:label "Vote" ;
        rdfs:comment "A vote on an answer" .

    # Properties
    etd:hasExpert a owl:ObjectProperty ;
        rdfs:label "has expert" ;
        rdfs:domain etd:Theme ;
        rdfs:range etd:Expert .

    etd:belongsToTheme a owl:ObjectProperty ;
        rdfs:label "belongs to theme" ;
        rdfs:domain etd:Question ;
        rdfs:range etd:Theme .

    etd:answersQuestion a owl:ObjectProperty ;
        rdfs:label "answers question" ;
        rdfs:domain etd:Answer ;
        rdfs:range etd:Question .

    etd:askedBy a owl:ObjectProperty ;
        rdfs:label "asked by" ;
        rdfs:domain etd:Question ;
        rdfs:range etd:Expert .

    etd:providedBy a owl:ObjectProperty ;
        rdfs:label "provided by" ;
        rdfs:domain etd:Answer ;
        rdfs:range etd:Expert .

    etd:votedOn a owl:ObjectProperty ;
        rdfs:label "voted on" ;
        rdfs:domain etd:Vote ;
        rdfs:range etd:Answer .

    etd:votedBy a owl:ObjectProperty ;
        rdfs:label "voted by" ;
        rdfs:domain etd:Vote ;
        rdfs:range etd:Expert .

    etd:problemCategory a owl:DatatypeProperty ;
        rdfs:label "problem category" ;
        rdfs:domain etd:Theme .

    etd:modelCategory a owl:DatatypeProperty ;
        rdfs:label "model category" ;
        rdfs:domain etd:Theme .

    etd:areaOfExpertise a owl:DatatypeProperty ;
        rdfs:label "area of expertise" ;
        rdfs:domain etd:Expert .

    etd:voteValue a owl:DatatypeProperty ;
        rdfs:label "vote value" ;
        rdfs:domain etd:Vote ;
        rdfs:range xsd:integer .
    """
    
    return ontology

def insert_etd_hub_data():
    """Insert sample ETD-Hub data as RDF triples"""
    
    # Sample ETD-Hub data converted to RDF
    sample_data = """
    @prefix etd: <http://example.org/etd-hub#> .
    @prefix foaf: <http://xmlns.com/foaf/0.1/> .
    @prefix dc: <http://purl.org/dc/elements/1.1/> .
    @prefix schema: <http://schema.org/> .

    # Theme: COMPAS Recidivism Prediction
    etd:theme-6 a etd:Theme ;
        dc:title "Criminal Justice: COMPAS Recidivism Prediction" ;
        dc:description "The COMPAS (Correctional Offender Management Profiling for Alternative Sanctions) system by Northpointe is used by U.S. courts to assess defendant recidivism probability. ProPublica's 2016 investigation revealed systematic racial bias in these predictions." ;
        etd:hasExpert etd:expert-5 ;
        etd:problemCategory "AI_BIAS" ;
        etd:modelCategory "Machine_Learning" ;
        etd:domainCategory "Justice" ;
        schema:dateCreated "2025-07-20T08:34:34Z"^^xsd:dateTime .

    # Expert: AI Ethics Researcher
    etd:expert-5 a etd:Expert, foaf:Person ;
        foaf:name "Dr. Sarah Johnson" ;
        etd:areaOfExpertise "AI_ETHICS" ;
        foaf:bio "Leading researcher in AI ethics and algorithmic fairness" ;
        schema:dateJoined "2025-06-26T20:26:54Z"^^xsd:dateTime .

    # Question about COMPAS fairness
    etd:question-14 a etd:Question ;
        dc:title "Example Question" ;
        dc:description "Can a predictive system used in life-altering decisions ever be considered 'fair' if its inner workings are proprietary and its outcomes show systemic racial disparities, even when trained on 'real-world' data?" ;
        etd:belongsToTheme etd:theme-6 ;
        etd:askedBy etd:expert-5 ;
        schema:dateCreated "2025-07-21T00:23:20Z"^^xsd:dateTime .

    # Answer about COMPAS fairness
    etd:answer-11 a etd:Answer ;
        dc:description "A predictive system like COMPAS cannot truly be considered fair if it lacks transparency and exhibits systemic racial disparities; even if trained on 'real-world' data. Fairness in algorithmic decision-making, especially in high-stakes domains like criminal justice, goes beyond technical accuracy; it requires accountability, interpretability, and equity in outcomes." ;
        etd:answersQuestion etd:question-14 ;
        etd:providedBy etd:expert-5 ;
        schema:dateCreated "2025-07-21T00:25:14Z"^^xsd:dateTime .

    # Vote on the answer
    etd:vote-52 a etd:Vote ;
        etd:votedOn etd:answer-11 ;
        etd:votedBy etd:expert-4 ;
        etd:voteValue 1 ;
        schema:dateCreated "2025-07-21T16:49:39Z"^^xsd:dateTime .
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

def main():
    """Main function demonstrating ETD-Hub to GraphDB workflow"""
    print("ETD-Hub to GraphDB Semantic Knowledge Graph Example")
    print("=" * 60)
    
    # Step 1: Insert the ontology
    print("\n1. Creating ETD-Hub Ontology...")
    ontology = create_etd_hub_ontology()
    result = execute_sparql_query(ontology, "INSERT")
    if result and result.get('success'):
        print("✅ Ontology created successfully")
    else:
        print("❌ Failed to create ontology")
        return
    
    # Step 2: Insert sample ETD-Hub data
    print("\n2. Inserting ETD-Hub Data...")
    sample_data = insert_etd_hub_data()
    result = execute_sparql_query(sample_data, "INSERT")
    if result and result.get('success'):
        print("✅ ETD-Hub data inserted successfully")
    else:
        print("❌ Failed to insert data")
        return
    
    # Step 3: Query the knowledge graph
    print("\n3. Querying the Knowledge Graph...")
    
    # Query 1: Get all themes
    print("\n📊 All Themes:")
    query1 = """
    PREFIX etd: <http://example.org/etd-hub#>
    PREFIX dc: <http://purl.org/dc/elements/1.1/>
    
    SELECT ?theme ?title ?category WHERE {
        ?theme a etd:Theme ;
               dc:title ?title ;
               etd:problemCategory ?category .
    }
    """
    result1 = execute_sparql_query(query1)
    if result1 and result1.get('success'):
        print("✅ Themes retrieved successfully")
        print(f"   Execution time: {result1['execution_time']:.3f}s")
    else:
        print("❌ Failed to retrieve themes")
    
    # Query 2: Get questions and their answers
    print("\n❓ Questions and Answers:")
    query2 = """
    PREFIX etd: <http://example.org/etd-hub#>
    PREFIX dc: <http://purl.org/dc/elements/1.1/>
    
    SELECT ?question ?answer ?questionTitle ?answerText WHERE {
        ?question a etd:Question ;
                  dc:title ?questionTitle .
        ?answer a etd:Answer ;
                etd:answersQuestion ?question ;
                dc:description ?answerText .
    }
    """
    result2 = execute_sparql_query(query2)
    if result2 and result2.get('success'):
        print("✅ Questions and answers retrieved successfully")
        print(f"   Execution time: {result2['execution_time']:.3f}s")
    else:
        print("❌ Failed to retrieve questions and answers")
    
    # Query 3: Get expert contributions
    print("\n👨‍💼 Expert Contributions:")
    query3 = """
    PREFIX etd: <http://example.org/etd-hub#>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    
    SELECT ?expert ?name ?expertise (COUNT(?answer) AS ?answerCount) WHERE {
        ?expert a etd:Expert ;
                foaf:name ?name ;
                etd:areaOfExpertise ?expertise .
        ?answer etd:providedBy ?expert .
    }
    GROUP BY ?expert ?name ?expertise
    """
    result3 = execute_sparql_query(query3)
    if result3 and result3.get('success'):
        print("✅ Expert contributions retrieved successfully")
        print(f"   Execution time: {result3['execution_time']:.3f}s")
    else:
        print("❌ Failed to retrieve expert contributions")
    
    # Query 4: Get voting patterns
    print("\n🗳️ Voting Patterns:")
    query4 = """
    PREFIX etd: <http://example.org/etd-hub#>
    
    SELECT ?answer (AVG(?voteValue) AS ?avgVote) (COUNT(?vote) AS ?voteCount) WHERE {
        ?vote a etd:Vote ;
              etd:votedOn ?answer ;
              etd:voteValue ?voteValue .
    }
    GROUP BY ?answer
    """
    result4 = execute_sparql_query(query4)
    if result4 and result4.get('success'):
        print("✅ Voting patterns retrieved successfully")
        print(f"   Execution time: {result4['execution_time']:.3f}s")
    else:
        print("❌ Failed to retrieve voting patterns")
    
    print("\n" + "=" * 60)
    print("ETD-Hub Knowledge Graph Example Complete!")
    print("\n🎯 Benefits of using GraphDB for ETD-Hub data:")
    print("   • Semantic relationships between themes, questions, and answers")
    print("   • Complex queries across the knowledge graph")
    print("   • Integration with other semantic data sources")
    print("   • Support for reasoning and inference")
    print("   • Standard RDF/SPARQL ecosystem compatibility")

if __name__ == "__main__":
    main()
