import pytest
import psycopg2
from clintrial_agent.data.db import get_db_connection, get_readonly_db_connection

def test_db_connection_pool():
    """Test getting and closing a pooled database connection."""
    conn = get_db_connection()
    assert conn is not None
    cur = conn.cursor()
    cur.execute("SELECT 1;")
    res = cur.fetchone()
    assert res[0] == 1
    cur.close()
    conn.close()

def test_readonly_db_privileges():
    """Test that clintrial_readonly user can SELECT but CANNOT DELETE or MUTATE."""
    conn = get_readonly_db_connection()
    assert conn is not None
    cur = conn.cursor()
    
    # 1. SELECT query must succeed
    cur.execute("SELECT count(*) FROM ctgov.studies;")
    count = cur.fetchone()[0]
    assert count > 0
    
    # 2. DELETE query must be rejected by PostgreSQL permissions
    with pytest.raises((psycopg2.errors.InsufficientPrivilege, psycopg2.Error)):
        cur.execute("DELETE FROM ctgov.studies WHERE nct_id = 'NONEXISTENT_TEST_ID';")
    
    conn.close()
