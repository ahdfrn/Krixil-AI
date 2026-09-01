from rich.console import Console

from krixil_cli.render import render_step, render_transcript


def _plain(renderable) -> str:
    console = Console(width=100, file=None, record=True, force_terminal=False)
    console.print(renderable)
    return console.export_text()


def test_render_tool_call_step():
    step = {
        "type": "tool_call",
        "tool_name": "host.run_command",
        "content": {"arguments": {"command": "pytest -q"}},
    }
    text = _plain(render_step(step)[0])
    assert "Bash(pytest -q)" in text


def test_render_write_observation_shows_saved():
    step = {
        "type": "observation",
        "tool_name": "host.write_file",
        "content": {"path": "a.py", "written": True},
    }
    text = "".join(_plain(t) for t in render_step(step))
    assert "Saved" in text


def test_render_error_observation_shows_the_message():
    step = {"type": "observation", "tool_name": "host.read_file", "content": {"error": "not found"}}
    text = "".join(_plain(t) for t in render_step(step))
    assert "Error" in text
    assert "not found" in text


def test_render_command_observation_shows_exit_code_and_output():
    step = {
        "type": "observation",
        "tool_name": "host.run_command",
        "content": {"exit_code": 0, "stdout": "ok\n", "stderr": "", "timed_out": False},
    }
    text = "".join(_plain(t) for t in render_step(step))
    assert "Exit 0" in text
    assert "ok" in text


def test_render_transcript_includes_goal_and_final_response():
    steps = [{"type": "final_response", "content": {"content": "All done."}}]
    text = _plain(render_transcript("fix the bug", steps, "completed", 4.2))
    assert "fix the bug" in text
    assert "All done." in text


def test_render_transcript_running_shows_working_indicator():
    text = _plain(render_transcript("fix the bug", [], "running", 2.5))
    assert "Working" in text
