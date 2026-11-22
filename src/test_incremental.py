
import pandas as pd

# Simulate existing DWH IDs
existing_ids = set(range(1, 10000))

# Simulate the same source records plus one new record
source_ids = list(range(1, 10000)) + [10000]

new_ids = [
    item_id for item_id in source_ids
    if item_id not in existing_ids
]

print("Existing IDs:", len(existing_ids))
print("Source rows:", len(source_ids))
print("New IDs to insert:", len(new_ids))
print("New ID:", new_ids)
