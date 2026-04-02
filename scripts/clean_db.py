import sys
from pathlib import Path

# Ensure src is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aiNewReader.db import get_db, init_db
from aiNewReader.cleaner import clean_paywalls

def main():
    print("Initializing database connection...")
    init_db()
    
    print("\n1. Running cleaner to flag paywalled/low-quality articles...")
    stats = clean_paywalls(dry_run=False)
    print(f"   Flagged {stats.get('deleted', 0)} paywalled/short articles.")
    
    with get_db() as conn:
        # Ensure foreign keys are enforced for cascading deletes
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Delete explicitly excluded/paywalled articles
        cur = conn.execute("DELETE FROM articles WHERE excluded_post_audit = 1")
        excluded_deleted = cur.rowcount
        
        # Delete duplicate articles
        cur = conn.execute("DELETE FROM articles WHERE dedup_status != 'original'")
        duplicates_deleted = cur.rowcount
        
        # Manually clean up any orphaned tags or feedback (fallback if CASCADE was off during creation)
        conn.execute("DELETE FROM article_tags WHERE article_id NOT IN (SELECT id FROM articles)")
        conn.execute("DELETE FROM feedback WHERE article_id NOT IN (SELECT id FROM articles)")
        
        print(f"\n2. Deleting records permanently from database...")
        print(f"   - Removed {excluded_deleted} excluded/paywalled articles.")
        print(f"   - Removed {duplicates_deleted} duplicate articles.")
        
        total = excluded_deleted + duplicates_deleted
        print(f"\n   Total articles permanently removed: {total}")
        
    print("\n3. Vacuuming database to reclaim disk space...")
    with get_db() as conn:
        conn.isolation_level = None  # Disable auto-transaction
        conn.execute("VACUUM")
    print("   Done!")

if __name__ == "__main__":
    main()
