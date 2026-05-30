# Skill: OSMnx Road Network + Routing

## Installation
```bash
pip install osmnx networkx geopandas shapely
```

## Fetch pedestrian graph from bbox
```python
import osmnx as ox
import networkx as nx

def fetch_graph(bbox: dict, mode: str = 'walk') -> nx.MultiGraph:
    G = ox.graph_from_bbox(
        north=bbox['max_lat'], south=bbox['min_lat'],
        east=bbox['max_lon'],  west=bbox['min_lon'],
        network_type=mode,
        retain_all=True,
        useful_tags_way=[
            'highway','surface','lit','width','foot','bicycle',
            'access','name','natural','landuse','amenity',
            'tourism','covered','cycleway','oneway','maxspeed'
        ]
    )
    return ox.convert.to_undirected(G)
# mode='walk' for all pedestrian personas
# mode='bike' for cycling persona only
```

## Compute bbox from stops
```python
def bbox_from_stops(stops: list, padding_m: float = 500) -> dict:
    pad = padding_m / 111000   # metres to degrees
    lats = [s['lat'] for s in stops]
    lons = [s['lon'] for s in stops]
    return {
        'min_lat': min(lats)-pad, 'max_lat': max(lats)+pad,
        'min_lon': min(lons)-pad, 'max_lon': max(lons)+pad,
    }

def bbox_from_loop(start: dict, max_dist_m: float) -> dict:
    pad = (max_dist_m / 111000) + 0.005
    return {
        'min_lat': start['lat']-pad, 'max_lat': start['lat']+pad,
        'min_lon': start['lon']-pad, 'max_lon': start['lon']+pad,
    }
```

## Nearest node lookup
```python
def nearest_node(G, lat: float, lon: float) -> int:
    return ox.distance.nearest_nodes(G, X=lon, Y=lat)
```

## Assign edge costs from enriched scores
```python
def assign_costs(G, edge_scores: dict, persona) -> nx.MultiGraph:
    for u,v,k,data in G.edges(keys=True, data=True):
        scores = edge_scores.get((u,v,k), {})
        length = data.get('length', 50)
        cost = (
            persona.w_speed    * (length / 100.0)
            + persona.w_shade  * (1 - scores.get('shade_score', 0.5))
            + persona.w_nature * (1 - scores.get('veg_score', 0.3))
            + persona.w_discovery * (1 - scores.get('poi_density', 0.1))
            + persona.w_speed  * scores.get('surface_penalty', 0.1)
            + persona.w_speed  * scores.get('highway_safety', 0.2)
        ) * length
        G[u][v][k]['cost'] = cost
    return G
```

## Convert node path to GeoJSON LineString
```python
def path_to_geojson(G, node_path: list) -> dict:
    coords = []
    for u,v in zip(node_path[:-1], node_path[1:]):
        data = G[u][v][0]
        if 'geometry' in data:
            coords.extend(list(data['geometry'].coords))
        else:
            coords.append((G.nodes[u]['x'], G.nodes[u]['y']))
    coords.append((G.nodes[node_path[-1]]['x'], G.nodes[node_path[-1]]['y']))
    return {"type":"LineString","coordinates":coords}
```

## Edge bearing (for turn penalty)
```python
import math
def edge_bearing(G, u, v) -> float:
    x1,y1 = G.nodes[u]['x'], G.nodes[u]['y']
    x2,y2 = G.nodes[v]['x'], G.nodes[v]['y']
    return math.degrees(math.atan2(y2-y1, x2-x1)) % 360

def bearing_change(b1: float, b2: float) -> float:
    return abs((b2 - b1 + 180) % 360 - 180)
```

## Cycling lane detection
```python
def is_cycling_lane(edge_data: dict) -> bool:
    return (
        edge_data.get('highway') == 'cycleway'
        or edge_data.get('cycleway') in ['lane','track','shared_lane','shared']
    )
```

## POI density per edge
```python
from shapely.strtree import STRtree
from shapely.geometry import Point

def build_poi_index(G) -> STRtree:
    # Fetch POI nodes from graph
    pois = [Point(d['x'],d['y']) for n,d in G.nodes(data=True)
            if d.get('amenity') or d.get('tourism')]
    return STRtree(pois)

def poi_density(edge_geom, poi_tree, radius_deg=0.0005) -> float:
    buf = edge_geom.buffer(radius_deg)   # ~50m
    count = len(poi_tree.query(buf))
    return min(1.0, count / 10.0)
```
