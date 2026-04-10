from __future__ import annotations


class TutorComposer:
    def compose(self, detected_stack: dict[str, list[str]], logic_summary: dict[str, list[dict[str, object]]]) -> dict[str, object]:
        frameworks = detected_stack.get("frameworks", [])
        flows = logic_summary.get("flows", [])
        stack_label = ", ".join(frameworks) if frameworks else "当前识别出的技术栈"

        return {
            "mental_model": f"把这个项目理解为由 {stack_label} 组成的一条处理链路。",
            "request_lifecycle": [
                "用户操作或路由请求会先进入框架入口文件。",
                "请求会按照当前技术栈被分发到前端页面逻辑或后端接口逻辑。",
                "数据在模块边界之间流转后，最终返回页面渲染结果或接口响应。",
            ],
            "run_steps": [
                "先找到项目入口文件，确认应用是如何启动的。",
                "沿着一个真实的路由或界面操作继续追踪到下一层逻辑。",
                "顺着数据流一直看到持久化层或外部服务边界为止。",
            ],
            "pitfalls": [
                "不要想当然地认为每个前端请求都能在后端找到一一对应的接口。",
                f"即使当前只识别到 {stack_label}，也要警惕框架隐式行为带来的跳转。",
                "生成产物、脚本和配置文件容易分散注意力，要优先抓主链路。",
            ],
            "next_steps": [
                "打开主入口文件，确认运行时从哪里开始。",
                "挑一条路由或一个界面事件，完整追到它的副作用。",
                "修改一个很小的行为，再跑一次对应测试或手工流程验证理解。",
            ],
            "self_check_questions": [
                "入口运行时是由哪些文件初始化的？",
                f"当前一共梳理出了多少条跨层链路？{len(flows)}",
                "如果要排查一条请求，你会先从哪个文件开始读起？",
            ],
            "faq_entries": [
                {
                    "question": "我应该从哪里开始读代码？",
                    "answer": "先看主入口文件，再顺着一条具体请求或界面操作往下追。",
                }
            ],
            "code_walkthroughs": [
                {
                    "title": "先读第一个关键文件",
                    "source_file": "README.md" if "README.md" in frameworks else "app/main.py",
                    "snippet": "先锁定启动入口，再顺着第一条有意义的路由或交互往下读。",
                    "notes": ["先把主链路看懂，再扩展到周边辅助模块。"],
                }
            ],
        }
