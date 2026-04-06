from __future__ import annotations


class TutorComposer:
    def compose(self, detected_stack: dict[str, list[str]], logic_summary: dict[str, list[dict[str, object]]]) -> dict[str, list[str] | str]:
        frameworks = detected_stack.get("frameworks", [])
        flows = logic_summary.get("flows", [])
        stack_label = ", ".join(frameworks) if frameworks else "the detected stack"

        return {
            "mental_model": f"Think of this project as a pipeline built from {stack_label}.",
            "run_steps": [
                "Start from the entrypoints and identify the framework-specific app bootstrap.",
                "Trace requests from routes or UI actions into the next layer.",
                "Follow each data flow until you reach persistence or an external boundary.",
            ],
            "pitfalls": [
                "Do not assume every frontend API call has a matching backend route.",
                f"Expect implicit framework behavior even when only {stack_label} is detected.",
                "Generated files can distract from the core application flow.",
            ],
            "self_check_questions": [
                "Which files initialize the main runtime?",
                f"How many cross-layer flows were mapped? {len(flows)}",
                "What would you read first if you needed to debug one request end to end?",
            ],
        }
