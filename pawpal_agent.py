import dataclasses
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from groq import APIStatusError, Groq

from pawpal_system import MAX_AVAILABLE_MINUTES, MIN_AVAILABLE_MINUTES, Owner, Pet, Scheduler, Task

SYSTEM_PROMPT = """You are PawPal+'s scheduling assistant. You answer questions \
about the owner's pet-care schedule and help fit in or resolve conflicts \
around tasks.

Use the read-only tools to look up the current plan and tasks before \
answering. When the user asks why something is or isn't scheduled, always \
explain the reason first, in plain language, using what the schedule/task \
tools tell you — do not jump straight to proposing a change. Only propose a \
change when the user asks for one, or after you've explained the problem and \
offer a suggestion as a next step.

task_id must always be the exact integer id from a schedule or task \
snapshot — never guess it and never use a task's name or description as \
the id. If you don't already know it, call get_schedule_snapshot or \
get_all_tasks_snapshot first.

If the user wants something changed (a different time, duration, priority, \
or required flag), use propose_change to stage a candidate edit and see its \
effect — try more than one candidate if the first doesn't work, using the \
preview (conflicts, remaining minutes, whether the task ends up scheduled) \
to decide what to try next. If the real problem is not enough total time in \
the day (rather than a task being in the wrong place), use \
propose_available_minutes_change instead to suggest a bigger time budget. \
Only present a change once you've previewed it.

Never mention tool or field names to the user — describe changes in plain, \
everyday language (e.g. "move the walk to 9:00 AM" or "give yourself 90 \
minutes today" instead of naming a function or a variable). When telling the \
user about a task's time, always use its "time_display" value (e.g. "9:00 \
AM") — never repeat the raw "time" timestamp (e.g. "2026-08-02T09:00:00"), \
which is only there for your own calculations. Proposing a change never \
modifies the real schedule — it only stages a proposal that the user must \
approve in the app. Never tell the user a change has been applied; say \
what you're proposing and that they need to confirm it."""

_ALLOWED_UPDATE_FIELDS = {"time", "duration_minutes", "priority", "required"}

_MAX_TOOL_ROUNDS = 8

_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_schedule_snapshot",
            "description": "Return today's plan, unscheduled tasks, and time conflicts.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_tasks_snapshot",
            "description": "Return every task across all pets, including ones not in today's plan.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_available_minutes",
            "description": "Preview the plan under a different time budget, without changing the real schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "integer",
                        "description": "The hypothetical available_minutes to try.",
                    },
                },
                "required": ["minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_change",
            "description": (
                "Stage a candidate edit to one task and preview its effect on the plan. "
                "Only the fields you pass are changed. This never modifies the real "
                "schedule — the user must approve the staged proposal in the app."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "The task_id from a schedule or task snapshot.",
                    },
                    "time": {
                        "type": "string",
                        "description": "New time as an ISO 8601 string, or omit to leave unchanged.",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "New duration in minutes (1-240), or omit to leave unchanged.",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "New priority from 1 (lowest) to 10 (highest), or omit to leave unchanged.",
                    },
                    "required": {
                        "type": "boolean",
                        "description": "New required flag, or omit to leave unchanged.",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_available_minutes_change",
            "description": (
                "Stage a candidate change to the owner's total available time for the "
                "day and preview its effect on the plan. Use this when the real fix is "
                "more (or less) total time, not moving a specific task. This never "
                "modifies the real schedule — the user must approve the staged "
                "proposal in the app."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes": {
                        "type": "integer",
                        "description": (
                            f"The new total available minutes for the day to try "
                            f"({MIN_AVAILABLE_MINUTES}-{MAX_AVAILABLE_MINUTES})."
                        ),
                    },
                },
                "required": ["minutes"],
            },
        },
    },
]


@dataclass
class SchedulingAgent:
    scheduler: Scheduler
    owner: Owner
    model: str = "llama-3.3-70b-versatile"
    conversation_history: List[dict] = field(default_factory=list)
    pending_proposal: Optional[dict] = None

    def ask(self, question: str) -> str:
        client = Groq()
        messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}]
            + self.conversation_history
            + [{"role": "user", "content": question}]
        )

        answer = "I wasn't able to finish that — too many steps were needed."
        for _ in range(_MAX_TOOL_ROUNDS):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=_TOOL_SCHEMAS,
                )
            except APIStatusError as exc:
                if exc.status_code != 400:
                    raise
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your last tool call was invalid: {exc.message} Look up the "
                        "real task_id (an integer) from get_schedule_snapshot or "
                        "get_all_tasks_snapshot before trying again."
                    ),
                })
                continue
            message = response.choices[0].message

            if not message.tool_calls:
                answer = message.content or "I wasn't able to get a response — please try again."
                break

            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments},
                    }
                    for call in message.tool_calls
                ],
            })
            for call in message.tool_calls:
                arguments = json.loads(call.function.arguments) or {}
                result = self._call_tool(call.function.name, arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                })

        self.conversation_history.append({"role": "user", "content": question})
        self.conversation_history.append({"role": "assistant", "content": answer})
        return answer

    def apply_pending_proposal(self) -> None:
        if self.pending_proposal is None:
            return

        if self.pending_proposal["kind"] == "available_minutes":
            self.scheduler.set_available_minutes(self.pending_proposal["minutes"])
            self.scheduler.build_plan(self.owner)
        else:
            task, _ = self._find_task_and_pet(self.pending_proposal["task_id"])
            if task is not None:
                task.modify_task(**self.pending_proposal["updates"])
                self.scheduler.build_plan(self.owner)

        self.pending_proposal = None

    def _call_tool(self, name: str, arguments: dict) -> dict:
        if name == "get_schedule_snapshot":
            return self._get_schedule_snapshot()
        if name == "get_all_tasks_snapshot":
            return self._get_all_tasks_snapshot()
        if name == "simulate_available_minutes":
            return self._simulate_available_minutes(arguments["minutes"])
        if name == "propose_change":
            updates = {
                "time": arguments.get("time"),
                "duration_minutes": arguments.get("duration_minutes"),
                "priority": arguments.get("priority"),
                "required": arguments.get("required"),
            }
            return self._propose_change(arguments["task_id"], updates)
        if name == "propose_available_minutes_change":
            return self._propose_available_minutes_change(arguments["minutes"])
        return {"error": f"Unknown tool: {name}"}

    def _get_schedule_snapshot(self) -> dict:
        return {
            "available_minutes": self.scheduler.available_minutes,
            "remaining_minutes": self.scheduler.remaining_minutes,
            "plan": [self._task_summary(t) for t in self.scheduler.plan],
            "unscheduled": [self._task_summary(t) for t in self.scheduler.unscheduled],
            "conflicts": [
                {"a": self._task_summary(a), "b": self._task_summary(b)}
                for a, b in self.scheduler.time_conflicts
            ],
        }

    def _get_all_tasks_snapshot(self) -> dict:
        return {"tasks": [self._task_summary(t) for t in self.owner.get_all_tasks()]}

    def _simulate_available_minutes(self, minutes: int) -> dict:
        scratch_scheduler = Scheduler(available_minutes=minutes)
        scratch_scheduler.build_plan(self.owner)
        return {
            "available_minutes": minutes,
            "plan": [self._task_summary(t) for t in scratch_scheduler.plan],
            "unscheduled": [self._task_summary(t) for t in scratch_scheduler.unscheduled],
            "remaining_minutes": scratch_scheduler.remaining_minutes,
            "conflicts": len(scratch_scheduler.time_conflicts),
        }

    def _propose_available_minutes_change(self, minutes: int) -> dict:
        if not MIN_AVAILABLE_MINUTES <= minutes <= MAX_AVAILABLE_MINUTES:
            return {
                "error": (
                    f"available_minutes must be between {MIN_AVAILABLE_MINUTES} and "
                    f"{MAX_AVAILABLE_MINUTES}, got {minutes}"
                )
            }

        simulated = self._simulate_available_minutes(minutes)
        preview = {
            "before_minutes": self.scheduler.available_minutes,
            "after_minutes": minutes,
            "scheduled_count_after": len(simulated["plan"]),
            "unscheduled_after": [t["description"] for t in simulated["unscheduled"]],
            "remaining_minutes_after": simulated["remaining_minutes"],
            "conflicts_after": simulated["conflicts"],
        }

        self.pending_proposal = {"kind": "available_minutes", "minutes": minutes, "preview": preview}
        return preview

    def _propose_change(self, task_id: int, updates: dict) -> dict:
        task, pet = self._find_task_and_pet(task_id)
        if task is None:
            return {"error": f"No task found with id {task_id}."}

        parsed_updates = self._parse_updates(updates)
        if not parsed_updates:
            return {"error": "No recognized fields to update were provided."}

        before = self._task_summary(task)
        try:
            updated_task = dataclasses.replace(task, **parsed_updates)
        except ValueError as exc:
            return {"error": str(exc)}

        scratch_pet = dataclasses.replace(
            pet, task_list=[updated_task if t is task else t for t in pet.task_list]
        )
        scratch_owner = dataclasses.replace(
            self.owner, pet_list=[scratch_pet if p is pet else p for p in self.owner.pet_list]
        )

        scratch_scheduler = Scheduler(available_minutes=self.scheduler.available_minutes)
        scratch_scheduler.build_plan(scratch_owner)

        preview = {
            "task_id": task_id,
            "before": before,
            "after": {**self._task_summary(updated_task), "task_id": task_id},
            "scheduled_after": any(t is updated_task for t in scratch_scheduler.plan),
            "remaining_minutes_after": scratch_scheduler.remaining_minutes,
            "conflicts_after": len(scratch_scheduler.time_conflicts),
            "unscheduled_after": [t.description for t in scratch_scheduler.unscheduled],
        }

        self.pending_proposal = {"kind": "task", "task_id": task_id, "updates": parsed_updates, "preview": preview}
        return preview

    def _find_task_and_pet(self, task_id: int) -> Tuple[Optional[Task], Optional[Pet]]:
        for pet in self.owner.pet_list:
            for task in pet.task_list:
                if id(task) == task_id:
                    return task, pet
        return None, None

    @staticmethod
    def _parse_updates(updates: dict) -> dict:
        parsed = {}
        for key, value in updates.items():
            if key not in _ALLOWED_UPDATE_FIELDS or value is None:
                continue
            if key == "time" and isinstance(value, str):
                value = datetime.fromisoformat(value)
            parsed[key] = value
        return parsed

    @staticmethod
    def _task_summary(task: Task) -> dict:
        return {
            "task_id": id(task),
            "description": task.description,
            "time": task.time.isoformat() if task.time else None,
            "time_display": task.time.strftime("%I:%M %p") if task.time else "unscheduled",
            "duration_minutes": task.duration_minutes,
            "priority": task.priority,
            "required": task.required,
            "completed": task.completed,
        }
