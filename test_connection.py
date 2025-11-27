#!/usr/bin/env python3
"""
Test Neo4j connection and display database information
"""
import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

try:
    from neo4j import GraphDatabase
    from wikiquote_voice.config import Config
    
    print("🔧 Testing Neo4j Connection...")
    print(f"📍 URI: {Config.NEO4J_URI}")
    print(f"👤 Username: {Config.NEO4J_USERNAME}")
    print(f"🔑 Password: {'*' * len(Config.NEO4J_PASSWORD)}")
    
    # Test connection
    driver = GraphDatabase.driver(
        Config.NEO4J_URI, 
        auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD)
    )
    
    print("\n🔄 Verifying connectivity...")
    driver.verify_connectivity()
    print("✅ Connection successful!")
    
    # Get database info
    with driver.session() as session:
        print("\n📊 Database Information:")
        
        # Get Neo4j version
        try:
            result = session.run("CALL dbms.components() YIELD name, versions, edition")
            for record in result:
                print(f"   • {record['name']}: {record['versions'][0]} ({record['edition']})")
        except Exception as e:
            print(f"   • Version info not available: {e}")
        
        # Get current database name
        try:
            result = session.run("CALL db.name()")
            db_name = result.single()['name']
            print(f"   • Current database: {db_name}")
        except Exception as e:
            print(f"   • Database name not available: {e}")
        
        # Check if there are any existing nodes
        try:
            result = session.run("MATCH (n) RETURN count(n) as node_count")
            node_count = result.single()['node_count']
            print(f"   • Existing nodes: {node_count:,}")
        except Exception as e:
            print(f"   • Node count not available: {e}")
    
    driver.close()
    print("\n🎉 Neo4j is ready for data population!")
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("💡 Make sure neo4j driver is installed: pip install neo4j")
except Exception as e:
    print(f"❌ Connection Error: {e}")
    print("\n🔧 Troubleshooting:")
    print("   1. Check if Neo4j Desktop is running")
    print("   2. Verify your database is started in Neo4j Desktop")
    print("   3. Check your credentials in .env file")
    print("   4. Try connecting via Neo4j Browser first")
