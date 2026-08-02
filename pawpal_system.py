from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

RECURRENCE_INTERVALS = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}

MIN_PRIORITY = 1
MAX_PRIORITY = 10
MIN_DURATION_MINUTES = 1
MAX_DURATION_MINUTES = 240
MIN_AVAILABLE_MINUTES = 0
MAX_AVAILABLE_MINUTES = 600


@dataclass
class Task:
    description: str
    duration_minutes: int
    priority: int  # 1 (lowest) to 10 (highest)
    time: Optional[datetime] = None
    frequency: str = ""
    completed: bool = False
    required: bool = False

    def __post_init__(self) -> None:
        self._validate_priority(self.priority)
        self._validate_duration_minutes(self.duration_minutes)

    def modify_task(self, **updates) -> None:
        """Update any given attributes on this task in place."""
        if "priority" in updates:
            self._validate_priority(updates["priority"])
        if "duration_minutes" in updates:
            self._validate_duration_minutes(updates["duration_minutes"])

        for key, value in updates.items():
            if hasattr(self, key):
                setattr(self, key, value)

    @staticmethod
    def _validate_priority(priority: int) -> None:
        if not MIN_PRIORITY <= priority <= MAX_PRIORITY:
            raise ValueError(f"priority must be between {MIN_PRIORITY} and {MAX_PRIORITY}, got {priority}")

    @staticmethod
    def _validate_duration_minutes(duration_minutes: int) -> None:
        if not MIN_DURATION_MINUTES <= duration_minutes <= MAX_DURATION_MINUTES:
            raise ValueError(
                f"duration_minutes must be between {MIN_DURATION_MINUTES} and "
                f"{MAX_DURATION_MINUTES}, got {duration_minutes}"
            )

    def mark_complete(self) -> Optional["Task"]:
        """Mark this task complete; if it recurs (daily/weekly), return its next occurrence."""
        self.completed = True

        interval = RECURRENCE_INTERVALS.get(self.frequency)
        if interval is None:
            return None

        return Task(
            description=self.description,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            time=self.time + interval if self.time else None,
            frequency=self.frequency,
            required=self.required,
        )


@dataclass
class Pet:
    name: str
    species: str
    meds: list = field(default_factory=list)
    last_walked: Optional[datetime] = None
    last_bathed: Optional[datetime] = None
    last_fed: Optional[datetime] = None
    last_played: Optional[datetime] = None
    task_list: List[Task] = field(default_factory=list)
    special_info: str = ""

    def feed(self) -> None:
        """Record that this pet was just fed."""
        self.last_fed = datetime.now()

    def bathe(self) -> None:
        """Record that this pet was just bathed."""
        self.last_bathed = datetime.now()

    def walk(self) -> None:
        """Record that this pet was just walked."""
        self.last_walked = datetime.now()

    def play(self) -> None:
        """Record that this pet was just played with."""
        self.last_played = datetime.now()

    def add_task(self, task: Task) -> None:
        """Add a task to this pet's task list."""
        self.task_list.append(task)

    def remove_task(self, task: Task) -> None:
        """Remove a task from this pet's task list, if present."""
        if task in self.task_list:
            self.task_list.remove(task)

    def complete_task(self, task: Task) -> None:
        """Mark a task complete, scheduling its next occurrence if it recurs."""
        next_task = task.mark_complete()
        if next_task is not None:
            self.add_task(next_task)


@dataclass
class Owner:
    pet_list: List[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner's pet list."""
        self.pet_list.append(pet)

    def remove_pet(self, pet: Pet) -> None:
        """Remove a pet from this owner's pet list, if present."""
        if pet in self.pet_list:
            self.pet_list.remove(pet)

    def get_all_tasks(self) -> List[Task]:
        """Return every task across all of this owner's pets."""
        return [task for pet in self.pet_list for task in pet.task_list]

    def filter_tasks(self, completed: Optional[bool] = None, pet_name: Optional[str] = None) -> List[Task]:
        """Return tasks across all pets, optionally filtered by completion status or pet name."""
        return [
            task
            for pet in self.pet_list
            if pet_name is None or pet.name == pet_name
            for task in pet.task_list
            if completed is None or task.completed == completed
        ]


@dataclass
class Scheduler:
    available_minutes: int = 0
    plan: List[Task] = field(default_factory=list)
    remaining_minutes: int = 0
    unscheduled: List[Task] = field(default_factory=list)
    time_conflicts: List[Tuple[Task, Task]] = field(default_factory=list)

    def build_plan(self, owner: Owner) -> List[Task]:
        """Build a plan of required tasks plus the highest-priority optional tasks that fit."""
        candidates = [task for task in owner.get_all_tasks() if not task.completed]
        required = sorted((t for t in candidates if t.required), key=lambda t: -t.priority)
        optional = sorted((t for t in candidates if not t.required), key=lambda t: -t.priority)

        plan: List[Task] = list(required)
        remaining_minutes = self.available_minutes - sum(t.duration_minutes for t in required)
        unscheduled: List[Task] = []

        for task in optional:
            if task.duration_minutes <= remaining_minutes:
                plan.append(task)
                remaining_minutes -= task.duration_minutes
            else:
                unscheduled.append(task)

        self.plan = plan
        self.remaining_minutes = remaining_minutes
        self.unscheduled = unscheduled
        self.time_conflicts = self.find_time_conflicts(plan)
        return self.plan

    def find_time_conflicts(self, tasks: List[Task]) -> List[Tuple[Task, Task]]:
        """Return pairs of tasks (same pet or different pets) whose scheduled times overlap."""
        conflicts = []
        for i, task_a in enumerate(tasks):
            for task_b in tasks[i + 1:]:
                if self._times_overlap(task_a, task_b):
                    conflicts.append((task_a, task_b))
        return conflicts

    @staticmethod
    def _times_overlap(task_a: Task, task_b: Task) -> bool:
        """Return True if task_a's and task_b's [time, time + duration) windows intersect."""
        if task_a.time is None or task_b.time is None:
            return False
        end_a = task_a.time + timedelta(minutes=task_a.duration_minutes)
        end_b = task_b.time + timedelta(minutes=task_b.duration_minutes)
        return task_a.time < end_b and task_b.time < end_a

    def set_available_minutes(self, minutes: int) -> None:
        """Set the time budget used by build_plan."""
        self.available_minutes = minutes

    def get_reasoning(self) -> str:
        """Explain why the current plan was chosen."""
        if not self.plan:
            if not self.unscheduled:
                return "No tasks were scheduled: there are no pending tasks to schedule."

            top = sorted(self.unscheduled, key=lambda task: (-task.priority, task.time or datetime.max))[0]
            time_str = top.time.strftime("%I:%M %p") if top.time else "unscheduled"
            deficit = top.duration_minutes - self.remaining_minutes
            return (
                "No tasks were scheduled: none fit within the available time. "
                f'The highest-priority pending task is "{top.description}" at {time_str} '
                f"(priority {top.priority}/10, {top.duration_minutes} min) — increase available "
                f"time by at least {deficit} minute(s) to fit it."
            )

        total_minutes = sum(task.duration_minutes for task in self.plan)
        lines = [
            f"Selected {len(self.plan)} task(s) totaling {total_minutes} of "
            f"{self.available_minutes} available minutes.",
            "Required tasks were guaranteed a slot first; remaining tasks were then added "
            "by priority (10 = highest, 1 = lowest) until the available time ran out:",
        ]
        for task in self.plan:
            tag = "required" if task.required else f"priority {task.priority}/10"
            lines.append(f"  - {task.description} ({tag}, {task.duration_minutes} min)")

        if self.remaining_minutes < 0:
            lines.append("")
            lines.append("**⚠️ Warning: Not Enough Time for Required Tasks**")
            lines.append(
                f"Required tasks alone need {abs(self.remaining_minutes)} more minute(s) "
                f"than your {self.available_minutes}-minute budget. All required tasks were still "
                "included; consider freeing up more time."
            )

        if self.time_conflicts:
            lines.append("")
            lines.append("**⚠️ Warning: Overlapping Tasks**")
            for task_a, task_b in self.time_conflicts:
                lines.append(
                    f"  - \"{task_a.description}\" ({task_a.time.strftime('%I:%M %p')}) overlaps "
                    f"\"{task_b.description}\" ({task_b.time.strftime('%I:%M %p')})"
                )
        return "\n".join(lines)

    def format_schedule(self, title: str = "Daily Schedule") -> str:
        """Render the current plan, unscheduled tasks, and reasoning as a printable string."""
        by_time = sorted(self.plan, key=lambda task: task.time or datetime.max)

        lines = [f"=== {title} ==="]
        for task in by_time:
            time_str = task.time.strftime("%I:%M %p") if task.time else "unscheduled"
            tag = "required" if task.required else f"priority {task.priority}/10"
            lines.append(f"{time_str} — {task.description} ({task.duration_minutes} min, {tag})")

        if self.unscheduled:
            lines.append("")
            lines.append("Not scheduled:")
            for task in sorted(self.unscheduled, key=lambda task: task.time or datetime.max):
                time_str = task.time.strftime("%I:%M %p") if task.time else "unscheduled"
                lines.append(
                    f"{time_str} — {task.description} "
                    f"({task.duration_minutes} min, priority {task.priority}/10) [insufficient time]"
                )

        if self.time_conflicts:
            lines.append("")
            lines.append("Overlapping tasks:")
            for task_a, task_b in self.time_conflicts:
                time_a = task_a.time.strftime("%I:%M %p")
                time_b = task_b.time.strftime("%I:%M %p")
                lines.append(
                    f"{task_a.description} ({time_a}) overlaps {task_b.description} ({time_b}) [time overlap]"
                )

        lines.append("")
        lines.append(self.get_reasoning())
        return "\n".join(lines)
