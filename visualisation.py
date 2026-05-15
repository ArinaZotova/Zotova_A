# visualization.py

"""
Модуль визуализации маршрутов и профилей скорости.
"""

import os

import folium
import matplotlib.pyplot as plt

from traffic_model import predicted_speed_kph
from config import INCIDENT_ZONE


def route_edges_to_coordinates(graph, path_edges: list) -> list[tuple[float, float]]:
    """
    Преобразует список ребер маршрута в список координат для Folium.
    Возвращает координаты в формате [(lat, lon), ...].

    Если у ребра есть геометрия, используется она.
    Если геометрии нет, используется линия между вершинами.
    """
    coordinates = []

    for u, v, key in path_edges:
        edge_data = graph.get_edge_data(u, v, key)

        if edge_data and "geometry" in edge_data:
            # geometry в OSMnx хранит координаты как (lon, lat),
            # а Folium ожидает (lat, lon).
            edge_coords = [
                (lat, lon)
                for lon, lat in edge_data["geometry"].coords
            ]

            if not coordinates:
                coordinates.extend(edge_coords)
            else:
                coordinates.extend(edge_coords[1:])

        else:
            u_data = graph.nodes[u]
            v_data = graph.nodes[v]

            if not coordinates:
                coordinates.append((u_data["y"], u_data["x"]))

            coordinates.append((v_data["y"], v_data["x"]))

    return coordinates


def add_incident_zone_to_map(route_map):
    """
    Добавляет на карту отдельную зону модельного локального ухудшения дорожной ситуации.
    """
    bounds = [
        [INCIDENT_ZONE["min_lat"], INCIDENT_ZONE["min_lon"]],
        [INCIDENT_ZONE["max_lat"], INCIDENT_ZONE["max_lon"]],
    ]

    folium.Rectangle(
        bounds=bounds,
        color="orange",
        fill=True,
        fill_color="orange",
        fill_opacity=0.22,
        weight=2,
        tooltip="Зона модельного локального ухудшения дорожной ситуации",
        popup="Модельное локальное ухудшение дорожной ситуации",
    ).add_to(route_map)


def add_map_legend(route_map, show_incident_zone: bool = False):
    """
    Добавляет легенду на карту.
    """
    incident_html = ""

    if show_incident_zone:
        incident_html = """
        <div style="margin-top: 8px;">
            <span style="
                display: inline-block;
                width: 28px;
                height: 14px;
                background-color: orange;
                opacity: 0.5;
                margin-right: 8px;
                vertical-align: middle;
            "></span>
            Зона локального ухудшения
        </div>
        """

    legend_html = f"""
    <div style="
        position: fixed;
        bottom: 40px;
        left: 40px;
        width: 300px;
        background-color: white;
        border: 2px solid #d1d5db;
        z-index: 9999;
        font-size: 14px;
        border-radius: 10px;
        padding: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    ">
        <b>Обозначения</b><br>
        <div style="margin-top: 8px;">
            <span style="
                display: inline-block;
                width: 28px;
                height: 4px;
                background-color: blue;
                margin-right: 8px;
                vertical-align: middle;
            "></span>
            Статический маршрут
        </div>
        <div style="margin-top: 8px;">
            <span style="
                display: inline-block;
                width: 28px;
                height: 4px;
                background-color: red;
                margin-right: 8px;
                vertical-align: middle;
            "></span>
            Динамический маршрут
        </div>
        {incident_html}
    </div>
    """

    route_map.get_root().html.add_child(folium.Element(legend_html))


def save_route_map(
    graph,
    static_result: dict,
    dynamic_result: dict,
    start_point: tuple[float, float],
    end_point: tuple[float, float],
    output_path: str,
    show_incident_zone: bool = False,
):
    """
    Сохраняет карту со статическим и динамическим маршрутом.

    Цвета:
    - статический маршрут — синий;
    - динамический маршрут — красный;
    - зона модельного локального ухудшения — оранжевая область.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    center_lat = (start_point[0] + end_point[0]) / 2
    center_lon = (start_point[1] + end_point[1]) / 2

    route_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="OpenStreetMap",
    )

    if show_incident_zone:
        add_incident_zone_to_map(route_map)

    folium.Marker(
        location=start_point,
        popup="Старт",
        tooltip="Старт",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(route_map)

    folium.Marker(
        location=end_point,
        popup="Финиш",
        tooltip="Финиш",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(route_map)

    static_edges = static_result.get("path_edges", [])
    dynamic_edges = dynamic_result.get("path_edges", [])

    static_coords = route_edges_to_coordinates(graph, static_edges)
    dynamic_coords = route_edges_to_coordinates(graph, dynamic_edges)

    routes_are_equal = static_edges == dynamic_edges

    if static_coords:
        folium.PolyLine(
            static_coords,
            color="blue",
            weight=6,
            opacity=0.75,
            tooltip="Статический маршрут",
        ).add_to(route_map)

    if dynamic_coords:
        folium.PolyLine(
            dynamic_coords,
            color="red",
            weight=4 if not routes_are_equal else 9,
            opacity=0.85,
            dash_array=None if not routes_are_equal else "8, 8",
            tooltip="Динамический маршрут",
        ).add_to(route_map)

    add_map_legend(route_map, show_incident_zone=show_incident_zone)

    all_coords = static_coords + dynamic_coords

    if show_incident_zone:
        all_coords.extend(
            [
                (INCIDENT_ZONE["min_lat"], INCIDENT_ZONE["min_lon"]),
                (INCIDENT_ZONE["max_lat"], INCIDENT_ZONE["max_lon"]),
            ]
        )

    if all_coords:
        route_map.fit_bounds(all_coords)

    route_map.save(output_path)
    print(f"Карта маршрута сохранена: {output_path}")


def save_speed_profiles(graph, output_path: str):
    """
    Строит пример графиков прогнозной скорости для нескольких типов дорог.
    Для наглядности используются первые найденные ребра разных категорий.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    selected_edges = {}
    wanted_types = ["motorway", "trunk","primary", "secondary", "tertiary", "residential"]

    for _, _, _, data in graph.edges(keys=True, data=True):
        highway_type = data.get("highway_type", "unclassified")

        if highway_type in wanted_types and highway_type not in selected_edges:
            selected_edges[highway_type] = data

        if len(selected_edges) >= 4:
            break

    times = list(range(0, 24 * 60, 10))

    plt.figure(figsize=(10, 6))

    for highway_type, edge_data in selected_edges.items():
        speeds = [predicted_speed_kph(edge_data, tau) for tau in times]
        hours = [tau / 60 for tau in times]
        plt.plot(hours, speeds, label=highway_type)

    plt.xlabel("Время суток, ч")
    plt.ylabel("Прогнозируемая скорость, км/ч")
    plt.title("Модельные прогнозные профили скорости")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    plt.savefig(output_path, dpi=200)
    plt.close()

    print(f"График профилей скорости сохранен: {output_path}")
