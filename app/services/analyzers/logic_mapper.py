from __future__ import annotations


class LogicMapper:
    def map_flows(
        self, frontend_summary: dict[str, list[dict[str, str]]], backend_summary: dict[str, list[dict[str, str]]]
    ) -> dict[str, list[dict[str, str | float]]]:
        backend_routes = [
            route
            for route in backend_summary.get("routes", [])
            if "path" in route and "source_file" in route and "method" in route
        ]
        flows: list[dict[str, str | float]] = []

        for call in frontend_summary.get("api_calls", []):
            matches = [route for route in backend_routes if route["path"] == call.get("url", "")]
            for route in matches:
                flows.append(
                    {
                        "frontend_call": call["url"],
                        "frontend_source": call["source_file"],
                        "backend_route": route["path"],
                        "backend_source": route["source_file"],
                        "backend_method": route["method"],
                        "confidence": 1.0,
                    }
                )

        return {"flows": flows}
