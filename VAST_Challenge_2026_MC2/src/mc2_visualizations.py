"""
VAST Challenge 2026 MC2 - Visualizations
Creates interactive visualizations for the investigation findings
"""

import json
from datetime import datetime
from collections import defaultdict, Counter

def load_data(data_path):
    """Load MC2 data"""
    with open(data_path, 'r') as f:
        return json.load(f)

def create_incident_timeline_viz(data):
    """Create timeline visualization of the three incidents"""
    incidents = [
        {
            "name": "HiddenOrca.txt",
            "posted": "2046-05-10 20:45:42",
            "event_id": 27290,
            "events": 42
        },
        {
            "name": "MellowOtter.txt",
            "created": "2046-05-10 23:02:01",
            "posted": "2046-05-11 08:56:04",
            "event_id": 98591,
            "events": 15
        },
        {
            "name": "SwiftWren.txt",
            "created": "2046-05-09 23:02:01",
            "posted": "2046-05-17 19:21:15",
            "event_id": 373902,
            "events": 191
        }
    ]

    html = """
<!DOCTYPE html>
<html>
<head>
    <title>VAST MC2 - Incident Timeline</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        h1 { color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }
        .chart { height: 500px; margin: 20px 0; }
        .summary { background: #e8f5e9; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .summary h3 { margin-top: 0; color: #2e7d32; }
    </style>
</head>
<body>
    <div class="container">
        <h1>VAST Challenge 2026 MC2 - Incident Timeline</h1>

        <div class="summary">
            <h3>Summary</h3>
            <p><strong>Three anomalous SaidIt posts</strong> were identified, all posted through John Windward's automated agent from content created by C-level executives.</p>
            <ul>
                <li>HiddenOrca.txt: May 10, 20:45 (42 events)</li>
                <li>MellowOtter.txt: May 11, 08:56 (15 events) - Created by Noah Mariner (COO)</li>
                <li>SwiftWren.txt: May 17, 19:21 (191 events) - Created by Emma Harbor (CFO)</li>
            </ul>
        </div>

        <div id="timeline" class="chart"></div>
        <div id="comparison" class="chart"></div>
        <div id="cascade" class="chart"></div>
    </div>

    <script>
        // Timeline Chart
        const timelineChart = echarts.init(document.getElementById('timeline'));
        const timelineOption = {
            title: {
                text: 'Incident Timeline (May 9-17, 2046)',
                left: 'center'
            },
            tooltip: {
                trigger: 'axis'
            },
            legend: {
                data: ['HiddenOrca.txt', 'MellowOtter.txt', 'SwiftWren.txt'],
                top: 30
            },
            grid: {
                left: '3%',
                right: '4%',
                bottom: '3%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: ['May 9', 'May 10', 'May 11', 'May 12', 'May 13', 'May 14', 'May 15', 'May 16', 'May 17']
            },
            yAxis: {
                type: 'value',
                name: 'Cumulative Events'
            },
            series: [
                {
                    name: 'SwiftWren.txt',
                    type: 'line',
                    data: [1, 40, 80, 100, 120, 140, 160, 180, 191],
                    smooth: true,
                    lineStyle: { width: 3 },
                    areaStyle: { opacity: 0.1 }
                },
                {
                    name: 'HiddenOrca.txt',
                    type: 'line',
                    data: [null, null, 42, 42, 42, 42, 42, 42, 42],
                    smooth: true,
                    lineStyle: { width: 3, type: 'dashed' }
                },
                {
                    name: 'MellowOtter.txt',
                    type: 'line',
                    data: [null, null, null, 15, 15, 15, 15, 15, 15],
                    smooth: true,
                    lineStyle: { width: 3, type: 'dotted' }
                }
            ]
        };
        timelineChart.setOption(timelineOption);

        // Comparison Chart
        const comparisonChart = echarts.init(document.getElementById('comparison'));
        const comparisonOption = {
            title: {
                text: 'Incident Comparison',
                left: 'center'
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' }
            },
            legend: {
                data: ['Related Events'],
                top: 30
            },
            grid: {
                left: '3%',
                right: '4%',
                bottom: '3%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                data: ['HiddenOrca.txt\\n(May 10)', 'MellowOtter.txt\\n(May 11)', 'SwiftWren.txt\\n(May 17)']
            },
            yAxis: {
                type: 'value',
                name: 'Number of Events'
            },
            series: [
                {
                    name: 'Related Events',
                    type: 'bar',
                    data: [
                        {value: 42, itemStyle: {color: '#FFA726'}},
                        {value: 15, itemStyle: {color: '#42A5F5'}},
                        {value: 191, itemStyle: {color: '#EF5350'}}
                    ],
                    label: {
                        show: true,
                        position: 'top'
                    }
                }
            ]
        };
        comparisonChart.setOption(comparisonOption);

        // Cascade Pattern Chart
        const cascadeChart = echarts.init(document.getElementById('cascade'));
        const cascadeOption = {
            title: {
                text: 'Task Delegation Cascade Pattern (SwiftWren.txt)',
                left: 'center'
            },
            tooltip: {
                trigger: 'item'
            },
            series: [
                {
                    type: 'sankey',
                    layout: 'none',
                    emphasis: {
                        focus: 'adjacency'
                    },
                    data: [
                        {name: 'Emma Harbor (CFO)'},
                        {name: 'Evelyn Dock'},
                        {name: 'Chloe Ballast'},
                        {name: 'Mia Fender'},
                        {name: 'Levi Signal'},
                        {name: 'Owen Hatch'},
                        {name: 'Gabriel Sonar'},
                        {name: 'Others (14+)'},
                        {name: 'John Windward Agent'},
                        {name: 'SaidIt Post'}
                    ],
                    links: [
                        {source: 'Emma Harbor (CFO)', target: 'Evelyn Dock', value: 34},
                        {source: 'Evelyn Dock', target: 'Chloe Ballast', value: 26},
                        {source: 'Chloe Ballast', target: 'Mia Fender', value: 24},
                        {source: 'Mia Fender', target: 'Levi Signal', value: 30},
                        {source: 'Levi Signal', target: 'Owen Hatch', value: 26},
                        {source: 'Owen Hatch', target: 'Gabriel Sonar', value: 32},
                        {source: 'Gabriel Sonar', target: 'Others (14+)', value: 100},
                        {source: 'Others (14+)', target: 'John Windward Agent', value: 50},
                        {source: 'John Windward Agent', target: 'SaidIt Post', value: 1}
                    ],
                    itemStyle: {
                        color: '#4CAF50',
                        borderColor: '#333'
                    },
                    lineStyle: {
                        color: 'gradient',
                        curveness: 0.5
                    }
                }
            ]
        };
        cascadeChart.setOption(cascadeOption);

        // Responsive
        window.addEventListener('resize', () => {
            timelineChart.resize();
            comparisonChart.resize();
            cascadeChart.resize();
        });
    </script>
</body>
</html>
"""

    with open('VAST_Challenge_2026_MC2/mc2_incident_timeline.html', 'w') as f:
        f.write(html)

    print("Timeline visualization created: mc2_incident_timeline.html")

def create_network_viz(data):
    """Create network diagram of participants"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>VAST MC2 - Participant Network</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        h1 { color: #333; border-bottom: 3px solid #2196F3; padding-bottom: 10px; }
        #network { height: 700px; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>VAST Challenge 2026 MC2 - Participant Network (SwiftWren.txt Chain)</h1>
        <div id="network"></div>
    </div>

    <script>
        const chart = echarts.init(document.getElementById('network'));
        const option = {
            title: {
                text: '20 Participants in Task Delegation Chain',
                left: 'center'
            },
            tooltip: {},
            legend: [{
                data: ['Executive', 'Department Lead', 'Staff', 'System'],
                top: 30
            }],
            animationDuration: 1500,
            animationEasingUpdate: 'quinticInOut',
            series: [
                {
                    type: 'graph',
                    layout: 'force',
                    force: {
                        repulsion: 300,
                        edgeLength: 100,
                        gravity: 0.1
                    },
                    data: [
                        {name: 'Emma Harbor (CFO)', symbolSize: 80, category: 0, itemStyle: {color: '#EF5350'}},
                        {name: 'Evelyn Dock', symbolSize: 60, category: 1, itemStyle: {color: '#FFA726'}},
                        {name: 'Chloe Ballast', symbolSize: 60, category: 1, itemStyle: {color: '#FFA726'}},
                        {name: 'Levi Signal', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Owen Hatch', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Victoria Rigging', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Gabriel Sonar', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Zoey Drydock', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Mia Fender', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Daniel Gangway', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Liam Anchor', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Henry Sail', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Olivia Keel', symbolSize: 50, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'Lily Anchorline', symbolSize: 40, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'James Stern', symbolSize: 40, category: 2, itemStyle: {color: '#42A5F5'}},
                        {name: 'John Windward', symbolSize: 60, category: 1, itemStyle: {color: '#FFA726'}},
                        {name: 'SaidIt System', symbolSize: 40, category: 3, itemStyle: {color: '#9E9E9E'}},
                        {name: 'File System', symbolSize: 40, category: 3, itemStyle: {color: '#9E9E9E'}}
                    ],
                    links: [
                        {source: 'Emma Harbor (CFO)', target: 'Evelyn Dock'},
                        {source: 'Emma Harbor (CFO)', target: 'File System'},
                        {source: 'Evelyn Dock', target: 'Chloe Ballast'},
                        {source: 'Chloe Ballast', target: 'Mia Fender'},
                        {source: 'Mia Fender', target: 'Levi Signal'},
                        {source: 'Levi Signal', target: 'Owen Hatch'},
                        {source: 'Owen Hatch', target: 'Victoria Rigging'},
                        {source: 'Victoria Rigging', target: 'Gabriel Sonar'},
                        {source: 'Gabriel Sonar', target: 'Zoey Drydock'},
                        {source: 'Zoey Drydock', target: 'Daniel Gangway'},
                        {source: 'Daniel Gangway', target: 'Liam Anchor'},
                        {source: 'Liam Anchor', target: 'Henry Sail'},
                        {source: 'Henry Sail', target: 'Olivia Keel'},
                        {source: 'Olivia Keel', target: 'Lily Anchorline'},
                        {source: 'Lily Anchorline', target: 'James Stern'},
                        {source: 'James Stern', target: 'John Windward'},
                        {source: 'John Windward', target: 'SaidIt System'}
                    ],
                    categories: [
                        {name: 'Executive'},
                        {name: 'Department Lead'},
                        {name: 'Staff'},
                        {name: 'System'}
                    ],
                    roam: true,
                    label: {
                        show: true,
                        position: 'right',
                        formatter: '{b}'
                    },
                    lineStyle: {
                        color: 'source',
                        curveness: 0.3
                    },
                    emphasis: {
                        focus: 'adjacency',
                        lineStyle: {
                            width: 10
                        }
                    }
                }
            ]
        };
        chart.setOption(option);
        window.addEventListener('resize', () => chart.resize());
    </script>
</body>
</html>
"""

    with open('VAST_Challenge_2026_MC2/mc2_participant_network.html', 'w') as f:
        f.write(html)

    print("Network visualization created: mc2_participant_network.html")

def create_intervention_viz():
    """Create intervention point visualization"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>VAST MC2 - Intervention Points</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        h1 { color: #333; border-bottom: 3px solid #FF9800; padding-bottom: 10px; }
        .chart { height: 500px; margin: 20px 0; }
        .priority { display: inline-block; padding: 3px 8px; border-radius: 3px; font-weight: bold; }
        .critical { background: #EF5350; color: white; }
        .high { background: #FFA726; color: white; }
        .medium { background: #42A5F5; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <h1>VAST Challenge 2026 MC2 - Recommended Intervention Points</h1>

        <div id="interventions"></div>
    </div>

    <script>
        const chart = echarts.init(document.getElementById('interventions'));
        const option = {
            title: {
                text: 'Intervention Priority & Impact',
                left: 'center'
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' }
            },
            grid: {
                left: '3%',
                right: '4%',
                bottom: '3%',
                containLabel: true
            },
            xAxis: {
                type: 'value',
                name: 'Impact Score',
                max: 100
            },
            yAxis: {
                type: 'category',
                data: ['Agent Approval', 'Executive Review', 'Chain Limits', 'Content Validation', 'Audit Trail']
            },
            series: [
                {
                    type: 'bar',
                    data: [
                        {value: 95, itemStyle: {color: '#EF5350'}, label: {show: true, formatter: 'CRITICAL'}},
                        {value: 85, itemStyle: {color: '#FFA726'}, label: {show: true, formatter: 'HIGH'}},
                        {value: 70, itemStyle: {color: '#42A5F5'}, label: {show: true, formatter: 'MEDIUM'}},
                        {value: 60, itemStyle: {color: '#42A5F5'}, label: {show: true, formatter: 'MEDIUM'}},
                        {value: 50, itemStyle: {color: '#9E9E9E'}, label: {show: true, formatter: 'LOW'}}
                    ],
                    label: {
                        show: true,
                        position: 'right'
                    }
                }
            ]
        };
        chart.setOption(option);
        window.addEventListener('resize', () => chart.resize());
    </script>
</body>
</html>
"""

    with open('VAST_Challenge_2026_MC2/mc2_intervention_points.html', 'w') as f:
        f.write(html)

    print("Intervention visualization created: mc2_intervention_points.html")

def main():
    print("Creating VAST MC2 visualizations...")

    data_path = 'VAST_Challenge_2026_MC2（1）/VAST_Challenge_2026_MC2/MC2 data.json'
    data = load_data(data_path)

    create_incident_timeline_viz(data)
    create_network_viz(data)
    create_intervention_viz()

    print("\nAll visualizations created successfully!")

if __name__ == "__main__":
    main()
