#!/usr/bin/env python3
"""Check Neo4j connectivity and print basic database information."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    try:
        from neo4j import GraphDatabase
        from wikiquote_voice.config import Config

        print("Testing Neo4j connection")
        print(f"URI: {Config.NEO4J_URI}")
        print(f"Username: {Config.NEO4J_USERNAME}")
        print(f"Password: {'*' * len(Config.NEO4J_PASSWORD)}")

        driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USERNAME, Config.NEO4J_PASSWORD),
        )
        driver.verify_connectivity()
        print("Connection successful")

        with driver.session() as session:
            try:
                result = session.run("CALL dbms.components() YIELD name, versions, edition")
                for record in result:
                    print(f"{record['name']}: {record['versions'][0]} ({record['edition']})")
            except Exception as exc:
                print(f"Version info unavailable: {exc}")

            try:
                result = session.run("CALL db.name()")
                print(f"Database: {result.single()['name']}")
            except Exception as exc:
                print(f"Database name unavailable: {exc}")

            try:
                result = session.run("MATCH (n) RETURN count(n) AS node_count")
                print(f"Existing nodes: {result.single()['node_count']:,}")
            except Exception as exc:
                print(f"Node count unavailable: {exc}")

        driver.close()
    except ImportError as exc:
        print(f"Import error: {exc}")
        print("Install the Neo4j driver with: pip install neo4j")
    except Exception as exc:
        print(f"Connection error: {exc}")
        print("Check that Neo4j is running and that .env contains valid credentials.")


if __name__ == "__main__":
    main()
