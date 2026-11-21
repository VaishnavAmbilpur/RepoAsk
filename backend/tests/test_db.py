import os
from app.db import get_db, init_db

def test_db_init_and_tables():
    """Verify that libSQL initializes and tables can be written to."""
    init_db()
    
    client = get_db()
    
    # Insert a dummy repository
    client.execute(
        "INSERT OR REPLACE INTO repositories (id, owner, name, url) VALUES (?, ?, ?, ?)",
        ["repo_1", "fastapi", "fastapi", "https://github.com/fastapi/fastapi"]
    )
    
    # Query it back
    result = client.execute("SELECT owner, name FROM repositories WHERE id = ?", ["repo_1"])
    
    assert len(result.rows) == 1
    assert result.rows[0][0] == "fastapi"
    assert result.rows[0][1] == "fastapi"
    
    client.close()