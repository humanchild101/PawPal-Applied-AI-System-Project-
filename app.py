import os
from datetime import date, datetime, time

import streamlit as st

from pawpal_agent import SchedulingAgent
from pawpal_system import (
    MAX_AVAILABLE_MINUTES,
    MAX_DURATION_MINUTES,
    MAX_PRIORITY,
    MIN_AVAILABLE_MINUTES,
    MIN_DURATION_MINUTES,
    MIN_PRIORITY,
    Owner,
    Pet,
    Scheduler,
    Task,
)

_FIELD_LABELS = {
    "time": "Time",
    "duration_minutes": "Duration",
    "priority": "Priority",
    "required": "Required",
}


def _format_field_value(field, value):
    if field == "time":
        return datetime.fromisoformat(value).strftime("%I:%M %p") if value else "unscheduled"
    if field == "duration_minutes":
        return f"{value} min"
    if field == "priority":
        return f"{value}/10"
    if field == "required":
        return "yes" if value else "no"
    return str(value)

try:
    if "GROQ_API_KEY" not in os.environ and "GROQ_API_KEY" in st.secrets:
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
except Exception:
    pass

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

if st.session_state.pop("just_applied", False):
    st.success("Change applied.")

if "_available_minutes_to_sync" in st.session_state:
    st.session_state["available_minutes_input"] = st.session_state.pop("_available_minutes_to_sync")

st.markdown(
    """
Welcome to PawPal+ — a pet care planning assistant. Add your pets, give them
tasks, and generate a daily schedule based on priority and available time.
"""
)

with st.expander("Scenario", expanded=False):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps a pet owner plan care tasks
for their pet(s) based on constraints like time, priority, and preferences.
"""
    )

if "owner" not in st.session_state:
    st.session_state.owner = Owner()

owner: Owner = st.session_state.owner

if "scheduler" not in st.session_state:
    st.session_state.scheduler = Scheduler()

scheduler: Scheduler = st.session_state.scheduler

if "agent" not in st.session_state:
    st.session_state.agent = SchedulingAgent(scheduler=scheduler, owner=owner)

agent: SchedulingAgent = st.session_state.agent

with st.expander("🧪 Testing shortcut", expanded=False):
    st.caption("Load a pre-built pet and task list instead of adding them by hand.")
    if st.button("Load sample data"):
        if any(pet.name == "Pu" for pet in owner.pet_list):
            st.warning('Sample data for "Pu" is already loaded.')
        else:
            pu = Pet(name="Pu", species="dog")
            owner.add_pet(pu)
            for description, task_time, duration, priority, frequency, required in [
                ("Feed Pu Morning", time(9, 0), 10, 10, "daily", True),
                ("Bathe Pu", time(11, 0), 40, 10, "daily", True),
                ("Groom Pu", time(10, 30), 20, 6, "", False),
                ("Clean Pu's litter box", time(10, 0), 10, 7, "daily", False),
                ("PuPi Playdate", time(11, 0), 90, 8, "weekly", False),
                ("Calm Pu Tantrum", time(13, 0), 15, 4, "daily", False),
                ("Pu Vet Visit", time(15, 0), 120, 10, "", True),
            ]:
                pu.add_task(Task(
                    description=description,
                    duration_minutes=duration,
                    priority=priority,
                    required=required,
                    time=datetime.combine(date.today(), task_time),
                    frequency=frequency,
                ))
            st.success("Sample data loaded — scroll down to see Pu's tasks.")

st.divider()

st.subheader("Add a Pet")
pet_name = st.text_input("Pet name", placeholder="e.g. Mochi")
species = st.text_input("Species", placeholder="e.g. dog, cat, parrot")

if st.button("Add pet"):
    if not pet_name or not species:
        st.warning("Enter a pet name and species before adding.")
    else:
        owner.add_pet(Pet(name=pet_name, species=species))

if owner.pet_list:
    st.write("Current pets:", ", ".join(pet.name for pet in owner.pet_list))

    pet_to_remove = st.selectbox(
        "Remove a pet", [pet.name for pet in owner.pet_list], index=None,
        placeholder="Select a pet to remove", key="remove_pet_select",
    )
    if st.button("Remove pet"):
        if not pet_to_remove:
            st.warning("Select a pet to remove.")
        else:
            owner.remove_pet(next(pet for pet in owner.pet_list if pet.name == pet_to_remove))
else:
    st.info("No pets yet. Add one above.")

st.divider()

st.subheader("Add a Task")
st.caption("Tasks are added directly to the selected pet's task list.")

pet_names = [pet.name for pet in owner.pet_list]

if not pet_names:
    st.info("Add a pet above before scheduling tasks.")
else:
    selected_pet_name = st.selectbox("Pet", pet_names, index=None, placeholder="Select a pet", key="add_task_pet_select")

    task_title = st.text_input("Task title", placeholder="e.g. Morning walk")
    required = st.checkbox("Required (e.g. feeding, meds)")

    col2, col3 = st.columns(2)
    with col2:
        duration = st.number_input(
            "Duration (minutes)", min_value=MIN_DURATION_MINUTES, max_value=MAX_DURATION_MINUTES, value=None,
        )
    with col3:
        priority = st.number_input(
            "Priority (1-10)", min_value=MIN_PRIORITY, max_value=MAX_PRIORITY, value=None,
            disabled=required,
            help="Required tasks are always scheduled regardless of priority.",
        )
    task_time = st.time_input("Time", value=None)
    frequency = st.selectbox("Repeats", ["", "daily", "weekly"], index=0)

    if st.button("Add task"):
        missing = []
        if not selected_pet_name:
            missing.append("pet")
        if not task_title:
            missing.append("task title")
        if duration is None:
            missing.append("duration")
        if priority is None and not required:
            missing.append("priority")

        if missing:
            st.warning(f"Fill in: {', '.join(missing)}.")
        else:
            selected_pet = next(pet for pet in owner.pet_list if pet.name == selected_pet_name)
            selected_pet.add_task(Task(
                description=task_title,
                duration_minutes=int(duration),
                priority=int(priority) if priority is not None else 10,
                required=required,
                time=datetime.combine(date.today(), task_time) if task_time else None,
                frequency=frequency,
            ))

    st.markdown("##### Filter tasks")
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        status_filter = st.selectbox("Status", ["All", "Pending", "Completed"], key="task_status_filter")
    with fcol2:
        pet_filter = st.selectbox("Pet", ["All"] + pet_names, key="task_pet_filter")

    completed_filter = {"All": None, "Pending": False, "Completed": True}[status_filter]
    pet_name_filter = None if pet_filter == "All" else pet_filter

    filtered_tasks = owner.filter_tasks(completed=completed_filter, pet_name=pet_name_filter)
    task_by_id = {id(task): pet for pet in owner.pet_list for task in pet.task_list}
    task_entries = [(task_by_id[id(task)], task) for task in filtered_tasks]

    if task_entries:
        st.write("Current tasks:")
        st.table([
            {
                "pet": pet.name,
                "task": task.description,
                "time": task.time.strftime("%I:%M %p") if task.time else "unscheduled",
                "duration_minutes": task.duration_minutes,
                "priority": task.priority,
                "repeats": task.frequency if task.frequency else "neither",
                "required": task.required,
                "completed": task.completed,
            }
            for pet, task in task_entries
        ])

        def task_label(entry):
            pet, task = entry
            status = "done" if task.completed else "pending"
            time_str = task.time.strftime("%I:%M %p") if task.time else "unscheduled"
            return f"{pet.name}: {task.description} at {time_str} ({status})"

        task_labels = [task_label(entry) for entry in task_entries]
        selected_task_label = st.selectbox(
            "Manage a task", task_labels, index=None,
            placeholder="Select a task", key="manage_task_select",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Mark complete"):
                if not selected_task_label:
                    st.warning("Select a task to mark complete.")
                else:
                    pet, task = task_entries[task_labels.index(selected_task_label)]
                    pet.complete_task(task)
        with col_b:
            if st.button("Remove task"):
                if not selected_task_label:
                    st.warning("Select a task to remove.")
                else:
                    pet, task = task_entries[task_labels.index(selected_task_label)]
                    pet.remove_task(task)
    elif owner.get_all_tasks():
        st.info("No tasks match the selected filters.")
    else:
        st.info("No tasks yet. Add one above.")

st.divider()

st.subheader("Build Schedule")
st.caption("Runs the scheduler across all pets' tasks to build today's plan.")

available_minutes = st.number_input(
    "Available time today (minutes)", min_value=MIN_AVAILABLE_MINUTES, max_value=MAX_AVAILABLE_MINUTES, value=None,
    key="available_minutes_input",
)

if st.button("Generate schedule"):
    if available_minutes is None:
        st.warning("Enter the available time before generating a schedule.")
    else:
        scheduler.set_available_minutes(int(available_minutes))
        scheduler.build_plan(owner)
        st.session_state.schedule_generated = True

if st.session_state.get("schedule_generated"):
    conflicted_ids = {id(task) for pair in scheduler.time_conflicts for task in pair}

    if scheduler.time_conflicts:
        st.warning(
            f"⚠️ {len(conflicted_ids)} task(s) are scheduled at overlapping "
            "times — see the items marked in red below."
        )

    st.markdown("#### 📅 Daily Schedule")
    by_time = sorted(scheduler.plan, key=lambda task: task.time or datetime.max)
    if by_time:
        for task in by_time:
            time_str = task.time.strftime("%I:%M %p") if task.time else "Unscheduled"
            tag = "🔒 Required" if task.required else f"⭐ Priority {task.priority}/10"
            line = f"- ⏰ **{time_str}** — {task.description} ({task.duration_minutes} min) · {tag}"
            if id(task) in conflicted_ids:
                line += "  :red[⚠ Conflict]"
            st.markdown(line)
    else:
        st.info("No tasks were scheduled.")

    if scheduler.unscheduled:
        st.markdown("#### ⚠️ Not Scheduled — Insufficient Time")
        for task in sorted(scheduler.unscheduled, key=lambda task: task.time or datetime.max):
            time_str = task.time.strftime("%I:%M %p") if task.time else "Unscheduled"
            st.markdown(
                f"- ⏰ **{time_str}** — {task.description} ({task.duration_minutes} min) "
                f"· Priority {task.priority}/10"
            )

    if scheduler.time_conflicts:
        st.markdown("#### 🔀 Overlapping Tasks")
        for task_a, task_b in scheduler.time_conflicts:
            time_a = task_a.time.strftime("%I:%M %p")
            time_b = task_b.time.strftime("%I:%M %p")
            st.markdown(f"- **{task_a.description}** ({time_a}) overlaps **{task_b.description}** ({time_b})")

        if st.button("🤖 Suggest a fix for these conflicts"):
            try:
                with st.spinner("Asking the scheduling assistant to propose a fix..."):
                    agent.ask(
                        "A couple of my tasks overlap today. Can you suggest a change "
                        "that would fix one of the overlaps, and explain why?"
                    )
            except Exception as exc:
                st.error(f"Couldn't get a response from the scheduling assistant: {exc}")

    st.markdown("#### 🧠 Why this plan")
    st.info(scheduler.get_reasoning())

st.divider()

st.subheader("Ask PawPal+")
st.caption(
    "Ask questions about today's schedule, or ask for changes — nothing is "
    "applied until you approve it below."
)

for message in agent.conversation_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

question = st.chat_input("e.g. Why isn't grooming scheduled? Can you fit in a vet visit?")
if question:
    with st.chat_message("user"):
        st.markdown(question)
    try:
        with st.spinner("Thinking..."):
            answer = agent.ask(question)
    except Exception as exc:
        st.error(f"Couldn't get a response from the scheduling assistant: {exc}")
    else:
        with st.chat_message("assistant"):
            st.markdown(answer)

if agent.pending_proposal:
    proposal = agent.pending_proposal
    preview = proposal["preview"]

    st.markdown("#### 📝 Proposed Change")

    if proposal["kind"] == "available_minutes":
        st.write(
            f"**Change your available time today:** {preview['before_minutes']} min → "
            f"{preview['after_minutes']} min"
        )
        st.caption(
            f"After this change: {preview['scheduled_count_after']} task(s) scheduled, "
            f"{preview['conflicts_after']} conflict(s), "
            f"{preview['remaining_minutes_after']} minute(s) left over."
        )
        if preview["unscheduled_after"]:
            st.caption("Still not scheduled: " + ", ".join(preview["unscheduled_after"]))
    else:
        before, after = preview["before"], preview["after"]
        changed_fields = [f for f in ("time", "duration_minutes", "priority", "required") if before[f] != after[f]]

        st.write(f"**{before['description']}**")
        for f in changed_fields:
            label = _FIELD_LABELS[f]
            st.write(f"- **{label}:** {_format_field_value(f, before[f])} → {_format_field_value(f, after[f])}")
        if "required" in changed_fields:
            st.warning("This changes whether the task is guaranteed a slot, regardless of priority.")
        st.caption(
            f"After this change: {preview['conflicts_after']} conflict(s), "
            f"{preview['remaining_minutes_after']} minute(s) remaining."
        )

    col_apply, col_discard = st.columns(2)
    with col_apply:
        if st.button("✅ Apply this change"):
            if proposal["kind"] == "available_minutes":
                st.session_state["_available_minutes_to_sync"] = proposal["minutes"]
            agent.apply_pending_proposal()
            st.session_state.just_applied = True
            st.rerun()
    with col_discard:
        if st.button("❌ Discard"):
            agent.pending_proposal = None
            st.rerun()

    custom_response = st.text_input(
        "Or tell it what you'd rather do instead",
        key="proposal_custom_response",
        placeholder="e.g. try 30 minutes earlier instead",
    )
    if st.button("Send") and custom_response:
        agent.pending_proposal = None
        try:
            with st.spinner("Thinking..."):
                agent.ask(custom_response)
        except Exception as exc:
            st.error(f"Couldn't get a response from the scheduling assistant: {exc}")
