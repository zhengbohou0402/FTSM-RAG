import threading


# Shared process-local lock for writes to the Chroma store and ingestion manifest.
indexing_lock = threading.Lock()
