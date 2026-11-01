"""Steam September 2026 snapshot, checked 2026-11-01.
Tuple: model, Steam percent, author shutdown recommendation, NVIDIA maximum.
Laptop recommendation is provisional and must be checked against OEM specs.
"""
PROFILES = [
    ('RTX 5070', 6.15, 80, 85),
    ('RTX 5060', 4.40, 84, 89),
    ('RTX 5060 Ti', 4.06, 82, 87),
    ('RTX 4060', 3.89, 85, 90),
    ('RTX 3060', 3.66, 85, 93),
    ('RTX 4060 Laptop GPU', 3.50, 83, None),
    ('RTX 3050', 2.90, 85, 93),
    ('RTX 4060 Ti', 2.85, 85, 90),
    ('RTX 5060 Laptop GPU', 2.45, 83, None),
    ('GTX 1650', 2.19, 85, None),
    ('RTX 4070', 2.11, 85, 90),
    ('RTX 3060 Ti', 2.08, 85, 93),
    ('RTX 5080', 1.98, 83, 88),
    ('RTX 3070', 1.97, 85, 93),
    ('RTX 5070 Ti', 1.87, 83, 88),
    ('RTX 4070 SUPER', 1.74, 85, 90),
    ('RTX 3060 Laptop GPU', 1.66, 83, None),
    ('RTX 4050 Laptop GPU', 1.59, 83, None),
    ('RTX 2060', 1.53, 83, 88),
    ('Intel Iris Xe Graphics', 1.52, None, None),
]
