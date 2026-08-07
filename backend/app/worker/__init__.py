"""Celery worker package for Konverse.

Purpose: move slow work (document parsing, chunking, embedding, vector
upsert — Phase 3) off the API request path. Scaling model: you add *worker*
replicas to ingest faster, independently of the API replicas that serve chat.
"""