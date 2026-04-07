from __future__ import annotations

import re

import yaml
_ENV_VAR_PATTERN = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]+)\s*=", re.MULTILINE)


class DeployAnalyzer:
    def analyze(self, file_paths: list[str], file_contents: dict[str, str]) -> dict[str, object]:
        environment_files = [path for path in file_paths if path.lower().endswith(".env") or path.endswith(".env.example")]
        manifests = [path for path in file_paths if self._is_manifest(path)]
        services = self._extract_services(file_contents)
        environment_variables = self._extract_environment_variables(environment_files, file_contents)
        kubernetes_resources = self._extract_kubernetes_resources(manifests, file_contents)
        return {
            "services": services,
            "environment_files": environment_files,
            "manifests": manifests,
            "environment_variables": environment_variables,
            "kubernetes_resources": kubernetes_resources,
        }

    def _extract_services(self, file_contents: dict[str, str]) -> list[dict[str, object]]:
        services: list[dict[str, object]] = []
        for source_file, content in sorted(file_contents.items()):
            if source_file not in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
                continue
            payload = yaml.safe_load(content) or {}
            compose_services = payload.get("services", {})
            if not isinstance(compose_services, dict):
                continue
            for service_name, service_payload in compose_services.items():
                if not isinstance(service_payload, dict):
                    service_payload = {}
                services.append(
                    {
                        "name": str(service_name),
                        "source_file": source_file,
                        "ports": [str(port) for port in service_payload.get("ports", [])],
                        "depends_on": self._normalize_depends_on(service_payload.get("depends_on")),
                    }
                )
        return services

    def _extract_environment_variables(self, environment_files: list[str], file_contents: dict[str, str]) -> list[dict[str, str]]:
        variables: list[dict[str, str]] = []
        for source_file in environment_files:
            content = file_contents.get(source_file, "")
            for match in _ENV_VAR_PATTERN.finditer(content):
                variables.append({"key": match.group("key"), "source_file": source_file})
        return variables

    def _extract_kubernetes_resources(self, manifests: list[str], file_contents: dict[str, str]) -> list[dict[str, str]]:
        resources: list[dict[str, str]] = []
        for source_file in manifests:
            content = file_contents.get(source_file, "")
            for document in yaml.safe_load_all(content):
                if not isinstance(document, dict):
                    continue
                kind = document.get("kind")
                metadata = document.get("metadata", {})
                name = metadata.get("name") if isinstance(metadata, dict) else None
                if kind and name:
                    resources.append(
                        {
                            "kind": str(kind),
                            "name": str(name),
                            "source_file": source_file,
                        }
                    )
        return resources

    def _normalize_depends_on(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, dict):
            return [str(key) for key in value.keys()]
        return []

    def _is_manifest(self, path: str) -> bool:
        lowered = path.lower()
        return lowered.startswith("k8s/") or lowered.startswith("kubernetes/") or lowered.endswith(".yaml") or lowered.endswith(".yml")
