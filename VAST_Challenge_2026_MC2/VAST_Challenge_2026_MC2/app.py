"""
VAST Challenge 2026 MC2 - Visual Analytics System
Analyzing anomalous SaidIT posts from John Windward
"""

import json
import os
from datetime import datetime
from flask import Flask, render_template, jsonify, request
import pandas as pd
import networkx as nx
from collections import defaultdict, Counter
import itertools

app = Flask(__name__)

# Global data structures
events_data = None
org_graph = None
events_df = None

# Key event: John Windward's post on May 17, 2046 at 4:21am
# Converting to timestamp: May 17, 2046 04:21 AM
KEY_EVENT_TIMESTAMP = datetime(2046, 5, 17, 4, 21).timestamp()


def load_data():
    """Load and process the event data and organization chart"""
    global events_data, org_graph, events_df

    # Load events
    with open('MC2 data.json', 'r', encoding='utf-8') as f:
        events_data = json.load(f)

    # Load organization chart
    with open('org_chart.json', 'r', encoding='utf-8') as f:
        org_data = json.load(f)
        org_graph = nx.node_link_graph(org_data)

    # Create DataFrame for easier analysis
    events_list = []
    for event in events_data['events']:
        events_list.append({
            'id': event['id'],
            'short_name': event['short_name'],
            'parties': event['parties'],
            'when': event['when'],
            'details': event.get('details', {})
        })

    events_df = pd.DataFrame(events_list)
    events_df['datetime'] = pd.to_datetime(events_df['when'], unit='s')

    print(f"Loaded {len(events_df)} events")
    print(f"Organization has {org_graph.number_of_nodes()} nodes")


def find_john_windward_events():
    """Find all events related to John Windward"""
    john_events = []

    for event in events_data['events']:
        parties_str = str(event['parties'])
        if 'john_windward' in parties_str.lower() or 'person:john_windward' in parties_str:
            john_events.append(event)

    return john_events


def find_saidit_posts():
    """Find all SaidIT post events"""
    saidit_posts = []

    for event in events_data['events']:
        if event['short_name'] in ['post', 'posted', 'create_post', 'send_post']:
            parties_str = str(event['parties']) + str(event.get('details', {}))
            if 'saidit' in parties_str.lower():
                saidit_posts.append(event)

    return saidit_posts


def get_event_chain(target_timestamp, window_hours=24):
    """Get events leading up to a specific timestamp"""
    window_seconds = window_hours * 3600
    start_time = target_timestamp - window_seconds

    chain_events = []
    for event in events_data['events']:
        if start_time <= event['when'] <= target_timestamp:
            chain_events.append(event)

    return sorted(chain_events, key=lambda x: x['when'])


def build_interaction_graph(events):
    """Build a network graph from events"""
    G = nx.DiGraph()

    for event in events:
        parties = event.get('parties', [])
        # Add edges between parties
        for i in range(len(parties)):
            for j in range(i + 1, len(parties)):
                source = parties[i]
                target = parties[j]
                if G.has_edge(source, target):
                    G[source][target]['weight'] += 1
                else:
                    G.add_edge(source, target, weight=1)

    return G


def extract_person_id(party_string):
    """Extract person ID from party string"""
    if isinstance(party_string, str):
        if party_string.startswith('person:'):
            return party_string
        elif party_string.startswith('Agent/'):
            return party_string.split('/')[1]
    return None


def categorize_event(event):
    """Categorize events by type"""
    short_name = event.get('short_name', '')
    details = event.get('details', {})

    categories = {
        'communication': ['sent', 'received', 'email', 'message', 'chat'],
        'collaboration': ['propose_meeting', 'schedule', 'invite', 'meeting'],
        'file_ops': ['upload', 'download', 'share', 'access'],
        'agent_activity': ['Agent', 'autonomous', 'automated'],
        'post': ['post', 'publish', 'saidit']
    }

    for category, keywords in categories.items():
        if any(keyword in short_name.lower() for keyword in keywords):
            return category

    return 'other'


def find_similar_patterns(target_event_chain):
    """Find similar event patterns in historic data"""
    # Extract the pattern of event types
    target_pattern = [e['short_name'] for e in target_event_chain]

    similar_chains = []

    # Look for similar sequences in the full dataset
    all_events = sorted(events_data['events'], key=lambda x: x['when'])

    window_size = len(target_pattern)
    for i in range(len(all_events) - window_size):
        window = all_events[i:i + window_size]
        window_pattern = [e['short_name'] for e in window]

        # Calculate similarity
        matches = sum(1 for t, w in zip(target_pattern, window_pattern) if t == w)
        similarity = matches / window_size

        if similarity >= 0.5:  # At least 50% similarity
            similar_chains.append({
                'events': window,
                'similarity': similarity,
                'start_time': window[0]['when'],
                'end_time': window[-1]['when']
            })

    return similar_chains[:10]  # Return top 10


@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')


@app.route('/api/events/summary')
def events_summary():
    """Get summary statistics of events"""
    if events_df is None:
        load_data()

    summary = {
        'total_events': len(events_df),
        'date_range': {
            'start': events_df['datetime'].min().isoformat(),
            'end': events_df['datetime'].max().isoformat()
        },
        'event_types': events_df['short_name'].value_counts().to_dict(),
        'unique_participants': len(set([p for event in events_data['events'] for p in event['parties']])),
        'john_windward_events': len(find_john_windward_events()),
        'saidit_posts': len(find_saidit_posts())
    }

    return jsonify(summary)


@app.route('/api/john_windward/timeline')
def john_windward_timeline():
    """Get timeline of John Windward's activities"""
    john_events = find_john_windward_events()

    timeline = []
    for event in sorted(john_events, key=lambda x: x['when']):
        timeline.append({
            'time': datetime.fromtimestamp(event['when']).isoformat(),
            'action': event['short_name'],
            'parties': event['parties'],
            'details': event.get('details', {}),
            'id': event['id']
        })

    return jsonify({
        'events': timeline,
        'total_count': len(timeline)
    })


@app.route('/api/key_event/chain')
def key_event_chain():
    """Get the chain of events leading to the key post"""
    chain = get_event_chain(KEY_EVENT_TIMESTAMP, window_hours=48)

    timeline = []
    for event in chain:
        timeline.append({
            'time': datetime.fromtimestamp(event['when']).isoformat(),
            'action': event['short_name'],
            'parties': event['parties'],
            'category': categorize_event(event),
            'details': str(event.get('details', {}))[:200],  # Truncate long details
            'id': event['id']
        })

    return jsonify({
        'key_event_time': datetime.fromtimestamp(KEY_EVENT_TIMESTAMP).isoformat(),
        'chain_events': timeline,
        'total_count': len(timeline)
    })


@app.route('/api/similar_patterns')
def similar_patterns_api():
    """Find patterns similar to the anomalous post chain"""
    # Get the event chain around the key event
    target_chain = get_event_chain(KEY_EVENT_TIMESTAMP, window_hours=24)

    similar = find_similar_patterns(target_chain)

    results = []
    for chain in similar:
        results.append({
            'similarity': chain['similarity'],
            'start_time': datetime.fromtimestamp(chain['start_time']).isoformat(),
            'end_time': datetime.fromtimestamp(chain['end_time']).isoformat(),
            'event_count': len(chain['events']),
            'first_event': chain['events'][0]['short_name'] if chain['events'] else None
        })

    return jsonify({
        'similar_patterns': results,
        'target_event_time': datetime.fromtimestamp(KEY_EVENT_TIMESTAMP).isoformat()
    })


@app.route('/api/network/generate')
def generate_network():
    """Generate network graph data for visualization"""
    # Get events around the key time
    chain = get_event_chain(KEY_EVENT_TIMESTAMP, window_hours=48)

    G = build_interaction_graph(chain)

    nodes = []
    edges = []

    # Get node types from org chart
    node_types = {}
    for node in org_graph.nodes(data=True):
        node_types[node[0]] = node[1].get('type', 'unknown')

    for node in G.nodes():
        node_type = 'unknown'
        if node in node_types:
            node_type = node_types[node]
        elif 'person:' in node:
            node_type = 'person'
        elif 'agent:' in node:
            node_type = 'agent'
        elif 'system:' in node or 'world:' in node:
            node_type = 'system'

        nodes.append({
            'id': node,
            'type': node_type,
            'degree': G.degree(node)
        })

    for source, target, data in G.edges(data=True):
        edges.append({
            'source': source,
            'target': target,
            'weight': data.get('weight', 1)
        })

    return jsonify({
        'nodes': nodes,
        'edges': edges,
        'node_count': len(nodes),
        'edge_count': len(edges)
    })


@app.route('/api/post_analysis')
def post_analysis():
    """Analyze the SaidIT posts"""
    saidit_posts = find_saidit_posts()

    posts = []
    for post in saidit_posts:
        posts.append({
            'time': datetime.fromtimestamp(post['when']).isoformat(),
            'parties': post['parties'],
            'details': post.get('details', {}),
            'id': post['id']
        })

    return jsonify({
        'posts': posts,
        'total_count': len(posts)
    })


@app.route('/api/intervention_points')
def intervention_points():
    """Suggest intervention points to prevent anomalous posts"""
    # Analyze the chain to find critical intervention points
    chain = get_event_chain(KEY_EVENT_TIMESTAMP, window_hours=48)

    interventions = []

    # Find agent activities
    agent_events = [e for e in chain if any('agent:' in str(p).lower() for p in e['parties'])]

    # Find automated triggers
    automated_events = [e for e in chain if e['short_name'] in ['autonomous', 'automated', 'trigger', 'schedule']]

    # Find unusual patterns
    unusual_party_counts = [e for e in chain if len(e['parties']) > 5 or len(e['parties']) == 0]

    interventions.append({
        'type': 'agent_validation',
        'description': 'Add validation checkpoints for agent-initiated posts',
        'priority': 'high',
        'evidence': f'Found {len(agent_events)} agent-related events in the 48h window before the post',
        'suggestion': 'Implement human-in-the-loop approval for any agent-generated content destined for public platforms'
    })

    interventions.append({
        'type': 'rate_limiting',
        'description': 'Implement rate limiting for rapid automated actions',
        'priority': 'medium',
        'evidence': f'Found {len(automated_events)} automated events that could trigger cascades',
        'suggestion': 'Add cooldown periods between automated actions and monitoring for rapid succession events'
    })

    interventions.append({
        'type': 'content_filtering',
        'description': 'Enhance content filtering for anomalous text patterns',
        'priority': 'high',
        'evidence': 'The post contained gibberish content that should have been flagged',
        'suggestion': 'Implement semantic analysis to detect and flag nonsensical or malformed content before publication'
    })

    return jsonify({
        'interventions': interventions,
        'analysis_based_on': f'{len(chain)} events in the 48h window'
    })


if __name__ == '__main__':
    load_data()
    app.run(debug=True, port=5000)
