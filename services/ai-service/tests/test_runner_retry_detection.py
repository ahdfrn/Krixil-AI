from app.agents.runner import (
    _count_test_attempts,
    _is_test_command_call,
    _last_step_is_a_failed_test_attempt,
    _observation_is_failure,
)
from app.models.agent_step import AgentStep


def _step(
    step_number: int, step_type: str, tool_name: str | None = None, content: dict | None = None
) -> AgentStep:
    return AgentStep(
        step_number=step_number, type=step_type, tool_name=tool_name, content=content or {}
    )


def test_is_test_command_call_matches_pytest_via_run_command_tools():
    assert _is_test_command_call("host.run_command", {"command": "pytest -q"}) is True
    assert _is_test_command_call("code.run_command", {"command": "npm test"}) is True


def test_is_test_command_call_false_for_non_run_command_tools():
    assert _is_test_command_call("host.read_file", {"command": "pytest -q"}) is False


def test_is_test_command_call_false_for_a_non_test_command():
    assert _is_test_command_call("host.run_command", {"command": "ls -la"}) is False


def test_is_test_command_call_false_when_command_is_missing_or_not_a_string():
    assert _is_test_command_call("host.run_command", {}) is False
    assert _is_test_command_call("host.run_command", {"command": 123}) is False


def test_observation_is_failure_for_error_timeout_and_nonzero_exit():
    assert _observation_is_failure({"error": "boom"}) is True
    assert _observation_is_failure({"timed_out": True, "exit_code": 0}) is True
    assert _observation_is_failure({"exit_code": 1}) is True


def test_observation_is_failure_false_for_a_real_success():
    assert _observation_is_failure({"exit_code": 0, "stdout": "ok", "timed_out": False}) is False


def test_count_test_attempts_counts_only_matching_tool_calls():
    steps = [
        _step(1, "tool_call", "host.run_command", {"arguments": {"command": "pytest -q"}}),
        _step(1, "observation", "host.run_command", {"exit_code": 1}),
        _step(2, "tool_call", "host.read_file", {"arguments": {"path": "a.py"}}),
        _step(2, "observation", "host.read_file", {"content": "..."}),
        _step(3, "tool_call", "host.run_command", {"arguments": {"command": "npm test"}}),
    ]
    assert _count_test_attempts(steps) == 2


def test_last_step_is_a_failed_test_attempt_true_case():
    steps = [
        _step(1, "tool_call", "host.run_command", {"arguments": {"command": "pytest -q"}}),
        _step(1, "observation", "host.run_command", {"exit_code": 1, "stderr": "1 failed"}),
    ]
    assert _last_step_is_a_failed_test_attempt(steps) is True


def test_last_step_is_a_failed_test_attempt_false_when_it_passed():
    steps = [
        _step(1, "tool_call", "host.run_command", {"arguments": {"command": "pytest -q"}}),
        _step(1, "observation", "host.run_command", {"exit_code": 0}),
    ]
    assert _last_step_is_a_failed_test_attempt(steps) is False


def test_last_step_is_a_failed_test_attempt_false_when_last_step_is_a_tool_call():
    steps = [_step(1, "tool_call", "host.run_command", {"arguments": {"command": "pytest -q"}})]
    assert _last_step_is_a_failed_test_attempt(steps) is False


def test_last_step_is_a_failed_test_attempt_false_for_a_non_test_command():
    steps = [
        _step(1, "tool_call", "host.write_file", {"arguments": {"path": "a.py"}}),
        _step(1, "observation", "host.write_file", {"error": "disk full"}),
    ]
    assert _last_step_is_a_failed_test_attempt(steps) is False


def test_last_step_is_a_failed_test_attempt_false_for_empty_steps():
    assert _last_step_is_a_failed_test_attempt([]) is False
