# app.py

"""
Веб-интерфейс для системы динамической маршрутизации.

Пользователь вводит:
- место отправления;
- место назначения;
- время выезда.

Программа:
- преобразует названия мест в координаты;
- строит статический и динамический маршруты;
- сравнивает их в динамических условиях;
- выводит результаты и карту в браузере.

Дополнительно пользователь может включить модельное локальное ухудшение
дорожной ситуации. Это демонстрационный сценарий, а не реальные данные о ДТП.
"""

import os
import webbrowser
from threading import Timer

import osmnx as ox
from flask import Flask, request, render_template_string, send_from_directory, url_for

from config import (
    PLACE_NAME,
    NETWORK_TYPE,
    MAPS_DIR,
    FIGURES_DIR,
)

from graph_loader import load_graph, get_nearest_node

from routing import (
    static_astar_route,
    dynamic_astar_route,
    calculate_route_dynamic_time_min,
    calculate_route_length_km,
)

from visualization import save_route_map, save_speed_profiles
from analysis import minutes_to_hhmm
from traffic_model import set_incident_scenario_enabled


app = Flask(__name__)

GRAPH = None



HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Динамическая маршрутизация</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            background: #f3f4f6;
            color: #111827;
        }

        .container {
            max-width: 1100px;
            margin: 0 auto;
            padding: 30px;
        }

        .card {
            background: white;
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
        }

        h1 {
            margin-top: 0;
            font-size: 28px;
        }

        h2 {
            font-size: 21px;
            margin-top: 0;
        }

        label {
            display: block;
            margin-top: 14px;
            margin-bottom: 6px;
            font-weight: bold;
        }

        input {
            width: 100%;
            padding: 11px;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            font-size: 15px;
            box-sizing: border-box;
        }

        button {
            margin-top: 20px;
            padding: 12px 18px;
            border: none;
            border-radius: 8px;
            background: #2563eb;
            color: white;
            font-size: 15px;
            cursor: pointer;
        }

        button:hover {
            background: #1d4ed8;
        }

        .hint {
            color: #6b7280;
            font-size: 14px;
            margin-top: 8px;
        }

        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
        }

        .metric {
            background: #f9fafb;
            border-radius: 10px;
            padding: 14px;
            border: 1px solid #e5e7eb;
        }

        .metric-title {
            color: #6b7280;
            font-size: 13px;
            margin-bottom: 5px;
        }

        .metric-value {
            font-size: 20px;
            font-weight: bold;
        }

        .success {
            background: #ecfdf5;
            border: 1px solid #10b981;
            color: #065f46;
            padding: 14px;
            border-radius: 10px;
        }

        .warning {
            background: #fffbeb;
            border: 1px solid #f59e0b;
            color: #92400e;
            padding: 14px;
            border-radius: 10px;
        }

        .error {
            background: #fef2f2;
            border: 1px solid #ef4444;
            color: #991b1b;
            padding: 14px;
            border-radius: 10px;
        }

        iframe {
            width: 100%;
            height: 620px;
            border: none;
            border-radius: 12px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 14px;
        }

        th, td {
            border: 1px solid #e5e7eb;
            padding: 10px;
            text-align: left;
        }

        th {
            background: #f9fafb;
        }

        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 18px;
            font-weight: normal;
        }

        .checkbox-label input {
            width: auto;
        }

        #loading {
            display: none;
            margin-top: 16px;
            padding: 12px;
            border-radius: 10px;
            background: #eff6ff;
            border: 1px solid #3b82f6;
            color: #1e40af;
        }

        @media (max-width: 800px) {
            .grid {
                grid-template-columns: 1fr;
            }

            .container {
                padding: 16px;
            }
        }
    </style>

    <script>
        function showLoading() {
            const loadingBlock = document.getElementById("loading");
            if (loadingBlock) {
                loadingBlock.style.display = "block";
            }
        }
    </script>
</head>
<body>
<div class="container">

    <div class="card">
        <h1>Динамическая маршрутизация наземного личного автотранспорта</h1>
        <p>
            Введите место отправления, место назначения и время выезда.
            Система построит статический и динамический маршруты и сравнит их
            с учетом прогнозной дорожной загруженности.
        </p>
        <p class="hint">
            Текущая территория графа: <b>{{ place_name }}</b>
        </p>
    </div>

    <div class="card">
        <h2>Параметры маршрута</h2>

        <form method="post" onsubmit="showLoading()">
            <label for="start_place">Место отправления</label>
            <input
                id="start_place"
                name="start_place"
                type="text"
                required
                value="{{ start_place or '' }}"
                placeholder="Например: Москва-Сити, Москва, Россия"
            >

            <label for="end_place">Место назначения</label>
            <input
                id="end_place"
                name="end_place"
                type="text"
                required
                value="{{ end_place or '' }}"
                placeholder="Например: Курский вокзал, Москва, Россия"
            >

            <label for="departure_time">Время отправления</label>
            <input
                id="departure_time"
                name="departure_time"
                type="time"
                required
                value="{{ departure_time or '08:00' }}"
            >

            <label class="checkbox-label">
                <input
                    type="checkbox"
                    name="incident_enabled"
                    value="1"
                    {% if incident_enabled %}checked{% endif %}
                >
                Учитывать модельное локальное ухудшение дорожной ситуации
            </label>

            <p class="hint">
                Этот режим имитирует временное снижение скорости в небольшой области графа.
                Он используется только как демонстрационный сценарий.
            </p>

            <button type="submit">Построить маршрут</button>

            <div id="loading">
                Маршрут строится, пожалуйста подождите...
            </div>

            <p class="hint">
                Введите начальную и конечную точки маршрута, а также время отправления.
            </p>
        </form>
    </div>

    {% if error %}
    <div class="card">
        <div class="error">
            {{ error }}
        </div>
    </div>
    {% endif %}

    {% if result %}
    <div class="card">
        <h2>Результаты маршрутизации</h2>

        {% if result.routes_are_equal %}
        <div class="warning">
            Статический и динамический маршруты совпали. Для данного времени отправления
            и выбранных точек динамическая модель не изменила маршрут.
        </div>
        {% else %}
        <div class="success">
            Динамический алгоритм выбрал альтернативный маршрут.
            Выигрыш по прогнозируемому времени движения составил
            <b>{{ result.time_gain_min }} мин</b>,
            что соответствует
            <b>{{ result.time_gain_percent }} %</b>.
        </div>
        {% endif %}

        <div class="grid" style="margin-top: 18px;">
            <div class="metric">
                <div class="metric-title">Время отправления</div>
                <div class="metric-value">{{ result.departure_time }}</div>
            </div>

            <div class="metric">
                <div class="metric-title">Прогнозируемое время прибытия</div>
                <div class="metric-value">{{ result.arrival_time }}</div>
            </div>

            <div class="metric">
                <div class="metric-title">Выигрыш динамического маршрута</div>
                <div class="metric-value">
                    {{ result.time_gain_min }} мин
                    <br>
                    <span style="font-size: 15px; color: #059669;">
                        {{ result.time_gain_percent }} %
                    </span>
                </div>
            </div>


            <div class="metric">
                <div class="metric-title">Модельное локальное ухудшение</div>
                <div class="metric-value">
                    {% if result.incident_enabled %}
                        включено
                    {% else %}
                        выключено
                    {% endif %}
                </div>
            </div>
        </div>

        <table>
            <tr>
                <th>Показатель</th>
                <th>Статический маршрут</th>
                <th>Динамический маршрут</th>
            </tr>
            <tr>
                <td>Длина маршрута, км</td>
                <td>{{ result.static_length_km }}</td>
                <td>{{ result.dynamic_length_km }}</td>
            </tr>
            <tr>
                <td>Время движения в динамических условиях, мин</td>
                <td>{{ result.static_dynamic_time_min }}</td>
                <td>{{ result.dynamic_dynamic_time_min }}</td>
            </tr>
            <tr>
                <td>Количество ребер</td>
                <td>{{ result.static_edges }}</td>
                <td>{{ result.dynamic_edges }}</td>
            </tr>
            <tr>
                <td>Раскрыто вершин</td>
                <td>{{ result.static_expanded_nodes }}</td>
                <td>{{ result.dynamic_expanded_nodes }}</td>
            </tr>
            <tr>
                <td>Время выполнения, сек</td>
                <td>{{ result.static_runtime_sec }}</td>
                <td>{{ result.dynamic_runtime_sec }}</td>
            </tr>
            <tr>
                <td>Выигрыш динамического маршрута</td>
                <td colspan="2">
                    {{ result.time_gain_min }} мин, {{ result.time_gain_percent }} %
                </td>
            </tr>
        </table>
    </div>

    <div class="card">
        <h2>Карта маршрута</h2>
        <p class="hint">
            На карте отображаются статический и динамический маршруты.
            Синий цвет соответствует статическому маршруту, красный --- динамическому.
            Если маршруты совпадают, визуально может быть видна только одна линия.
        </p>
        <iframe src="{{ map_url }}"></iframe>
    </div>
    {% endif %}

</div>
</body>
</html>
"""


def get_graph():
    """
    Загружает граф один раз и переиспользует его для последующих запросов.
    """
    global GRAPH

    if GRAPH is None:
        print("Загрузка дорожного графа...")
        GRAPH = load_graph(PLACE_NAME, NETWORK_TYPE)

    return GRAPH


def parse_time_hhmm(value: str) -> int:
    """
    Преобразует время HH:MM в минуты от начала суток.
    """
    hours_str, minutes_str = value.split(":")
    hours = int(hours_str)
    minutes = int(minutes_str)

    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        raise ValueError("Некорректное время")

    return hours * 60 + minutes


def geocode_place(place_name: str) -> tuple[float, float]:
    """
    Преобразует адрес или название места в координаты.
    Возвращает (latitude, longitude).
    """
    try:
        lat, lon = ox.geocoder.geocode(place_name)
        return lat, lon
    except AttributeError:
        lat, lon = ox.geocode(place_name)
        return lat, lon


@app.route("/maps/<path:filename>")
def serve_map(filename):
    """
    Отдает HTML-карты из папки maps.
    """
    return send_from_directory(MAPS_DIR, filename)


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None
    map_url = None

    start_place = ""
    end_place = ""
    departure_time_value = "08:00"
    incident_enabled = False

    if request.method == "POST":
        start_place = request.form.get("start_place", "").strip()
        end_place = request.form.get("end_place", "").strip()
        departure_time_value = request.form.get("departure_time", "08:00").strip()

        incident_enabled = request.form.get("incident_enabled") == "1"

        # Включаем или выключаем модельное локальное ухудшение
        # до расчета маршрутов и проверки FIFO.
        set_incident_scenario_enabled(incident_enabled)

        try:
            if not start_place or not end_place:
                raise ValueError("Необходимо заполнить место отправления и место назначения.")

            departure_time_min = parse_time_hhmm(departure_time_value)

            graph = get_graph()

            print(f"Геокодирование места отправления: {start_place}")
            start_point = geocode_place(start_place)

            print(f"Геокодирование места назначения: {end_place}")
            end_point = geocode_place(end_place)

            print("Поиск ближайших узлов графа...")
            start_node = get_nearest_node(graph, start_point)
            end_node = get_nearest_node(graph, end_point)

            print("Построение статического маршрута...")
            static_result = static_astar_route(graph, start_node, end_node)

            print("Построение динамического маршрута...")
            dynamic_result = dynamic_astar_route(
                graph=graph,
                start=start_node,
                target=end_node,
                departure_time_min=departure_time_min,
            )

            if not static_result.get("success") or not dynamic_result.get("success"):
                raise ValueError("Не удалось построить маршрут между выбранными точками.")

            static_dynamic_time = calculate_route_dynamic_time_min(
                graph=graph,
                path_edges=static_result.get("path_edges", []),
                departure_time_min=departure_time_min,
            )

            dynamic_dynamic_time = calculate_route_dynamic_time_min(
                graph=graph,
                path_edges=dynamic_result.get("path_edges", []),
                departure_time_min=departure_time_min,
            )

            static_length = calculate_route_length_km(
                graph,
                static_result.get("path_edges", []),
            )

            dynamic_length = calculate_route_length_km(
                graph,
                dynamic_result.get("path_edges", []),
            )

            time_gain = static_dynamic_time - dynamic_dynamic_time

            if static_dynamic_time > 0 and static_dynamic_time != float("inf"):
                time_gain_percent = time_gain / static_dynamic_time * 100
            else:
                time_gain_percent = 0.0

            os.makedirs(MAPS_DIR, exist_ok=True)
            os.makedirs(FIGURES_DIR, exist_ok=True)

           # save_speed_profiles(
           #     graph,
            #    os.path.join(FIGURES_DIR, "web_speed_profiles.png"),
            #)

            map_filename = "web_route.html"
            map_path = os.path.join(MAPS_DIR, map_filename)

            save_route_map(
                graph=graph,
                static_result=static_result,
                dynamic_result=dynamic_result,
                start_point=start_point,
                end_point=end_point,
                output_path=map_path,
                show_incident_zone=incident_enabled,
            )

            routes_are_equal = (
                static_result.get("path_edges", [])
                == dynamic_result.get("path_edges", [])
            )

            result = {
                "departure_time": minutes_to_hhmm(departure_time_min),
                "arrival_time": minutes_to_hhmm(departure_time_min + dynamic_dynamic_time),
                "static_length_km": round(static_length, 2),
                "dynamic_length_km": round(dynamic_length, 2),
                "static_dynamic_time_min": round(static_dynamic_time, 2),
                "dynamic_dynamic_time_min": round(dynamic_dynamic_time, 2),
                "time_gain_min": round(time_gain, 2),
                "time_gain_percent": round(time_gain_percent, 2),
                "static_edges": len(static_result.get("path_edges", [])),
                "dynamic_edges": len(dynamic_result.get("path_edges", [])),
                "static_expanded_nodes": static_result.get("expanded_nodes", 0),
                "dynamic_expanded_nodes": dynamic_result.get("expanded_nodes", 0),
                "static_runtime_sec": round(static_result.get("runtime_sec", 0.0), 4),
                "dynamic_runtime_sec": round(dynamic_result.get("runtime_sec", 0.0), 4),
                "routes_are_equal": routes_are_equal,
                "incident_enabled": incident_enabled,
            }

            map_url = url_for("serve_map", filename=map_filename)

        except Exception as exc:
            error = str(exc)

    return render_template_string(
        HTML_TEMPLATE,
        place_name=PLACE_NAME,
        start_place=start_place,
        end_place=end_place,
        departure_time=departure_time_value,
        incident_enabled=incident_enabled,
        result=result,
        error=error,
        map_url=map_url,
    )


def open_browser():
    """
    Автоматически открывает страницу приложения в браузере.
    """
    webbrowser.open_new("http://127.0.0.1:5000/")


if __name__ == "__main__":
    Timer(1.0, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
