from app.services.chat.rule_fallback_planner import RuleFallbackPlanner


def test_rule_fallback_planner_prefers_repo_map_for_request_path_questions():
    planner = RuleFallbackPlanner()
    result = planner.plan("前端请求如何到后端？")

    assert result.tool_call is not None
    assert result.tool_call.name == "load_repo_map"
