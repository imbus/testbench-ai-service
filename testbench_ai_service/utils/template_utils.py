from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def load_template(path: Path, values: dict[str, str]) -> str:
    env = Environment(loader=FileSystemLoader(path.parent))
    template = env.get_template(path.name)
    return template.render(values)


if __name__ == "__main__":
    path = Path(
        r"E:\Projekte\Testbench\testbench-ai-service\testbench_ai_service\templates\de\test_case_set_describer\ai_response.jinja"
    )
    lalal = {"ai_output": "AHHHHHHH", "ai_output1": "HAHHAHHAH"}
    print(load_template(path, lalal))
