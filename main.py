# main.py

"""
Точка входа в программу.
Запускает эксперименты статической и динамической маршрутизации.
"""

import os

from config import (
    PLACE_NAME,
    NETWORK_TYPE,
    START_POINT,
    END_POINT,
    DEPARTURE_TIMES,
    RESULTS_DIR,
    MAPS_DIR,
    FIGURES_DIR,
)

from graph_loader import load_graph, get_nearest_node
from fifo_check import check_fifo_for_graph

from routing import (
    static_astar_route,
    dynamic_astar_route,
    calculate_route_dynamic_time_min,
)

from analysis import (
    build_result_row,
    save_results,
    build_comparison_row,
    save_comparison_results,
)

from visualization import save_route_map, save_speed_profiles


def main():
    graph = load_graph(PLACE_NAME, NETWORK_TYPE)

    print("\nПоиск ближайших узлов к стартовой и конечной точкам...")
    start_node = get_nearest_node(graph, START_POINT)
    end_node = get_nearest_node(graph, END_POINT)

    print(f"Стартовый узел: {start_node}")
    print(f"Конечный узел: {end_node}")

    print("\nПроверка условия FIFO...")
    fifo_stats = check_fifo_for_graph(graph, max_edges=500, step_min=5)

    print(f"Проверено ребер: {fifo_stats['checked_edges']}")
    print(f"Нарушений FIFO: {fifo_stats['violations']}")
    print(f"FIFO выполнено: {fifo_stats['is_fifo_valid']}")

    print("\nПостроение графиков профилей скорости...")
    save_speed_profiles(
        graph,
        os.path.join(FIGURES_DIR, "speed_profiles.png"),
    )

    rows = []
    comparison_rows = []

    for scenario_name, departure_time in DEPARTURE_TIMES.items():
        print("\n" + "=" * 70)
        print(f"Сценарий: {scenario_name}, время отправления: {departure_time} мин")

        print("Статическая маршрутизация...")
        static_result = static_astar_route(graph, start_node, end_node)

        print("Динамическая маршрутизация...")
        dynamic_result = dynamic_astar_route(
            graph,
            start_node,
            end_node,
            departure_time_min=departure_time,
        )

        rows.append(
            build_result_row(
                graph=graph,
                scenario_name=scenario_name,
                departure_time_min=departure_time,
                routing_type="static",
                route_result=static_result,
            )
        )

        rows.append(
            build_result_row(
                graph=graph,
                scenario_name=scenario_name,
                departure_time_min=departure_time,
                routing_type="dynamic",
                route_result=dynamic_result,
            )
        )

        static_dynamic_time = calculate_route_dynamic_time_min(
            graph=graph,
            path_edges=static_result.get("path_edges", []),
            departure_time_min=departure_time,
        )

        dynamic_dynamic_time = calculate_route_dynamic_time_min(
            graph=graph,
            path_edges=dynamic_result.get("path_edges", []),
            departure_time_min=departure_time,
        )

        comparison_rows.append(
            build_comparison_row(
                graph=graph,
                scenario_name=scenario_name,
                departure_time_min=departure_time,
                static_result=static_result,
                dynamic_result=dynamic_result,
                static_dynamic_time_min=static_dynamic_time,
                dynamic_dynamic_time_min=dynamic_dynamic_time,
            )
        )

        map_path = os.path.join(MAPS_DIR, f"route_{scenario_name}.html")

        save_route_map(
            graph=graph,
            static_result=static_result,
            dynamic_result=dynamic_result,
            start_point=START_POINT,
            end_point=END_POINT,
            output_path=map_path,
        )

        print("Статический маршрут:")
        print(static_result)

        print("Динамический маршрут:")
        print(dynamic_result)

        print("Честное сравнение в динамических условиях:")
        print(f"Статический маршрут в динамике: {static_dynamic_time:.2f} мин")
        print(f"Динамический маршрут в динамике: {dynamic_dynamic_time:.2f} мин")
        print(f"Выигрыш: {static_dynamic_time - dynamic_dynamic_time:.2f} мин")

    dataframe = save_results(rows, RESULTS_DIR)
    comparison_dataframe = save_comparison_results(comparison_rows, RESULTS_DIR)

    print("\nИтоговая таблица результатов:")
    print(dataframe)

    print("\nИтоговая таблица честного сравнения:")
    print(comparison_dataframe)


if __name__ == "__main__":
    main()
