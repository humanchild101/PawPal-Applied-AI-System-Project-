import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest
from groq import BadRequestError, InternalServerError

from pawpal_agent import _MAX_TOOL_ROUNDS, _TOOL_SCHEMAS, SchedulingAgent
from pawpal_system import Owner, Pet, Scheduler, Task


def _api_status_error(error_cls, message, status_code):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_cls(message, response=response, body=None)


def _completion(content=None, tool_calls=None):
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _tool_call(call_id, name, arguments):
    call = MagicMock()
    call.id = call_id
    call.function.name = name
    call.function.arguments = arguments
    return call


def _build_conflicted_schedule():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)

    feed = Task(
        description="Feed", duration_minutes=10, priority=10, required=True,
        time=datetime(2026, 1, 1, 8, 0),
    )
    walk = Task(
        description="Walk", duration_minutes=30, priority=7,
        time=datetime(2026, 1, 1, 8, 5),
    )
    groom = Task(description="Groom", duration_minutes=45, priority=3)
    pet.add_task(feed)
    pet.add_task(walk)
    pet.add_task(groom)

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    scheduler.build_plan(owner)

    agent = SchedulingAgent(scheduler=scheduler, owner=owner)
    return agent, feed, walk, groom


def test_get_schedule_snapshot_reflects_current_plan_and_unscheduled():
    agent, feed, walk, groom = _build_conflicted_schedule()

    snapshot = agent._get_schedule_snapshot()

    assert snapshot["available_minutes"] == 60
    assert snapshot["remaining_minutes"] == 20
    assert [t["description"] for t in snapshot["plan"]] == ["Feed", "Walk"]
    assert [t["description"] for t in snapshot["unscheduled"]] == ["Groom"]


def test_get_schedule_snapshot_includes_conflicts():
    agent, feed, walk, groom = _build_conflicted_schedule()

    snapshot = agent._get_schedule_snapshot()

    assert len(snapshot["conflicts"]) == 1
    conflict = snapshot["conflicts"][0]
    assert {conflict["a"]["description"], conflict["b"]["description"]} == {"Feed", "Walk"}


def test_get_all_tasks_snapshot_includes_every_task_across_pets():
    agent, feed, walk, groom = _build_conflicted_schedule()

    snapshot = agent._get_all_tasks_snapshot()

    descriptions = {t["description"] for t in snapshot["tasks"]}
    assert descriptions == {"Feed", "Walk", "Groom"}


def test_simulate_available_minutes_reflects_hypothetical_budget():
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._simulate_available_minutes(200)

    assert result["available_minutes"] == 200
    assert [t["description"] for t in result["plan"]] == ["Feed", "Walk", "Groom"]
    assert result["unscheduled"] == []


def test_simulate_available_minutes_does_not_mutate_the_real_scheduler():
    agent, feed, walk, groom = _build_conflicted_schedule()
    original_plan = list(agent.scheduler.plan)
    original_remaining = agent.scheduler.remaining_minutes

    agent._simulate_available_minutes(200)

    assert agent.scheduler.available_minutes == 60
    assert agent.scheduler.remaining_minutes == original_remaining
    assert agent.scheduler.plan == original_plan


def test_propose_available_minutes_change_stages_pending_proposal():
    agent, feed, walk, groom = _build_conflicted_schedule()

    preview = agent._propose_available_minutes_change(200)

    assert preview["before_minutes"] == 60
    assert preview["after_minutes"] == 200
    assert preview["scheduled_count_after"] == 3
    assert preview["unscheduled_after"] == []
    assert agent.pending_proposal == {"kind": "available_minutes", "minutes": 200, "preview": preview}


def test_propose_available_minutes_change_does_not_mutate_the_real_scheduler():
    agent, feed, walk, groom = _build_conflicted_schedule()

    agent._propose_available_minutes_change(200)

    assert agent.scheduler.available_minutes == 60


@pytest.mark.parametrize("minutes", [-1, 601, 1000])
def test_propose_available_minutes_change_returns_error_for_out_of_range_minutes(minutes):
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._propose_available_minutes_change(minutes)

    assert "error" in result
    assert agent.pending_proposal is None


def test_propose_change_returns_error_for_unknown_task_id():
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._propose_change(-1, {"priority": 9})

    assert "error" in result
    assert agent.pending_proposal is None


def test_propose_change_returns_error_for_out_of_range_priority():
    agent, feed, walk, groom = _build_conflicted_schedule()
    original_priority = walk.priority

    result = agent._propose_change(id(walk), {"priority": 11})

    assert "error" in result
    assert agent.pending_proposal is None
    assert walk.priority == original_priority


def test_propose_change_returns_error_for_out_of_range_duration():
    agent, feed, walk, groom = _build_conflicted_schedule()
    original_duration = walk.duration_minutes

    result = agent._propose_change(id(walk), {"duration_minutes": 0})

    assert "error" in result
    assert agent.pending_proposal is None
    assert walk.duration_minutes == original_duration


def test_propose_change_returns_error_when_no_recognized_fields_given():
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._propose_change(id(walk), {"foo": "bar", "priority": None})

    assert "error" in result
    assert agent.pending_proposal is None


def test_propose_change_does_not_mutate_the_real_task():
    agent, feed, walk, groom = _build_conflicted_schedule()
    original_time = walk.time

    agent._propose_change(id(walk), {"time": "2026-01-01T09:00:00"})

    assert walk.time == original_time


def test_propose_change_does_not_mutate_the_real_scheduler():
    agent, feed, walk, groom = _build_conflicted_schedule()

    agent._propose_change(id(walk), {"time": "2026-01-01T09:00:00"})

    assert len(agent.scheduler.time_conflicts) == 1


def test_propose_change_preview_shows_conflict_resolved():
    agent, feed, walk, groom = _build_conflicted_schedule()

    preview = agent._propose_change(id(walk), {"time": "2026-01-01T09:00:00"})

    assert preview["conflicts_after"] == 0
    assert preview["scheduled_after"] is True
    assert preview["unscheduled_after"] == ["Groom"]


def test_propose_change_ignores_unrecognized_and_none_fields_in_preview():
    agent, feed, walk, groom = _build_conflicted_schedule()

    preview = agent._propose_change(id(walk), {"duration_minutes": 20, "priority": None, "foo": "bar"})

    assert preview["after"]["duration_minutes"] == 20
    assert preview["after"]["priority"] == walk.priority


def test_propose_change_stages_pending_proposal():
    agent, feed, walk, groom = _build_conflicted_schedule()

    agent._propose_change(id(walk), {"time": "2026-01-01T09:00:00"})

    assert agent.pending_proposal["task_id"] == id(walk)
    assert agent.pending_proposal["updates"] == {"time": datetime(2026, 1, 1, 9, 0)}


def test_apply_pending_proposal_commits_staged_change():
    agent, feed, walk, groom = _build_conflicted_schedule()
    agent._propose_change(id(walk), {"time": "2026-01-01T09:00:00"})

    agent.apply_pending_proposal()

    assert walk.time == datetime(2026, 1, 1, 9, 0)


def test_apply_pending_proposal_rebuilds_the_real_scheduler_plan():
    agent, feed, walk, groom = _build_conflicted_schedule()
    agent._propose_change(id(walk), {"time": "2026-01-01T09:00:00"})

    agent.apply_pending_proposal()

    assert agent.scheduler.time_conflicts == []


def test_apply_pending_proposal_clears_pending_proposal():
    agent, feed, walk, groom = _build_conflicted_schedule()
    agent._propose_change(id(walk), {"time": "2026-01-01T09:00:00"})

    agent.apply_pending_proposal()

    assert agent.pending_proposal is None


def test_apply_pending_proposal_is_a_noop_when_nothing_staged():
    agent, feed, walk, groom = _build_conflicted_schedule()
    original_plan = list(agent.scheduler.plan)

    agent.apply_pending_proposal()

    assert agent.pending_proposal is None
    assert agent.scheduler.plan == original_plan


def test_apply_pending_proposal_handles_available_minutes_kind():
    agent, feed, walk, groom = _build_conflicted_schedule()
    agent._propose_available_minutes_change(200)

    agent.apply_pending_proposal()

    assert agent.scheduler.available_minutes == 200
    assert groom in agent.scheduler.plan
    assert agent.pending_proposal is None


def test_find_task_and_pet_locates_an_existing_task():
    agent, feed, walk, groom = _build_conflicted_schedule()

    found_task, found_pet = agent._find_task_and_pet(id(walk))

    assert found_task is walk
    assert found_pet is agent.owner.pet_list[0]


def test_find_task_and_pet_returns_none_for_unknown_id():
    agent, feed, walk, groom = _build_conflicted_schedule()

    found_task, found_pet = agent._find_task_and_pet(-1)

    assert found_task is None
    assert found_pet is None


def test_parse_updates_keeps_only_allowed_non_none_fields():
    parsed = SchedulingAgent._parse_updates(
        {"time": "2026-01-01T08:30:00", "priority": 9, "bogus": "x", "required": None}
    )

    assert parsed == {"time": datetime(2026, 1, 1, 8, 30), "priority": 9}


def test_task_summary_includes_expected_fields():
    task = Task(
        description="Bathe", duration_minutes=15, priority=4, required=False,
        time=datetime(2026, 1, 1, 10, 0),
    )

    summary = SchedulingAgent._task_summary(task)

    assert summary == {
        "task_id": id(task),
        "description": "Bathe",
        "time": "2026-01-01T10:00:00",
        "time_display": "10:00 AM",
        "duration_minutes": 15,
        "priority": 4,
        "required": False,
        "completed": False,
    }


def test_task_summary_shows_unscheduled_for_no_time():
    task = Task(description="Groom", duration_minutes=20, priority=6)

    summary = SchedulingAgent._task_summary(task)

    assert summary["time"] is None
    assert summary["time_display"] == "unscheduled"


def test_tool_schemas_expose_the_expected_tool_names():
    assert {schema["function"]["name"] for schema in _TOOL_SCHEMAS} == {
        "get_schedule_snapshot",
        "get_all_tasks_snapshot",
        "simulate_available_minutes",
        "propose_change",
        "propose_available_minutes_change",
    }


def test_call_tool_dispatches_get_schedule_snapshot():
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._call_tool("get_schedule_snapshot", {})

    assert result == agent._get_schedule_snapshot()


def test_call_tool_dispatches_get_all_tasks_snapshot():
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._call_tool("get_all_tasks_snapshot", {})

    assert result == agent._get_all_tasks_snapshot()


def test_call_tool_dispatches_simulate_available_minutes():
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._call_tool("simulate_available_minutes", {"minutes": 200})

    assert result == agent._simulate_available_minutes(200)


def test_call_tool_dispatches_propose_change():
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._call_tool("propose_change", {"task_id": id(walk), "time": "2026-01-01T09:00:00"})

    assert result["scheduled_after"] is True
    assert agent.pending_proposal["task_id"] == id(walk)


def test_call_tool_dispatches_propose_available_minutes_change():
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._call_tool("propose_available_minutes_change", {"minutes": 200})

    assert result["after_minutes"] == 200
    assert agent.pending_proposal["kind"] == "available_minutes"
    assert agent.pending_proposal["minutes"] == 200


def test_call_tool_returns_error_for_unknown_tool_name():
    agent, feed, walk, groom = _build_conflicted_schedule()

    result = agent._call_tool("delete_everything", {})

    assert "error" in result


def test_ask_recovers_from_a_400_tool_validation_error_instead_of_crashing():
    agent, feed, walk, groom = _build_conflicted_schedule()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _api_status_error(
            BadRequestError,
            "tool call validation failed: /task_id: expected integer, but got string",
            400,
        ),
        _completion(content="All set.", tool_calls=None),
    ]

    with patch("pawpal_agent.Groq", return_value=mock_client):
        answer = agent.ask("fix the conflict")

    assert answer == "All set."
    assert mock_client.chat.completions.create.call_count == 2
    # the corrective note went back to the model as context, not a crash
    retried_messages = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert "invalid" in retried_messages[-1]["content"]


def test_ask_does_not_swallow_non_400_api_errors():
    agent, feed, walk, groom = _build_conflicted_schedule()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _api_status_error(
        InternalServerError, "server had a bad day", 500
    )

    with patch("pawpal_agent.Groq", return_value=mock_client):
        with pytest.raises(InternalServerError):
            agent.ask("fix the conflict")


# ---- Agentic workflow edge cases: multi-step tool chains and bounded loops ----

def test_ask_chains_multiple_tool_calls_across_rounds_before_answering():
    """Each tool result should inform the next call, not just a single read-then-answer hop."""
    agent, feed, walk, groom = _build_conflicted_schedule()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _completion(tool_calls=[_tool_call("call_1", "get_schedule_snapshot", "{}")]),
        _completion(tool_calls=[
            _tool_call(
                "call_2", "propose_change",
                json.dumps({"task_id": id(walk), "time": "2026-01-01T09:00:00"}),
            )
        ]),
        _completion(content="I moved Walk to 9:00 AM to clear the overlap with Feed."),
    ]

    with patch("pawpal_agent.Groq", return_value=mock_client):
        answer = agent.ask("why do Feed and Walk overlap?")

    assert mock_client.chat.completions.create.call_count == 3
    assert "9:00 AM" in answer
    # the second round's decision (which task to move) depended on the first round's snapshot
    assert agent.pending_proposal["task_id"] == id(walk)
    # staging a candidate never mutates the real task
    assert walk.time == datetime(2026, 1, 1, 8, 5)


def test_ask_stops_after_max_tool_rounds_instead_of_looping_forever():
    agent, feed, walk, groom = _build_conflicted_schedule()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _completion(tool_calls=[_tool_call(f"call_{i}", "get_schedule_snapshot", "{}")])
        for i in range(_MAX_TOOL_ROUNDS)
    ]

    with patch("pawpal_agent.Groq", return_value=mock_client):
        answer = agent.ask("keep checking the schedule")

    assert mock_client.chat.completions.create.call_count == _MAX_TOOL_ROUNDS
    assert answer == "I wasn't able to finish that — too many steps were needed."


def test_ask_returns_fallback_message_when_model_gives_an_empty_response():
    agent, feed, walk, groom = _build_conflicted_schedule()

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _completion(content=None, tool_calls=None)

    with patch("pawpal_agent.Groq", return_value=mock_client):
        answer = agent.ask("hello?")

    assert answer == "I wasn't able to get a response — please try again."


def test_ask_persists_conversation_history_and_replays_it_on_the_next_question():
    agent, feed, walk, groom = _build_conflicted_schedule()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _completion(content="First answer."),
        _completion(content="Second answer."),
    ]

    with patch("pawpal_agent.Groq", return_value=mock_client):
        agent.ask("first question")
        agent.ask("second question")

    assert agent.conversation_history == [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "First answer."},
        {"role": "user", "content": "second question"},
        {"role": "assistant", "content": "Second answer."},
    ]
    second_call_messages = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert {"role": "user", "content": "first question"} in second_call_messages
    assert {"role": "assistant", "content": "First answer."} in second_call_messages


# ---- Robustness to malformed or hallucinated model output ----

def test_ask_handles_null_string_arguments_for_a_zero_argument_tool():
    """Groq occasionally sends the JSON literal "null" instead of "{}" for no-arg tools."""
    agent, feed, walk, groom = _build_conflicted_schedule()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _completion(tool_calls=[_tool_call("call_1", "get_schedule_snapshot", "null")]),
        _completion(content="Here's the current plan."),
    ]

    with patch("pawpal_agent.Groq", return_value=mock_client):
        answer = agent.ask("what's scheduled?")

    assert answer == "Here's the current plan."
    tool_result_message = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"][-1]
    assert "error" not in json.loads(tool_result_message["content"])


def test_ask_recovers_when_model_references_an_unknown_task_id():
    """A hallucinated/stale task_id should surface as a tool error the model can react to, not a crash."""
    agent, feed, walk, groom = _build_conflicted_schedule()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        _completion(tool_calls=[
            _tool_call("call_1", "propose_change", json.dumps({"task_id": 999999, "priority": 9}))
        ]),
        _completion(content="I couldn't find that task — could you confirm which one you mean?"),
    ]

    with patch("pawpal_agent.Groq", return_value=mock_client):
        answer = agent.ask("bump the priority on that task")

    tool_result_message = mock_client.chat.completions.create.call_args_list[1].kwargs["messages"][-1]
    assert "No task found" in tool_result_message["content"]
    assert agent.pending_proposal is None
    assert "confirm" in answer


def test_call_tool_enforces_the_priority_guardrail_through_the_same_path_the_model_uses():
    agent, feed, walk, groom = _build_conflicted_schedule()
    original_priority = walk.priority

    result = agent._call_tool("propose_change", {"task_id": id(walk), "priority": 11})

    assert "error" in result
    assert agent.pending_proposal is None
    assert walk.priority == original_priority


# ---- Retrieval (RAG-style context) edge cases ----

def test_snapshots_on_an_owner_with_no_pets_return_empty_context_without_crashing():
    owner = Owner()
    scheduler = Scheduler()
    scheduler.build_plan(owner)
    agent = SchedulingAgent(scheduler=scheduler, owner=owner)

    assert agent._get_schedule_snapshot() == {
        "available_minutes": 0,
        "remaining_minutes": 0,
        "plan": [],
        "unscheduled": [],
        "conflicts": [],
    }
    assert agent._get_all_tasks_snapshot() == {"tasks": []}


def test_schedule_snapshot_reflects_an_applied_change_immediately():
    """The next turn's retrieved context must be fresh, not the pre-apply state."""
    agent, feed, walk, groom = _build_conflicted_schedule()
    agent._propose_change(id(walk), {"time": "2026-01-01T09:00:00"})

    agent.apply_pending_proposal()
    snapshot = agent._get_schedule_snapshot()

    assert snapshot["conflicts"] == []
    walk_summary = next(t for t in snapshot["plan"] if t["description"] == "Walk")
    assert walk_summary["time_display"] == "09:00 AM"
