# audit_segment_usage.py
from database import get_unrefined_segments, get_refined_segments
import json

def audit_segment_integrity():
    print("Auditing segment integrity...\n")

    unrefined_ids = [seg['id'] for seg in get_unrefined_segments()]
    print(f"🔍 Unrefined Segment IDs: {sorted(unrefined_ids)}")

    refined = get_refined_segments()
    all_used_ids = set()
    duplicates = set()

    for ref in refined:
        source = ref['source_segments']
        if not source:
            continue
        try:
            raw_ids = json.loads(source)
            for rid in raw_ids:
                if rid in all_used_ids:
                    duplicates.add(rid)
                all_used_ids.add(rid)
        except Exception as e:
            print(f"⚠️ Error decoding source_segments for refined id {ref['id']}: {e}")

    print(f"\n✅ Total Used Segment IDs: {len(all_used_ids)}")
    print(f"⚠️ Duplicate Raw Segment IDs Across Refined Segments: {sorted(duplicates)}" if duplicates else "✔️ No duplicate raw segments in refined data.")

    reused_unrefined = [rid for rid in unrefined_ids if rid in all_used_ids]
    if reused_unrefined:
        print(f"\n🛑 THESE RAW SEGMENTS ARE UNREFINED *AND* ALREADY USED: {reused_unrefined}")
    else:
        print("✔️ All unrefined segments are clean (not reused).")

if __name__ == "__main__":
    audit_segment_integrity()
