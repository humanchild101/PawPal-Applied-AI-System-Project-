"""End-to-end UI tests for app.py, driven via Streamlit's AppTest harness.

The scheduling assistant (SchedulingAgent.ask) is mocked throughout so these
tests never make a real network call or require a GROQ_API_KEY.
"""

from datetime import datetime
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP_PATH = "app.py"


def _fresh_app():
    at = AppTest.from_file(APP_PATH, default_timeout=10)
    at.run()
    return at


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def _text_input(at, label):
    return next(t for t in at.text_input if t.label == label)


def _number_input(at, label):
    return next(n for n in at.number_input if n.label == label)


def _selectbox(at, label):
    return next(s for s in at.selectbox if s.label == label)


def _checkbox(at, label):
    return next(c for c in at.checkbox if c.label == label)


def _add_pet(at, name="Mochi", species="dog"):
    _text_input(at, "Pet name").set_value(name).run()
    _text_input(at, "Species").set_value(species).run()
    _button(at, "Add pet").click().run()


def _load_sample_data(at):
    _button(at, "Load sample data").click().run()


def _generate_schedule(at, minutes):
    _number_input(at, "Available time today (minutes)").set_value(minutes).run()
    _button(at, "Generate schedule").click().run()


# ---- Adding / removing pets ----

def test_empty_state_shows_no_pets_and_no_tasks_messages():
    at = _fresh_app()

    assert any("No pets yet" in i.value for i in at.info)
    assert any("Add a pet above before scheduling tasks" in i.value for i in at.info)


def test_add_pet_without_filling_both_fields_shows_a_warning():
    at = _fresh_app()

    _button(at, "Add pet").click().run()

    assert any("Enter a pet name and species" in w.value for w in at.warning)
    assert at.session_state.owner.pet_list == []


def test_add_pet_flow_adds_the_pet_to_the_real_owner():
    at = _fresh_app()

    _add_pet(at, "Mochi", "dog")

    assert [p.name for p in at.session_state.owner.pet_list] == ["Mochi"]


def test_remove_pet_flow_removes_the_pet_from_the_real_owner():
    at = _fresh_app()
    _add_pet(at, "Mochi", "dog")

    _selectbox(at, "Remove a pet").select("Mochi").run()
    _button(at, "Remove pet").click().run()

    assert at.session_state.owner.pet_list == []


# ---- Testing shortcut (sample data) ----

def test_load_sample_data_adds_one_pet_and_seven_tasks():
    at = _fresh_app()

    _load_sample_data(at)

    owner = at.session_state.owner
    assert [p.name for p in owner.pet_list] == ["Pu"]
    assert len(owner.get_all_tasks()) == 7


def test_loading_sample_data_twice_warns_instead_of_duplicating():
    at = _fresh_app()
    _load_sample_data(at)

    _load_sample_data(at)

    assert len(at.session_state.owner.get_all_tasks()) == 7
    assert any("already loaded" in w.value for w in at.warning)


# ---- Adding tasks ----

def test_add_task_without_required_fields_shows_a_warning():
    at = _fresh_app()
    _add_pet(at, "Mochi", "dog")

    _button(at, "Add task").click().run()

    assert any("Fill in" in w.value for w in at.warning)
    assert at.session_state.owner.get_all_tasks() == []


def test_add_task_marked_required_does_not_need_a_priority_and_defaults_to_ten():
    at = _fresh_app()
    _add_pet(at, "Mochi", "dog")

    _selectbox(at, "Pet").select("Mochi").run()
    _text_input(at, "Task title").set_value("Feed").run()
    _checkbox(at, "Required (e.g. feeding, meds)").check().run()
    _number_input(at, "Duration (minutes)").set_value(10).run()

    _button(at, "Add task").click().run()

    tasks = at.session_state.owner.get_all_tasks()
    assert len(tasks) == 1
    assert tasks[0].required is True
    assert tasks[0].priority == 10


def test_add_task_with_an_explicit_priority_is_stored_as_given():
    at = _fresh_app()
    _add_pet(at, "Mochi", "dog")

    _selectbox(at, "Pet").select("Mochi").run()
    _text_input(at, "Task title").set_value("Walk").run()
    _number_input(at, "Duration (minutes)").set_value(20).run()
    _number_input(at, "Priority (1-10)").set_value(7).run()

    _button(at, "Add task").click().run()

    tasks = at.session_state.owner.get_all_tasks()
    assert len(tasks) == 1
    assert tasks[0].required is False
    assert tasks[0].priority == 7


# ---- Building the schedule ----

def test_generate_schedule_without_available_minutes_shows_a_warning():
    at = _fresh_app()
    _load_sample_data(at)

    _button(at, "Generate schedule").click().run()

    assert any("Enter the available time" in w.value for w in at.warning)


def test_generate_schedule_flow_renders_the_plan_and_reasoning():
    at = _fresh_app()
    _load_sample_data(at)

    _generate_schedule(at, 600)

    assert any("Daily Schedule" in m.value for m in at.markdown)
    assert at.session_state.scheduler.plan
    assert at.info  # get_reasoning() is rendered via st.info


def test_generate_schedule_flags_the_sample_datas_overlapping_tasks():
    """Bathe Pu and PuPi Playdate both start at 11:00 in the sample dataset."""
    at = _fresh_app()
    _load_sample_data(at)

    _generate_schedule(at, 600)

    assert any("overlapping" in w.value.lower() for w in at.warning)
    assert at.session_state.scheduler.time_conflicts
    assert any("🔀 Overlapping Tasks" in m.value for m in at.markdown)


# ---- Chat with the scheduling assistant (mocked) ----

def test_chat_question_calls_the_agent_and_renders_its_answer():
    at = _fresh_app()

    with patch("pawpal_agent.SchedulingAgent.ask", return_value="Here's what's scheduled today.") as mock_ask:
        at.chat_input[0].set_value("What's scheduled?").run()

    mock_ask.assert_called_once_with("What's scheduled?")
    assert any(
        m.value == "Here's what's scheduled today."
        for cm in at.chat_message
        for m in cm.markdown
    )


def test_chat_question_shows_a_clean_error_instead_of_a_raw_traceback():
    at = _fresh_app()

    with patch("pawpal_agent.SchedulingAgent.ask", side_effect=RuntimeError("boom")):
        at.chat_input[0].set_value("What's scheduled?").run()

    assert any("Couldn't get a response from the scheduling assistant" in e.value for e in at.error)


def test_suggest_a_fix_button_asks_the_agent_about_the_conflict():
    at = _fresh_app()
    _load_sample_data(at)
    _generate_schedule(at, 600)

    with patch("pawpal_agent.SchedulingAgent.ask", return_value="ok") as mock_ask:
        _button(at, "🤖 Suggest a fix for these conflicts").click().run()

    mock_ask.assert_called_once()
    assert "overlap" in mock_ask.call_args.args[0]


# ---- Proposed-change review card (apply / discard) ----

def test_apply_proposed_task_change_updates_the_real_schedule():
    at = _fresh_app()
    _load_sample_data(at)
    _generate_schedule(at, 600)

    agent = at.session_state.agent
    playdate = next(t for t in agent.owner.get_all_tasks() if t.description == "PuPi Playdate")
    agent._propose_change(id(playdate), {"time": "2026-01-01T09:30:00"})
    at.run()

    assert any("Proposed Change" in m.value for m in at.markdown)

    _button(at, "✅ Apply this change").click().run()

    assert agent.pending_proposal is None
    assert playdate.time == datetime(2026, 1, 1, 9, 30)
    assert any("Change applied." in s.value for s in at.success)


def test_discard_proposed_change_clears_it_without_mutating_the_task():
    at = _fresh_app()
    _load_sample_data(at)
    _generate_schedule(at, 600)

    agent = at.session_state.agent
    playdate = next(t for t in agent.owner.get_all_tasks() if t.description == "PuPi Playdate")
    original_time = playdate.time
    agent._propose_change(id(playdate), {"time": "2026-01-01T09:30:00"})
    at.run()

    _button(at, "❌ Discard").click().run()

    assert agent.pending_proposal is None
    assert playdate.time == original_time


def test_apply_proposed_available_minutes_change_syncs_the_number_input_widget():
    """Regression test: applying this proposal must not raise StreamlitAPIException
    from writing to available_minutes_input after the widget has rendered."""
    at = _fresh_app()
    _load_sample_data(at)
    _generate_schedule(at, 60)

    agent = at.session_state.agent
    agent._propose_available_minutes_change(600)
    at.run()

    _button(at, "✅ Apply this change").click().run()

    assert agent.scheduler.available_minutes == 600
    assert _number_input(at, "Available time today (minutes)").value == 600
