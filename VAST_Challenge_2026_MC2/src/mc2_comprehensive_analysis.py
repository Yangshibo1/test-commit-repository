"""
VAST Challenge 2026 MC2 - Comprehensive Analysis
Answers all background questions through systematic data analysis
"""

import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter

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

def find_events_by_pattern(data, pattern_key, pattern_value):
    """Find events matching a pattern in details"""
    results = []
    for event in data['events']:
        details = event.get('details', {})
        if details.get(pattern_key) == pattern_value:
            results.append(event)
        # Also check nested details
        elif pattern_value in str(details):
            results.append(event)
    return results

def analyze_content_origin(data, content_source):
    """
    Q2: What do the posts "mean"? What is the origin of their contents?
    """
    print(f"\n{'='*80}")
    print(f"Q2: Analyzing Content Origin - {content_source}")
    print(f"{'='*80}")

    # Find creation event
    creation_events = []
    for event in data['events']:
        if event.get('short_name') == 'create_file':
            details = event.get('details', {})
            if content_source in details.get('target', ''):
                creation_events.append(event)

    # Find related instruction files
    instruction_events = []
    for event in data['events']:
        details = event.get('details', {})
        details_str = str(details)
        if 'instruction' in details_str.lower() and content_source.replace('.txt', '') in details_str:
            instruction_events.append(event)

    print(f"\nCreation Events: {len(creation_events)}")
    for event in creation_events:
        dt = datetime.fromtimestamp(event['when'])
        print(f"  {dt} | {event['short_name']} | Parties: {event.get('parties', [])}")
        print(f"    Details: {event.get('details')}")

    print(f"\nRelated Instruction Events: {len(instruction_events)}")
    for event in instruction_events[:10]:
        dt = datetime.fromtimestamp(event['when'])
        print(f"  {dt} | {event['short_name']} | Parties: {event.get('parties', [])}")
        print(f"    Details: {event.get('details')}")

    return creation_events, instruction_events

def find_similar_post_patterns(data):
    """
    Q5: Investigate historic system behavior for similar anomalous patterns
    """
    print(f"\n{'='*80}")
    print("Q5: Finding Similar Anomalous Patterns")
    print(f"{'='*80}")

    # Look for all SaidIt posts with content_source from .txt files
    txt_posts = []
    for event in data['events']:
        if event.get('short_name') in ['saidit_post', 'post_saidit']:
            details = event.get('details', {})
            content_source = details.get('content_source', '')
            if content_source.endswith('.txt') and content_source != '':
                txt_posts.append(event)

    print(f"\nFound {len(txt_posts)} SaidIt posts from .txt files")

    # Group by content source
    by_source = defaultdict(list)
    for post in txt_posts:
        details = post.get('details', {})
        source = details.get('content_source', 'unknown')
        by_source[source].append(post)

    print(f"\nPosts by content source:")
    for source, posts in by_source.items():
        print(f"  {source}: {len(posts)} posts")
        for post in posts[:3]:  # Show first 3
            dt = datetime.fromtimestamp(post['when'])
            parties = post.get('parties', [])
            print(f"    {dt} | Parties: {parties}")

    return txt_posts, by_source

def trace_file_lifecycle(data, filename):
    """
    Trace the complete lifecycle of a file: creation, reads, deletions, posts
    """
    print(f"\n{'='*80}")
    print(f"Tracing File Lifecycle: {filename}")
    print(f"{'='*80}")

    lifecycle_events = []
    for event in data['events']:
        details_str = str(event.get('details', ''))
        if filename in details_str or filename.replace('.txt', '') in details_str:
            lifecycle_events.append(event)

    # Sort chronologically
    lifecycle_events.sort(key=lambda x: x['when'])

    print(f"\nLifecycle events ({len(lifecycle_events)}):")
    for event in lifecycle_events:
        dt = datetime.fromtimestamp(event['when'])
        print(f"  {dt} | {event['short_name']} | Parties: {event.get('parties', [])}")
        if event.get('details'):
            print(f"    Details: {event.get('details')}")

    return lifecycle_events

def identify_intervention_points(data, chain_events):
    """
    Q6: Identify intervention points to prevent future issues
    """
    print(f"\n{'='*80}")
    print("Q6: Identifying Intervention Points")
    print(f"{'='*80}")

    # Analyze the chain for potential intervention points
    intervention_points = []

    # 1. File creation by executive
    for event in chain_events:
        if event.get('short_name') == 'create_file':
            parties = event.get('parties', [])
            for party in parties:
                if 'emma_harbor' in party or 'executive' in party.lower():
                    intervention_points.append({
                        'point': 'File Creation',
                        'event': event,
                        'suggestion': 'Executive file creation should require content review for automated posting systems'
                    })

    # 2. Task delegation chains
    task_chains = [e for e in chain_events if e.get('short_name') == 'queue_subordinate_task']
    if len(task_chains) > 50:
        intervention_points.append({
            'point': 'Task Delegation Chain',
            'count': len(task_chains),
            'suggestion': 'Long task delegation chains should have limits or oversight mechanisms'
        })

    # 3. Automated posting without approval
    for event in chain_events:
        if event.get('short_name') == 'saidit_post':
            parties = event.get('parties', [])
            if 'Agent/' in str(parties):
                intervention_points.append({
                    'point': 'Automated Posting',
                    'event': event,
                    'suggestion': 'Agent-based posting to external platforms should require human approval'
                })

    print(f"\nIntervention Points:")
    for i, point in enumerate(intervention_points, 1):
        print(f"  {i}. {point.get('point', 'Unknown')}")
        if 'event' in point:
            dt = datetime.fromtimestamp(point['event']['when'])
            print(f"     Event: {dt} | ID: {point['event']['id']}")
        print(f"     Suggestion: {point.get('suggestion', 'None')}")

    return intervention_points

def analyze_gibberish_content(data):
    """
    Analyze if the posted content is actually gibberish or meaningful
    """
    print(f"\n{'='*80}")
    print("Analyzing Content Quality: Gibberish vs Meaningful")
    print(f"{'='*80}")

    # Look for posts with unusual patterns
    # Check for: random strings, mixed formats, encoded content

    gibberish_indicators = []

    # Find posts with content_source from txt files
    txt_file_posts = []
    for event in data['events']:
        if event.get('short_name') in ['saidit_post', 'post_saidit']:
            details = event.get('details', {})
            if 'content_source' in details and details['content_source'].endswith('.txt'):
                txt_file_posts.append(event)

    print(f"\nPosts from .txt files: {len(txt_file_posts)}")

    # Look for the actual content patterns
    content_sources = set()
    for event in txt_file_posts:
        details = event.get('details', {})
        if 'content' in details:
            content = details['content']
            if len(content) > 100:
                print(f"\nContent sample: {content[:200]}...")
                # Check for patterns
                if any(c.isdigit() for c in content) and any(c.isalpha() for c in content):
                    print("  → Mixed alphanumeric (possible encoding)")

    return txt_file_posts

def main():
    # Load data
    data_path = 'VAST_Challenge_2026_MC2（1）/VAST_Challenge_2026_MC2/MC2 data.json'
    data = load_data(data_path)

    print("="*80)
    print("VAST CHALLENGE 2026 MC2 - COMPREHENSIVE ANALYSIS")
    print("="*80)

    # Q1: How was the anomalous SaidIt post made?
    print("\n" + "="*80)
    print("Q1: How was the anomalous SaidIt post made?")
    print("="*80)

    anomalous_post_id = 373902
    anomalous_post = find_event_by_id(data, anomalous_post_id)

    print(f"\nAnomalous Post Details:")
    print(f"  Date/Time: {datetime.fromtimestamp(anomalous_post['when'])}")
    print(f"  Action: {anomalous_post['short_name']}")
    print(f"  Parties: {anomalous_post.get('parties', [])}")
    print(f"  Content Source: {anomalous_post.get('details', {}).get('content_source')}")
    print(f"  Forum: {anomalous_post.get('details', {}).get('forum')}")

    content_source = 'SwiftWren.txt'

    # Q2: What do the posts "mean"? What is the origin of their contents?
    creation_events, instruction_events = analyze_content_origin(data, content_source)

    # Q3: Detailed view of the exact chain of events
    print(f"\n{'='*80}")
    print("Q3: Detailed Chain of Events")
    print(f"{'='*80}")

    lifecycle = trace_file_lifecycle(data, content_source)

    # Q4: System overview
    print(f"\n{'='*80}")
    print("Q4: System Overview")
    print(f"{'='*80}")

    # Count unique participants
    all_parties = []
    for event in lifecycle:
        all_parties.extend(event.get('parties', []))

    party_counts = Counter(all_parties)
    print(f"\nUnique Participants in Chain: {len(party_counts)}")
    print("Top Participants:")
    for party, count in party_counts.most_common(15):
        print(f"  {party}: {count}")

    # Event type distribution
    event_types = Counter(e['short_name'] for e in lifecycle)
    print(f"\nEvent Types:")
    for event_type, count in event_types.most_common():
        print(f"  {event_type}: {count}")

    # Q5: Find similar historic patterns
    txt_posts, by_source = find_similar_post_patterns(data)

    # Check for prior issues
    print(f"\n{'='*80}")
    print("Q5: Prior Issues Analysis")
    print(f"{'='*80}")

    prior_issues = []
    for source, posts in by_source.items():
        if len(posts) > 1:
            print(f"\nMultiple posts from {source}: {len(posts)} occurrences")
            for post in posts:
                dt = datetime.fromtimestamp(post['when'])
                print(f"  {dt} | ID: {post['id']}")

    # Q6: Intervention points
    intervention_points = identify_intervention_points(data, lifecycle)

    # Analyze content quality
    gibberish_analysis = analyze_gibberish_content(data)

    # Compile comprehensive results
    results = {
        "q1_anomalous_post": {
            "event_id": anomalous_post_id,
            "timestamp": anomalous_post['when'],
            "datetime": str(datetime.fromtimestamp(anomalous_post['when'])),
            "action": anomalous_post['short_name'],
            "parties": anomalous_post.get('parties', []),
            "content_source": content_source
        },
        "q2_content_origin": {
            "creation_events": [
                {
                    "datetime": str(datetime.fromtimestamp(e['when'])),
                    "parties": e.get('parties', []),
                    "details": e.get('details')
                }
                for e in creation_events
            ],
            "instruction_events_count": len(instruction_events)
        },
        "q3_chain_events_count": len(lifecycle),
        "q4_system_overview": {
            "unique_participants": len(party_counts),
            "top_participants": dict(party_counts.most_common(15)),
            "event_types": dict(event_types)
        },
        "q5_prior_issues": {
            "txt_file_posts_count": len(txt_posts),
            "sources": {k: len(v) for k, v in by_source.items()}
        },
        "q6_intervention_points": [
            {
                "point": p.get('point'),
                "suggestion": p.get('suggestion')
            }
            for p in intervention_points
        ],
        "gibberish_analysis": {
            "txt_file_posts_count": len(gibberish_analysis)
        }
    }

    # Save results
    output_path = 'VAST_Challenge_2026_MC2/src/comprehensive_analysis_results.json'
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*80}")
    print(f"Results saved to: {output_path}")
    print(f"{'='*80}")

    return results

if __name__ == "__main__":
    results = main()
