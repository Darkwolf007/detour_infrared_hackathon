import logging
import math
import random
import networkx as nx
from typing import Optional

from models.response_models import EdgeScore, RouteSummary

logger = logging.getLogger("thermal_router.routing_service")

def edge_bearing(G: nx.MultiGraph, u: int, v: int) -> float:
    """
    Calculate the compass bearing (0-360 degrees) of the straight line from node u to node v.
    """
    x1, y1 = G.nodes[u]["x"], G.nodes[u]["y"]
    x2, y2 = G.nodes[v]["x"], G.nodes[v]["y"]
    bearing = math.degrees(math.atan2(y2 - y1, x2 - x1))
    return bearing % 360

def turn_penalty(prev_bearing: float, curr_bearing: float, preference: str) -> float:
    """
    Apply turn penalty if bearing change exceeds preference threshold.
    low: angle=45, penalty=0.4
    mid: angle=90, penalty=0.2
    high: angle=999, penalty=0.0
    """
    thresholds = {
        "low": (45.0, 0.4),
        "mid": (90.0, 0.2),
        "high": (999.0, 0.0)
    }
    angle, weight = thresholds.get(preference, (90.0, 0.2))
    diff = abs((curr_bearing - prev_bearing + 180) % 360 - 180)
    return weight if diff > angle else 0.0

def route_typical(G: nx.MultiGraph, src_node: int, dst_node: int) -> list[int]:
    """
    Standard A to B pedestrian routing using Dijkstra's shortest path.
    """
    logger.info(f"Routing typical path: {src_node} -> {dst_node}")
    return nx.shortest_path(G, src_node, dst_node, weight="cost")

def route_multi(G: nx.MultiGraph, stop_nodes: list[int]) -> list[int]:
    """
    Multiple stops pedestrian routing. Chains paths between consecutive stop pairs.
    """
    logger.info(f"Routing multi-stop path across stops: {stop_nodes}")
    full_path = []
    for i in range(len(stop_nodes) - 1):
        segment = nx.shortest_path(G, stop_nodes[i], stop_nodes[i+1], weight="cost")
        if i > 0:
            full_path.extend(segment[1:])
        else:
            full_path.extend(segment)
    return full_path

def route_loop(G: nx.MultiGraph, start_node: int, max_dist_m: float, turn_pref: str = "mid") -> list[int]:
    """
    Pedestrian loop routing. Uses a weighted random selection from top 3 neighbors
    until 0.65 * max_dist_m distance is covered, then finds the shortest path back.
    Reproducible by seeding random with start_node.
    """
    logger.info(f"Routing loop from start: {start_node}, max distance: {max_dist_m}m")
    
    # Seeding with start_node ensures deterministic loops for same start node
    rng = random.Random(start_node)
    
    outbound_budget = max_dist_m * 0.65
    visited = [start_node]
    curr_node = start_node
    current_dist = 0.0
    prev_bearing = None
    
    while current_dist < outbound_budget:
        neighbors = []
        for nbr in G.neighbors(curr_node):
            if nbr in visited:
                continue
                
            edge_data = G[curr_node].get(nbr)
            if not edge_data:
                continue
                
            # Select edge with lowest pre-computed cost
            best_k = min(edge_data.keys(), key=lambda k: edge_data[k].get("cost", 99999.0))
            best_edge = edge_data[best_k]
            
            cost = best_edge.get("cost", 1.0)
            length = best_edge.get("length", 50.0)
            
            # Incorporate turn penalty in greedy decision
            curr_bearing = edge_bearing(G, curr_node, nbr)
            penalty = 0.0
            if prev_bearing is not None:
                penalty = turn_penalty(prev_bearing, curr_bearing, turn_pref)
                
            adjusted_cost = cost + penalty * length
            neighbors.append((nbr, adjusted_cost, length, curr_bearing))
            
        if not neighbors:
            break
            
        # Sort and take top 3 neighbors
        neighbors.sort(key=lambda x: x[1])
        top_n = neighbors[:3]
        
        # Weighted selection based on inverse cost (lower cost -> higher probability)
        weights = [1.0 / max(0.001, x[1]) for x in top_n]
        total_w = sum(weights)
        
        if total_w == 0.0:
            chosen = rng.choice(top_n)
        else:
            norm_weights = [w / total_w for w in weights]
            chosen = rng.choices(top_n, weights=norm_weights, k=1)[0]
            
        next_node, _, length, bearing = chosen
        visited.append(next_node)
        current_dist += length
        curr_node = next_node
        prev_bearing = bearing
        
    # Route shortest path back to start
    try:
        return_path = nx.shortest_path(G, curr_node, start_node, weight="cost")
        visited.extend(return_path[1:])
    except nx.NetworkXNoPath:
        logger.warning(f"No path found to close the loop back to start {start_node} from {curr_node}")
        
    return visited

def get_path_distance(G: nx.MultiGraph, node_path: list[int]) -> float:
    """
    Calculate the total physical length of a node path in meters.
    """
    dist = 0.0
    for u, v in zip(node_path[:-1], node_path[1:]):
        edge_data = G[u].get(v)
        if edge_data:
            best_k = min(edge_data.keys(), key=lambda k: edge_data[k].get("cost", 99999.0))
            dist += edge_data[best_k].get("length", 50.0)
    return dist

def path_to_geojson(G: nx.MultiGraph, node_path: list[int]) -> dict:
    """
    Convert a node path into a closed GeoJSON LineString coordinates structure.
    Uses edge geometry if present, otherwise straight line between nodes.
    """
    coords = []
    for u, v in zip(node_path[:-1], node_path[1:]):
        edge_data = G[u].get(v)
        if not edge_data:
            continue
        best_k = min(edge_data.keys(), key=lambda k: edge_data[k].get("cost", 99999.0))
        best_edge = edge_data[best_k]
        
        if "geometry" in best_edge:
            # Extend with LineString coordinates
            coords.extend(list(best_edge["geometry"].coords)[:-1])
        else:
            coords.append((G.nodes[u]["x"], G.nodes[u]["y"]))
            
    # Add final node
    coords.append((G.nodes[node_path[-1]]["x"], G.nodes[node_path[-1]]["y"]))
    
    return {
        "type": "LineString",
        "coordinates": coords
    }

def path_to_edge_scores(G: nx.MultiGraph, node_path: list[int], edge_scores_dict: dict) -> list[EdgeScore]:
    """
    Map node path to list of EdgeScore response models.
    """
    edge_scores_list = []
    for u, v in zip(node_path[:-1], node_path[1:]):
        edge_data = G[u].get(v)
        if not edge_data:
            continue
        best_k = min(edge_data.keys(), key=lambda k: edge_data[k].get("cost", 99999.0))
        
        scores = edge_scores_dict.get((u, v, best_k))
        if not scores:
            scores = {
                "utci_score": 0.5,
                "raw_utci": 26.0,
                "wind_score": 0.3,
                "shade_score": 0.5,
                "veg_score": 0.3,
            }
            
        best_edge = edge_data[best_k]
        if "geometry" in best_edge:
            coords = list(best_edge["geometry"].coords)
        else:
            coords = [
                [G.nodes[u]["x"], G.nodes[u]["y"]],
                [G.nodes[v]["x"], G.nodes[v]["y"]]
            ]
            
        edge_scores_list.append(
            EdgeScore(
                coordinates=coords,
                utci_score=scores.get("utci_score", 0.5),
                raw_utci=scores.get("raw_utci", 26.0),
                wind_score=scores.get("wind_score", 0.3),
                shade_score=scores.get("shade_score", 0.5),
                veg_score=scores.get("veg_score", 0.3)
            )
        )
    return edge_scores_list

def build_summary(edge_scores_list: list[EdgeScore], distance_m: float, poi_count: int = 0) -> RouteSummary:
    """
    Compile RouteSummary object containing overall comfort and physical statistics.
    """
    if not edge_scores_list:
        return RouteSummary(
            distance_m=round(distance_m, 1),
            duration_min=round(distance_m / 80.0, 1),
            avg_utci=26.0,
            avg_shade=0.5,
            comfort_rating="comfortable",
            shade_pct=50.0,
            nature_pct=30.0,
            poi_count=poi_count
        )
        
    total_utci = 0.0
    total_shade = 0.0
    total_veg = 0.0
    total_utci_score = 0.0
    
    for edge in edge_scores_list:
        total_utci += edge.raw_utci
        total_shade += edge.shade_score
        total_veg += edge.veg_score
        total_utci_score += edge.utci_score
        
    n = len(edge_scores_list)
    avg_utci = total_utci / n
    avg_shade = total_shade / n
    avg_veg = total_veg / n
    avg_utci_score = total_utci_score / n
    
    # Comfort ratings (low = comfortable, high = hot/extreme stress)
    if avg_utci_score < 0.3:
        comfort_rating = "comfortable"
    elif avg_utci_score < 0.6:
        comfort_rating = "moderate"
    elif avg_utci_score < 0.8:
        comfort_rating = "hot"
    else:
        comfort_rating = "extreme"
        
    duration_min = distance_m / 80.0  # 80m/min = 4.8km/h standard walking pace
    
    return RouteSummary(
        distance_m=round(distance_m, 1),
        duration_min=round(duration_min, 1),
        avg_utci=round(avg_utci, 1),
        avg_shade=round(avg_shade, 2),
        comfort_rating=comfort_rating,
        shade_pct=round(avg_shade * 100.0, 1),
        nature_pct=round(avg_veg * 100.0, 1),
        poi_count=poi_count
    )
