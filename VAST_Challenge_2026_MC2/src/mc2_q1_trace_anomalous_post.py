"""
VAST Challenge 2026 MC2 - Question 1: Trace Anomalous Post
Traces the complete chain of events that led to the anomalous SaidIt post by John Windward
"""

import json
from datetime import datetime
from collections import defaultdict, Counter

# OpenTrace integration - will be added when module is available
try:
    from opentrace.mcp_server import get_server
    OPENTRACE_AVAILABLE = True
except ImportError:
    OPENTRACE_AVAILABLE = False
    print("Note: OpenTrace module not available - continuing without workflow tracking")

def load_data(data_path):
    """Load MC2 data"""
    with open(data_path, 'r') as f:
        return json.load(f)

def find_event_by_id(data, event_id):
    """Find event by ID"""
    for event in data['events']:
        if event.get('id') == event_id:
            return event
    return None

def find_events_by_time_range(data, start_ts, end_ts):
    """Find events in time range"""
    return [e for e in data['events'] if start_ts <= e.get('when', 0) < end_ts]

def find_events_by_party(data, party_name):
    """Find events involving a specific party"""
    return [e for e in data['events'] if party_name in str(e.get('parties', []))]

def trace_content_source_chain(data, content_source):
    """
    Trace the chain of events related to a content source file.
    Returns chronological chain from file creation to posting.
    """
    chain = []

    # Step 1: Find file creation
    for event in data['events']:
        if event.get('short_name') == 'create_file':
            details = event.get('details', {})
            if content_source in details.get('target', ''):
                chain.append(('create_file', event))
                break

    # Step 2: Find all events related to this file
    related_events = []
    for event in data['events']:
        details_str = str(event.get('details', ''))
        if content_source.replace('.txt', '') in details_str:
            related_events.append(event)

    # Sort chronologically
    related_events.sort(key=lambda x: x['when'])

    # Step 3: Find the SaidIt post using this content
    for event in data['events']:
        if event.get('short_name') == 'saidit_post':
            details = event.get('details', {})
            if details.get('content_source') == content_source:
                chain.append(('anomalous_post', event))
                break

    return chain, related_events

def analyze_task_delegations(data, target_event_id, window_hours=24):
    """Analyze task delegations leading to target event"""
    target_event = find_event_by_id(data, target_event_id)
    if not target_event:
        return []

    target_ts = target_event['when']
    window_start = target_ts - (window_hours * 3600)
    window_end = target_ts + (window_hours * 3600)

    # Find queue_subordinate_task events in window
    delegations = []
    for event in data['events']:
        if window_start <= event['when'] < window_end:
            if event.get('short_name') == 'queue_subordinate_task':
                details = event.get('details', {})
                if 'task' in details and 'args' in details:
                    delegations.append(event)

    delegations.sort(key=lambda x: x['when'])
    return delegations

def generate_timeline(chain, related_events):
    """Generate a timeline summary"""
    timeline = []
    for event in related_events:
        dt = datetime.fromtimestamp(event['when'])
        timeline.append({
            'timestamp': event['when'],
            'datetime': str(dt),
            'action': event.get('short_name'),
            'parties': event.get('parties', []),
            'details': event.get('details'),
            'id': event.get('id')
        })
    return timeline

def main():
    # Initialize OpenTrace (if available)
    server = None
    if OPENTRACE_AVAILABLE:
        server = get_server()

    # Load data
    data_path = 'VAST_Challenge_2026_MC2（1）/VAST_Challenge_2026_MC2/MC2 data.json'
    data = load_data(data_path)

    print("=" * 80)
    print("VAST Challenge 2026 MC2 - Question 1: Anomalous Post Analysis")
    print("=" * 80)

    # The anomalous post
    anomalous_post_id = 373902
    anomalous_post = find_event_by_id(data, anomalous_post_id)

    print(f"\nANOMALOUS POST:")
    print(f"  Date/Time: {datetime.fromtimestamp(anomalous_post['when'])}")
    print(f"  Action: {anomalous_post['short_name']}")
    print(f"  Parties: {anomalous_post.get('parties', [])}")
    print(f"  Content Source: {anomalous_post.get('details', {}).get('content_source')}")

    content_source = 'SwiftWren.txt'

    # Trace the chain
    print(f"\nTRACING CHAIN FOR: {content_source}")
    print("-" * 80)

    chain, related_events = trace_content_source_chain(data, content_source)

    print(f"\nChain Overview:")
    for step_type, event in chain:
        dt = datetime.fromtimestamp(event['when'])
        print(f"  {step_type.upper()}: {dt} | Event ID: {event['id']}")

    print(f"\nTotal related events: {len(related_events)}")

    # Generate detailed timeline
    timeline = generate_timeline(chain, related_events)

    # Analyze event types
    event_types = Counter(e['short_name'] for e in related_events)
    print(f"\nEvent Type Distribution:")
    for event_type, count in event_types.most_common():
        print(f"  {event_type}: {count}")

    # Analyze participants
    all_parties = []
    for event in related_events:
        all_parties.extend(event.get('parties', []))

    party_counts = Counter(all_parties)
    print(f"\nTop Participants:")
    for party, count in party_counts.most_common(10):
        print(f"  {party}: {count}")

    # Save results
    output = {
        'anomalous_post': {
            'event_id': anomalous_post_id,
            'timestamp': anomalous_post['when'],
            'datetime': str(datetime.fromtimestamp(anomalous_post['when'])),
            'action': anomalous_post['short_name'],
            'parties': anomalous_post.get('parties', []),
            'content_source': content_source
        },
        'chain_summary': [
            {
                'step': step,
                'event_id': event['id'],
                'timestamp': event['when'],
                'datetime': str(datetime.fromtimestamp(event['when']))
            }
            for step, event in chain
        ],
        'timeline': timeline,
        'event_types': dict(event_types),
        'participants': dict(party_counts)
    }

    output_path = 'VAST_Challenge_2026_MC2/src/q1_anomalous_post_analysis.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    # Record in OpenTrace (if available)
    if OPENTRACE_AVAILABLE:
        server = get_server()
        session_id = 'session_20260724_173543_86c11569-aa41-465e-8f07-95b99ba00c16'

        # Record the analysis step
        server.record_prov_relation(
            session_id=session_id,
            entities=[
                {"id": "input_data", "entity_type": "dataset", "location": data_path, "attributes": {"events": len(data['events'])}},
                {"id": "analysis_output", "entity_type": "analysis", "location": output_path, "attributes": {"related_events": len(related_events)}}
            ],
            activities=[
                {"id": "trace_chain", "activity_type": "data_analysis", "description": "Trace anomalous post chain to SwiftWren.txt", "attributes": {}}
            ],
            agents=[
                {"id": "analyst", "agent_type": "python_script", "name": "mc2_q1_trace_anomalous_post", "attributes": {}}
            ],
            relations=[
                ("trace_chain", "input_data", "used"),
                ("analysis_output", "trace_chain", "wasGeneratedBy"),
                ("trace_chain", "analyst", "wasAssociatedWith"),
                ("analysis_output", "input_data", "wasDerivedFrom")
            ]
        )
        print("\nOpenTrace: Analysis recorded")
    else:
        print("\nOpenTrace: Skipped (module not available)")

    return output

if __name__ == "__main__":
    result = main()
