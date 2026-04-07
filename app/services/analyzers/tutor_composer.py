from __future__ import annotations


class TutorComposer:
    def compose(self, detected_stack: dict[str, list[str]], logic_summary: dict[str, list[dict[str, object]]]) -> dict[str, object]:
        frameworks = detected_stack.get("frameworks", [])
        flows = logic_summary.get("flows", [])
        stack_label = ", ".join(frameworks) if frameworks else "the detected stack"

        return {
            "mental_model": f"Think of this project as a pipeline built from {stack_label}.",
            "request_lifecycle": [
                "A user action or route hit enters the application through a framework entrypoint.",
                "The request is routed into backend or frontend logic depending on the stack.",
                "Data crosses service boundaries before the UI or API response is returned.",
            ],
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
            "next_steps": [
                "Open the main entrypoint file and confirm how the runtime starts.",
                "Trace one route or UI event all the way to its side effects.",
                "Modify one small behavior and rerun the relevant test or app flow.",
            ],
            "self_check_questions": [
                "Which files initialize the main runtime?",
                f"How many cross-layer flows were mapped? {len(flows)}",
                "What would you read first if you needed to debug one request end to end?",
            ],
            "faq_entries": [
                {
                    "question": "Where should I start reading the code?",
                    "answer": "Start with the main entrypoint and then follow one concrete request path.",
                }
            ],
            "code_walkthroughs": [
                {
                    "title": "Trace the first important file",
                    "source_file": "README.md" if "README.md" in frameworks else "app/main.py",
                    "snippet": "Identify the bootstrap file and follow the first meaningful route or action.",
                    "notes": ["Use this as the anchor before exploring helper modules."],
                }
            ],
        }
