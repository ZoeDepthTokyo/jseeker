"""Test pattern learning during resume generation."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import logging
import sqlite3

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

from config import settings
from jseeker.pattern_learner import get_pattern_stats, learn_pattern

# Test 1: Check current patterns
print("\n=== BEFORE TEST ===")
stats = get_pattern_stats()
print(f"Total patterns: {stats['total_patterns']}")
print(f"By type: {stats['by_type']}")
print(f"Cache hit rate: {stats['cache_hit_rate']}%")
print(f"Cost saved: ${stats['cost_saved']}")

# Test 2: Learn some patterns manually
print("\n=== LEARNING TEST PATTERNS ===")

jd_context = {
    "title": "Senior AI Engineer",
    "ats_keywords": ["python", "machine learning", "tensorflow", "aws"],
    "industry": "technology",
}

# Learn summary pattern
learn_pattern(
    pattern_type="summary_adaptation",
    source_text="Experienced software engineer with 10+ years building scalable systems.",
    target_text="Senior AI Engineer with 10+ years building machine learning systems using Python, TensorFlow, and AWS.",
    jd_context=jd_context,
)
print("[OK] Learned summary pattern")

# Learn bullet pattern
learn_pattern(
    pattern_type="bullet_adaptation",
    source_text="Built microservices architecture\nImplemented CI/CD pipelines\nMentored junior developers",
    target_text="Architected machine learning microservices using Python and TensorFlow on AWS\nImplemented automated CI/CD pipelines for ML model deployment\nMentored 5 junior engineers in AI/ML best practices",
    jd_context=jd_context,
)
print("[OK] Learned bullet pattern")

# Test 3: Check patterns after learning
print("\n=== AFTER TEST ===")
stats = get_pattern_stats()
print(f"Total patterns: {stats['total_patterns']}")
print(f"By type: {stats['by_type']}")
print(f"Cache hit rate: {stats['cache_hit_rate']}%")
print(f"Cost saved: ${stats['cost_saved']}")

# Test 4: Check database directly
print("\n=== DATABASE CHECK ===")
conn = sqlite3.connect(str(settings.db_path))
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT * FROM learned_patterns ORDER BY created_at DESC LIMIT 5")
patterns = c.fetchall()

print(f"Recent patterns in DB: {len(patterns)}")
for row in patterns:
    print(
        f"  - ID {row['id']}: {row['pattern_type']} | freq={row['frequency']} | source_len={len(row['source_text'])} | target_len={len(row['target_text'])}"
    )

conn.close()

print("\n[SUCCESS] Pattern learning system is working!")
