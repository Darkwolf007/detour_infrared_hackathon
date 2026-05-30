import pytest
import numpy as np
import networkx as nx
from shapely.geometry import LineString

from utils.grid_sampler import sample_grid_at_point, sample_edge
from services.routing_service import turn_penalty, build_summary, route_loop
from models.response_models import EdgeScore

def test_sample_grid_at_point():
    grid = np.array([
        [1.0, 2.0],
        [3.0, 4.0]
    ], dtype=np.float32)
    # bounds: (min_lon, min_lat, max_lon, max_lat)
    bounds = (0.0, 0.0, 10.0, 10.0)
    
    # Northwest corner (col=0, row=0) -> Grid value 1.0
    val = sample_grid_at_point(grid, bounds, 2.0, 8.0)
    assert val == 1.0
    
    # Southeast corner (col=1, row=1) -> Grid value 4.0
    val = sample_grid_at_point(grid, bounds, 8.0, 2.0)
    assert val == 4.0

def test_sample_edge():
    grid = np.array([
        [1.0, 2.0],
        [3.0, 4.0]
    ], dtype=np.float32)
    bounds = (0.0, 0.0, 10.0, 10.0)
    
    # Simple short edge (<100m in degree representation)
    geom_short = LineString([(1.0, 8.0), (3.0, 8.0)])
    val = sample_edge(geom_short, grid, bounds)
    assert val == 1.0

def test_turn_penalty():
    # Low turn preference (threshold=45 deg, penalty=0.4)
    assert turn_penalty(0.0, 90.0, "low") == 0.4
    assert turn_penalty(0.0, 30.0, "low") == 0.0
    
    # Mid turn preference (threshold=90 deg, penalty=0.2)
    assert turn_penalty(0.0, 120.0, "mid") == 0.2
    assert turn_penalty(0.0, 45.0, "mid") == 0.0
    
    # High turn preference (threshold=999 deg, penalty=0.0)
    assert turn_penalty(0.0, 180.0, "high") == 0.0

def test_build_summary():
    edge_scores = [
        EdgeScore(coordinates=[[0,0],[1,1]], utci_score=0.2, raw_utci=24.0, wind_score=0.1, shade_score=0.8, veg_score=0.6),
        EdgeScore(coordinates=[[1,1],[2,2]], utci_score=0.1, raw_utci=25.0, wind_score=0.2, shade_score=0.7, veg_score=0.4)
    ]
    summary = build_summary(edge_scores, 200.0, 3)
    
    assert summary.distance_m == 200.0
    assert summary.duration_min == 2.5  # 200m / 80 = 2.5
    assert summary.avg_utci == 24.5     # (24 + 25) / 2
    assert summary.avg_shade == 0.75    # (0.8 + 0.7) / 2
    assert summary.comfort_rating == "comfortable"  # avg_utci_score = 0.15 < 0.3
    assert summary.poi_count == 3

def test_route_loop():
    # Build a simple grid graph
    G = nx.grid_2d_graph(5, 5, periodic=False)
    # Convert nodes to integer labels
    mapping = {node: i for i, node in enumerate(G.nodes())}
    G = nx.relabel_nodes(G, mapping)
    
    # Make it a MultiGraph with coordinates
    G_multi = nx.MultiGraph()
    for n in G.nodes():
        G_multi.add_node(n, x=float(n % 5) * 0.001, y=float(n // 5) * 0.001)
        
    for u, v in G.edges():
        G_multi.add_edge(u, v, cost=1.0, length=50.0)
        
    # Standard route_loop execution
    start = 0
    path = route_loop(G_multi, start_node=start, max_dist_m=400.0, turn_pref="mid")
    
    # Path should start and end at 0
    assert path[0] == start
    assert path[-1] == start
    assert len(path) > 2
