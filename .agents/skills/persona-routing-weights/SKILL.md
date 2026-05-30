# Skill: Persona Routing Weight Vectors

## All 13 default personas with full weight vectors

### COMMUTE
| sub_reason | name              | w_speed | w_shade | w_nature | w_discovery | turns | route   | SDK           |
|------------|-------------------|---------|---------|----------|-------------|-------|---------|---------------|
| office     | Office commuter   | 0.60    | 0.20    | 0.10     | 0.10        | low   | typical | UTCI,Wind     |
| home       | Evening commuter  | 0.50    | 0.30    | 0.10     | 0.10        | low   | typical | UTCI,Solar    |
| transit    | Transit connector | 0.70    | 0.15    | 0.05     | 0.10        | low   | typical | UTCI          |
| errands    | Errand runner     | 0.40    | 0.25    | 0.05     | 0.30        | mid   | multi   | UTCI,PWC      |

### STROLL
| sub_reason | name             | w_speed | w_shade | w_nature | w_discovery | turns | route | SDK                    |
|------------|------------------|---------|---------|----------|-------------|-------|-------|------------------------|
| kid        | Parent + child   | 0.10    | 0.30    | 0.50     | 0.10        | mid   | loop  | UTCI,Solar,Vegetation  |
| couple     | Couple stroll    | 0.15    | 0.35    | 0.30     | 0.20        | mid   | loop  | UTCI,Solar             |
| dog        | Dog walker       | 0.10    | 0.20    | 0.60     | 0.10        | high  | loop  | UTCI,Vegetation,PWC    |

### EXERCISE
| sub_reason | name            | w_speed | w_shade | w_nature | w_discovery | turns | route | SDK             |
|------------|-----------------|---------|---------|----------|-------------|-------|-------|-----------------|
| running    | Runner          | 0.40    | 0.30    | 0.20     | 0.10        | low   | loop  | UTCI,Wind,PWC   |
| walking    | Fitness walker  | 0.30    | 0.40    | 0.20     | 0.10        | mid   | loop  | UTCI,Solar      |
| cycling    | Cyclist         | 0.55    | 0.15    | 0.15     | 0.15        | low   | loop  | PWC,Wind        |

### EXPERIENCE
| sub_reason | name        | w_speed | w_shade | w_nature | w_discovery | turns | route | SDK                    |
|------------|-------------|---------|---------|----------|-------------|-------|-------|------------------------|
| tourist    | Tourist     | 0.05    | 0.25    | 0.20     | 0.50        | high  | multi | UTCI,Solar,Vegetation  |
| shopping   | Shopper     | 0.20    | 0.40    | 0.10     | 0.30        | mid   | multi | UTCI,Solar             |
| hopping    | Bar hopper  | 0.15    | 0.20    | 0.15     | 0.50        | high  | multi | UTCI,Wind              |

## Turn preference → routing behaviour
```
low  (angle=45°,  penalty=0.4) → penalise edges with bearing change > 45°
mid  (angle=90°,  penalty=0.2) → penalise edges with bearing change > 90°
high (angle=999°, penalty=0.0) → no turn penalty, winding routes allowed
```

## Rule: faster = lower turns
```
speed-dominant personas  (w_speed >= 0.40) → low turns
balanced personas        (0.20 <= w_speed < 0.40) → mid turns
discovery-dominant personas (w_discovery >= 0.40) → high turns
```

## Age modifier (applied server-side on top of persona weights)
```python
AGE_SHADE_BOOST = {
    'under_18':0.00, '18_35':0.00, '36_55':0.05,
    '56_70':0.15, '70_plus':0.25
}
# Boost w_shade by this amount, subtract equally from w_speed + w_discovery
# Renormalise so all 4 weights sum to 1.0
```

## Weight normalisation after user slider override
```python
def normalise_weights(speed, shade, nature, discovery):
    total = speed + shade + nature + discovery
    if total == 0: total = 1
    return {
        'w_speed':     round(speed/total, 4),
        'w_shade':     round(shade/total, 4),
        'w_nature':    round(nature/total, 4),
        'w_discovery': round(discovery/total, 4),
    }
```
