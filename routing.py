# routing.py

"""
Модуль маршрутизации:
- статический A*;
- динамический A* с зависящими от времени весами;
- расчет длины и времени уже найденного маршрута.
"""

import heapq
import math
import time

import networkx as nx

from traffic_model import dynamic_travel_time_min


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Расстояние между двумя точками на сфере в метрах.
    Используется для эвристики A*.
    """
    radius_m = 6_371_000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return radius_m * c


def heuristic_min_time(
    graph: nx.MultiDiGraph,
    node,
    target,
    max_speed_kph: float = 90.0,
) -> float:
    """
    Допустимая эвристика:
    время движения по прямой с максимально возможной скоростью.
    Возвращает значение в минутах.
    """
    node_data = graph.nodes[node]
    target_data = graph.nodes[target]

    lat1 = node_data["y"]
    lon1 = node_data["x"]

    lat2 = target_data["y"]
    lon2 = target_data["x"]

    distance_m = haversine_distance_m(lat1, lon1, lat2, lon2)

    return distance_m / max_speed_kph * 0.06


def reconstruct_path(parent: dict, start, target) -> list:
    """
    Восстанавливает маршрут по словарю parent.
    Возвращает список ребер:
        [(u, v, key), ...]
    """
    path_edges = []
    current = target

    while current != start:
        if current not in parent:
            return []

        previous_node, edge_key = parent[current]
        path_edges.append((previous_node, current, edge_key))
        current = previous_node

    path_edges.reverse()
    return path_edges


def get_best_static_edge(graph: nx.MultiDiGraph, u, v):
    """
    Для MultiDiGraph между u и v может быть несколько ребер.
    Выбираем ребро с минимальным статическим временем.
    """
    edge_dict = graph.get_edge_data(u, v)
    if not edge_dict:
        return None, None

    best_key = None
    best_data = None
    best_time = float("inf")

    for key, data in edge_dict.items():
        edge_time = float(data.get("static_travel_time_min", float("inf")))

        if edge_time < best_time:
            best_time = edge_time
            best_key = key
            best_data = data

    return best_key, best_data


def get_best_dynamic_edge(graph: nx.MultiDiGraph, u, v, tau_min: float):
    """
    Для MultiDiGraph между u и v может быть несколько ребер.
    Выбираем ребро с минимальным динамическим временем при въезде в tau_min.
    """
    edge_dict = graph.get_edge_data(u, v)
    if not edge_dict:
        return None, None, float("inf")

    best_key = None
    best_data = None
    best_time = float("inf")

    for key, data in edge_dict.items():
        edge_time = dynamic_travel_time_min(data, tau_min)

        if edge_time < best_time:
            best_time = edge_time
            best_key = key
            best_data = data

    return best_key, best_data, best_time


def static_astar_route(graph: nx.MultiDiGraph, start, target) -> dict:
    """
    Статический A*.
    Вес ребра не зависит от времени.
    """
    start_time = time.perf_counter()

    open_heap = []
    heapq.heappush(open_heap, (0.0, start))

    g_score = {start: 0.0}
    parent = {}

    visited = set()
    expanded_nodes = 0

    while open_heap:
        _, current = heapq.heappop(open_heap)

        if current in visited:
            continue

        visited.add(current)
        expanded_nodes += 1

        if current == target:
            elapsed = time.perf_counter() - start_time
            path_edges = reconstruct_path(parent, start, target)

            return {
                "path_edges": path_edges,
                "travel_time_min": g_score[target],
                "expanded_nodes": expanded_nodes,
                "runtime_sec": elapsed,
                "success": True,
            }

        for neighbor in graph.successors(current):
            edge_key, edge_data = get_best_static_edge(graph, current, neighbor)

            if edge_data is None:
                continue

            edge_time = float(edge_data.get("static_travel_time_min", float("inf")))
            tentative_g = g_score[current] + edge_time

            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                parent[neighbor] = (current, edge_key)

                f_score = tentative_g + heuristic_min_time(graph, neighbor, target)
                heapq.heappush(open_heap, (f_score, neighbor))

    elapsed = time.perf_counter() - start_time

    return {
        "path_edges": [],
        "travel_time_min": float("inf"),
        "expanded_nodes": expanded_nodes,
        "runtime_sec": elapsed,
        "success": False,
    }


def dynamic_astar_route(
    graph: nx.MultiDiGraph,
    start,
    target,
    departure_time_min: float,
) -> dict:
    """
    Модифицированный A* для динамической маршрутизации.
    Вес ребра вычисляется в зависимости от расчетного момента въезда на ребро.
    """
    start_time = time.perf_counter()

    open_heap = []
    heapq.heappush(open_heap, (0.0, start))

    g_score = {start: 0.0}
    parent = {}

    visited = set()
    expanded_nodes = 0

    while open_heap:
        _, current = heapq.heappop(open_heap)

        if current in visited:
            continue

        visited.add(current)
        expanded_nodes += 1

        if current == target:
            elapsed = time.perf_counter() - start_time
            path_edges = reconstruct_path(parent, start, target)

            return {
                "path_edges": path_edges,
                "travel_time_min": g_score[target],
                "arrival_time_min": departure_time_min + g_score[target],
                "expanded_nodes": expanded_nodes,
                "runtime_sec": elapsed,
                "success": True,
            }

        current_arrival_time = departure_time_min + g_score[current]

        for neighbor in graph.successors(current):
            edge_key, _, edge_time = get_best_dynamic_edge(
                graph,
                current,
                neighbor,
                current_arrival_time,
            )

            if edge_key is None:
                continue

            tentative_g = g_score[current] + edge_time

            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                parent[neighbor] = (current, edge_key)

                f_score = tentative_g + heuristic_min_time(graph, neighbor, target)
                heapq.heappush(open_heap, (f_score, neighbor))

    elapsed = time.perf_counter() - start_time

    return {
        "path_edges": [],
        "travel_time_min": float("inf"),
        "arrival_time_min": float("inf"),
        "expanded_nodes": expanded_nodes,
        "runtime_sec": elapsed,
        "success": False,
    }


def calculate_route_length_km(graph: nx.MultiDiGraph, path_edges: list) -> float:
    """
    Считает длину маршрута в километрах.
    """
    total_length_m = 0.0

    for u, v, key in path_edges:
        edge_data = graph.get_edge_data(u, v, key)

        if edge_data:
            total_length_m += float(edge_data.get("length", 0.0))

    return total_length_m / 1000


def calculate_route_dynamic_time_min(
    graph: nx.MultiDiGraph,
    path_edges: list,
    departure_time_min: float,
) -> float:
    """
    Вычисляет динамическое время прохождения уже найденного маршрута.

    Это нужно для честного сравнения:
    - статический маршрут сначала строится по статическим весам;
    - затем этот же статический маршрут оценивается в динамических условиях;
    - динамический маршрут тоже оценивается в динамических условиях.
    """
    current_time = departure_time_min
    total_travel_time = 0.0

    for u, v, key in path_edges:
        edge_data = graph.get_edge_data(u, v, key)

        if edge_data is None:
            return float("inf")

        edge_time = dynamic_travel_time_min(edge_data, current_time)

        total_travel_time += edge_time
        current_time += edge_time

    return total_travel_time


def calculate_route_static_time_min(
    graph: nx.MultiDiGraph,
    path_edges: list,
) -> float:
    """
    Вычисляет статическое время прохождения уже найденного маршрута.
    """
    total_time = 0.0

    for u, v, key in path_edges:
        edge_data = graph.get_edge_data(u, v, key)

        if edge_data is None:
            return float("inf")

        total_time += float(edge_data.get("static_travel_time_min", float("inf")))

    return total_time
