import sys
from pathlib import Path

# Ensure src is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aiNewReader.db import get_db, init_db

def main():
    print("Initializing database connection...")
    init_db()
    
    with get_db() as conn:
        # 1. Find orphaned articles
        orphaned_count = conn.execute("""
            SELECT COUNT(*) FROM articles 
            WHERE feed_id NOT IN (SELECT id FROM feeds)
        """).fetchone()[0]
        
        if orphaned_count == 0:
            print("No orphaned articles found (all articles belong to a known feed).")
            return
            
        print(f"Found {orphaned_count} orphaned articles with no matching feed in the database.")
        
        confirm = input("\nDelete these orphaned articles? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return
            
        print("\nDeleting records...")
        
        # Cleanup related data first for orphaned articles
        conn.execute("""
            DELETE FROM feedback 
            WHERE article_id IN (SELECT id FROM articles WHERE feed_id NOT IN (SELECT id FROM feeds))
        """)
        
        # Now delete articles
        cur = conn.execute("""
            DELETE FROM articles 
            WHERE feed_id NOT IN (SELECT id FROM feeds)
        """)
        
        print(f"   Removed {cur.rowcount} orphaned articles.")
        print("   Done!")

    print("\nVacuuming database...")
    with get_db() as conn:
        conn.isolation_level = None
        conn.execute("VACUUM")
    print("   Done!")

if __name__ == "__main__":
    main()
