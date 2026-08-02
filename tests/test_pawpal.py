from datetime import datetime

import pytest

from pawpal_system import Owner, Pet, Scheduler, Task


def test_mark_complete_changes_task_status():
    task = Task(description="Walk", duration_minutes=10, priority=5)
    assert task.completed is False

    task.mark_complete()

    assert task.completed is True


def test_mark_complete_returns_none_for_non_recurring_task():
    task = Task(description="Walk", duration_minutes=10, priority=5)

    assert task.mark_complete() is None


def test_mark_complete_returns_next_occurrence_for_daily_task():
    task = Task(
        description="Feed",
        duration_minutes=5,
        priority=5,
        frequency="daily",
        time=datetime(2026, 1, 1, 8, 0),
    )

    next_task = task.mark_complete()

    assert next_task is not None
    assert next_task.description == "Feed"
    assert next_task.frequency == "daily"
    assert next_task.completed is False
    assert next_task.time == datetime(2026, 1, 2, 8, 0)


def test_mark_complete_returns_next_occurrence_for_weekly_task():
    task = Task(
        description="Bathe",
        duration_minutes=15,
        priority=3,
        frequency="weekly",
        time=datetime(2026, 1, 1, 9, 0),
    )

    next_task = task.mark_complete()

    assert next_task is not None
    assert next_task.time == datetime(2026, 1, 8, 9, 0)


def test_complete_task_adds_next_occurrence_to_pet_task_list():
    pet = Pet(name="Mochi", species="dog")
    task = Task(description="Feed", duration_minutes=5, priority=5, frequency="daily")
    pet.add_task(task)

    pet.complete_task(task)

    assert len(pet.task_list) == 2
    assert task.completed is True
    assert pet.task_list[1].completed is False


def test_complete_task_does_not_add_occurrence_for_non_recurring_task():
    pet = Pet(name="Mochi", species="dog")
    task = Task(description="Walk", duration_minutes=10, priority=5)
    pet.add_task(task)

    pet.complete_task(task)

    assert len(pet.task_list) == 1


def test_modify_task_updates_the_given_field():
    task = Task(description="Walk", duration_minutes=10, priority=5)

    task.modify_task(priority=8)

    assert task.priority == 8


@pytest.mark.parametrize("priority", [0, -1, 11, 100])
def test_task_construction_rejects_out_of_range_priority(priority):
    with pytest.raises(ValueError):
        Task(description="Walk", duration_minutes=10, priority=priority)


@pytest.mark.parametrize("duration_minutes", [0, -5, 241, 1000])
def test_task_construction_rejects_out_of_range_duration(duration_minutes):
    with pytest.raises(ValueError):
        Task(description="Walk", duration_minutes=duration_minutes, priority=5)


def test_modify_task_rejects_out_of_range_priority():
    task = Task(description="Walk", duration_minutes=10, priority=5)

    with pytest.raises(ValueError):
        task.modify_task(priority=11)

    assert task.priority == 5


def test_modify_task_rejects_out_of_range_duration():
    task = Task(description="Walk", duration_minutes=10, priority=5)

    with pytest.raises(ValueError):
        task.modify_task(duration_minutes=0)

    assert task.duration_minutes == 10


def test_modify_task_does_not_partially_apply_when_one_field_is_invalid():
    task = Task(description="Walk", duration_minutes=10, priority=5)

    with pytest.raises(ValueError):
        task.modify_task(description="Run", priority=11)

    assert task.description == "Walk"
    assert task.priority == 5


def test_adding_task_increases_pet_task_count():
    pet = Pet(name="Mochi", species="dog")
    assert len(pet.task_list) == 0

    pet.add_task(Task(description="Walk", duration_minutes=10, priority=5))

    assert len(pet.task_list) == 1


def test_removing_task_decreases_pet_task_count():
    pet = Pet(name="Mochi", species="dog")
    task = Task(description="Walk", duration_minutes=10, priority=5)
    pet.add_task(task)

    pet.remove_task(task)

    assert len(pet.task_list) == 0


def test_feed_updates_last_fed():
    pet = Pet(name="Mochi", species="dog")
    assert pet.last_fed is None

    pet.feed()

    assert isinstance(pet.last_fed, datetime)


def test_walk_updates_last_walked():
    pet = Pet(name="Mochi", species="dog")
    assert pet.last_walked is None

    pet.walk()

    assert isinstance(pet.last_walked, datetime)


def test_adding_pet_increases_owner_pet_count():
    owner = Owner()
    assert len(owner.pet_list) == 0

    owner.add_pet(Pet(name="Mochi", species="dog"))

    assert len(owner.pet_list) == 1


def test_removing_pet_decreases_owner_pet_count():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)

    owner.remove_pet(pet)

    assert len(owner.pet_list) == 0


def test_get_all_tasks_includes_tasks_from_every_pet():
    owner = Owner()
    dog = Pet(name="Mochi", species="dog")
    cat = Pet(name="Whiskers", species="cat")
    owner.add_pet(dog)
    owner.add_pet(cat)
    dog.add_task(Task(description="Walk", duration_minutes=10, priority=5))
    cat.add_task(Task(description="Feed cat", duration_minutes=5, priority=5))

    assert len(owner.get_all_tasks()) == 2


def test_build_plan_always_includes_required_tasks():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    feed = Task(description="Feed", duration_minutes=50, priority=1, required=True)
    pet.add_task(feed)

    scheduler = Scheduler()
    scheduler.set_available_minutes(10)
    plan = scheduler.build_plan(owner)

    assert feed in plan


def test_build_plan_detects_overlap_between_different_pets():
    owner = Owner()
    dog = Pet(name="Mochi", species="dog")
    cat = Pet(name="Whiskers", species="cat")
    owner.add_pet(dog)
    owner.add_pet(cat)
    walk = Task(
        description="Walk", duration_minutes=30, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 0),
    )
    feed_cat = Task(
        description="Feed cat", duration_minutes=10, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 15),
    )
    dog.add_task(walk)
    cat.add_task(feed_cat)

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    scheduler.build_plan(owner)

    assert (walk, feed_cat) in scheduler.time_conflicts


def test_build_plan_detects_overlap_for_same_pet():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    walk = Task(
        description="Walk", duration_minutes=30, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 0),
    )
    play = Task(
        description="Play", duration_minutes=30, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 20),
    )
    pet.add_task(walk)
    pet.add_task(play)

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    scheduler.build_plan(owner)

    assert (walk, play) in scheduler.time_conflicts


def test_build_plan_reports_no_conflicts_for_back_to_back_tasks():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    walk = Task(
        description="Walk", duration_minutes=30, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 0),
    )
    feed = Task(
        description="Feed", duration_minutes=10, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 30),
    )
    pet.add_task(walk)
    pet.add_task(feed)

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    scheduler.build_plan(owner)

    assert scheduler.time_conflicts == []


def test_filter_tasks_by_completion_status():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    done = Task(description="Done", duration_minutes=10, priority=5, completed=True)
    pending = Task(description="Pending", duration_minutes=10, priority=5)
    pet.add_task(done)
    pet.add_task(pending)

    assert owner.filter_tasks(completed=True) == [done]
    assert owner.filter_tasks(completed=False) == [pending]


def test_filter_tasks_by_pet_name():
    owner = Owner()
    dog = Pet(name="Mochi", species="dog")
    cat = Pet(name="Whiskers", species="cat")
    owner.add_pet(dog)
    owner.add_pet(cat)
    dog_task = Task(description="Walk", duration_minutes=10, priority=5)
    cat_task = Task(description="Feed cat", duration_minutes=5, priority=5)
    dog.add_task(dog_task)
    cat.add_task(cat_task)

    assert owner.filter_tasks(pet_name="Mochi") == [dog_task]
    assert owner.filter_tasks(pet_name="Whiskers") == [cat_task]


def test_build_plan_excludes_completed_tasks():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    done = Task(description="Done", duration_minutes=10, priority=5, completed=True)
    pet.add_task(done)

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    plan = scheduler.build_plan(owner)

    assert done not in plan


# ---- Filtering by pet or completion status ----

def test_filter_tasks_with_no_arguments_returns_everything():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    pet.add_task(Task(description="Walk", duration_minutes=10, priority=5))
    pet.add_task(Task(description="Feed", duration_minutes=5, priority=5, completed=True))

    assert len(owner.filter_tasks()) == 2


def test_filter_tasks_combining_completed_and_pet_name():
    owner = Owner()
    dog = Pet(name="Mochi", species="dog")
    cat = Pet(name="Whiskers", species="cat")
    owner.add_pet(dog)
    owner.add_pet(cat)
    dog_pending = Task(description="Walk", duration_minutes=10, priority=5)
    dog_done = Task(description="Bathe", duration_minutes=10, priority=5, completed=True)
    cat_pending = Task(description="Feed cat", duration_minutes=5, priority=5)
    dog.add_task(dog_pending)
    dog.add_task(dog_done)
    cat.add_task(cat_pending)

    assert owner.filter_tasks(completed=False, pet_name="Mochi") == [dog_pending]


def test_filter_tasks_returns_empty_list_when_nothing_matches():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    pet.add_task(Task(description="Walk", duration_minutes=10, priority=5))

    assert owner.filter_tasks(pet_name="Nonexistent") == []
    assert owner.filter_tasks(completed=True) == []


# ---- Sorting tasks by time ----

def test_format_schedule_lists_tasks_in_chronological_order():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    late = Task(
        description="Evening walk", duration_minutes=10, priority=5, required=True,
        time=datetime(2026, 1, 1, 20, 0),
    )
    early = Task(
        description="Morning feed", duration_minutes=10, priority=5, required=True,
        time=datetime(2026, 1, 1, 6, 0),
    )
    pet.add_task(late)
    pet.add_task(early)

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    scheduler.build_plan(owner)
    schedule_text = scheduler.format_schedule()

    assert schedule_text.index("Morning feed") < schedule_text.index("Evening walk")


def test_format_schedule_places_untimed_tasks_after_timed_ones():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    untimed = Task(description="Someday task", duration_minutes=10, priority=5, required=True)
    timed = Task(
        description="Morning walk", duration_minutes=10, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 0),
    )
    pet.add_task(untimed)
    pet.add_task(timed)

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    scheduler.build_plan(owner)
    schedule_text = scheduler.format_schedule()

    assert schedule_text.index("Morning walk") < schedule_text.index("Someday task")


# ---- Time conflict handling edge cases ----

def test_find_time_conflicts_ignores_tasks_without_a_time():
    walk = Task(description="Walk", duration_minutes=30, priority=5)
    feed = Task(description="Feed", duration_minutes=10, priority=5)

    scheduler = Scheduler()

    assert scheduler.find_time_conflicts([walk, feed]) == []


def test_find_time_conflicts_detects_full_containment():
    long_task = Task(
        description="Long walk", duration_minutes=60, priority=5,
        time=datetime(2026, 1, 1, 8, 0),
    )
    short_task = Task(
        description="Quick photo", duration_minutes=5, priority=5,
        time=datetime(2026, 1, 1, 8, 30),
    )

    scheduler = Scheduler()
    conflicts = scheduler.find_time_conflicts([long_task, short_task])

    assert (long_task, short_task) in conflicts


def test_find_time_conflicts_detects_identical_start_times():
    walk = Task(description="Walk", duration_minutes=15, priority=5, time=datetime(2026, 1, 1, 8, 0))
    feed = Task(description="Feed", duration_minutes=15, priority=5, time=datetime(2026, 1, 1, 8, 0))

    scheduler = Scheduler()

    assert (walk, feed) in scheduler.find_time_conflicts([walk, feed])


def test_find_time_conflicts_detects_every_overlapping_pair_among_three_tasks():
    a = Task(description="A", duration_minutes=30, priority=5, time=datetime(2026, 1, 1, 8, 0))
    b = Task(description="B", duration_minutes=30, priority=5, time=datetime(2026, 1, 1, 8, 10))
    c = Task(description="C", duration_minutes=30, priority=5, time=datetime(2026, 1, 1, 8, 20))

    scheduler = Scheduler()
    conflicts = scheduler.find_time_conflicts([a, b, c])

    assert len(conflicts) == 3


# ---- Displaying conflict messages ----

def test_get_reasoning_includes_overlap_warning_and_task_descriptions():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    walk = Task(
        description="Walk", duration_minutes=30, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 0),
    )
    play = Task(
        description="Play", duration_minutes=30, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 15),
    )
    pet.add_task(walk)
    pet.add_task(play)

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    scheduler.build_plan(owner)
    reasoning = scheduler.get_reasoning()

    assert "Overlapping Tasks" in reasoning
    assert "Walk" in reasoning
    assert "Play" in reasoning


def test_format_schedule_includes_overlapping_tasks_section():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    walk = Task(
        description="Walk", duration_minutes=30, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 0),
    )
    play = Task(
        description="Play", duration_minutes=30, priority=5, required=True,
        time=datetime(2026, 1, 1, 8, 15),
    )
    pet.add_task(walk)
    pet.add_task(play)

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    scheduler.build_plan(owner)
    schedule_text = scheduler.format_schedule()

    assert "Overlapping tasks:" in schedule_text
    assert "Walk (08:00 AM) overlaps Play (08:15 AM)" in schedule_text


def test_get_reasoning_says_nothing_about_conflicts_when_there_are_none():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    pet.add_task(Task(description="Walk", duration_minutes=10, priority=5, required=True))

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    scheduler.build_plan(owner)

    assert "Overlapping Tasks" not in scheduler.get_reasoning()


def test_get_reasoning_warns_when_required_tasks_exceed_budget():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    pet.add_task(Task(description="Feed", duration_minutes=50, priority=5, required=True))

    scheduler = Scheduler()
    scheduler.set_available_minutes(10)
    scheduler.build_plan(owner)
    reasoning = scheduler.get_reasoning()

    assert "Not Enough Time for Required Tasks" in reasoning
    assert "40 more minute" in reasoning


def test_get_reasoning_suggests_time_needed_for_highest_priority_task():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    pet.add_task(Task(description="Walk", duration_minutes=20, priority=5))

    scheduler = Scheduler()
    scheduler.set_available_minutes(5)
    scheduler.build_plan(owner)
    reasoning = scheduler.get_reasoning()

    assert "Walk" in reasoning
    assert "15 minute" in reasoning


# ---- Adding and removing tasks (edge cases) ----

def test_add_task_preserves_insertion_order():
    pet = Pet(name="Mochi", species="dog")
    first = Task(description="First", duration_minutes=10, priority=5)
    second = Task(description="Second", duration_minutes=10, priority=5)

    pet.add_task(first)
    pet.add_task(second)

    assert pet.task_list == [first, second]


def test_add_task_allows_duplicate_descriptions():
    pet = Pet(name="Mochi", species="dog")

    pet.add_task(Task(description="Feed", duration_minutes=10, priority=5))
    pet.add_task(Task(description="Feed", duration_minutes=10, priority=5))

    assert len(pet.task_list) == 2


def test_remove_task_not_in_list_is_a_no_op():
    pet = Pet(name="Mochi", species="dog")
    kept = Task(description="Walk", duration_minutes=10, priority=5)
    never_added = Task(description="Bathe", duration_minutes=10, priority=5)
    pet.add_task(kept)

    pet.remove_task(never_added)

    assert pet.task_list == [kept]


# ---- Adding and removing pets (edge cases) ----

def test_add_pet_preserves_insertion_order():
    owner = Owner()
    dog = Pet(name="Mochi", species="dog")
    cat = Pet(name="Whiskers", species="cat")

    owner.add_pet(dog)
    owner.add_pet(cat)

    assert owner.pet_list == [dog, cat]


def test_remove_pet_not_in_list_is_a_no_op():
    owner = Owner()
    kept = Pet(name="Mochi", species="dog")
    never_added = Pet(name="Whiskers", species="cat")
    owner.add_pet(kept)

    owner.remove_pet(never_added)

    assert owner.pet_list == [kept]


# ---- Additional scheduling edge cases ----

def test_build_plan_marks_non_fitting_optional_task_as_unscheduled():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    too_long = Task(description="Long walk", duration_minutes=100, priority=5)
    pet.add_task(too_long)

    scheduler = Scheduler()
    scheduler.set_available_minutes(10)
    plan = scheduler.build_plan(owner)

    assert too_long not in plan
    assert too_long in scheduler.unscheduled


def test_build_plan_with_no_pets_produces_an_empty_plan():
    owner = Owner()

    scheduler = Scheduler()
    scheduler.set_available_minutes(60)
    plan = scheduler.build_plan(owner)

    assert plan == []
    assert scheduler.get_reasoning() == "No tasks were scheduled: there are no pending tasks to schedule."


def test_build_plan_includes_an_optional_task_that_exactly_uses_remaining_minutes():
    owner = Owner()
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    exact_fit = Task(description="Walk", duration_minutes=30, priority=5)
    pet.add_task(exact_fit)

    scheduler = Scheduler()
    scheduler.set_available_minutes(30)
    plan = scheduler.build_plan(owner)

    assert exact_fit in plan
    assert scheduler.remaining_minutes == 0


# ---- Boundary values (edge of the guardrail ranges) ----

@pytest.mark.parametrize("priority", [1, 10])
def test_task_construction_accepts_boundary_priority_values(priority):
    task = Task(description="Walk", duration_minutes=10, priority=priority)
    assert task.priority == priority


@pytest.mark.parametrize("duration_minutes", [1, 240])
def test_task_construction_accepts_boundary_duration_values(duration_minutes):
    task = Task(description="Walk", duration_minutes=duration_minutes, priority=5)
    assert task.duration_minutes == duration_minutes


# ---- Recurrence edge cases ----

def test_mark_complete_returns_none_for_an_unrecognized_frequency():
    task = Task(description="Walk", duration_minutes=10, priority=5, frequency="monthly")

    assert task.mark_complete() is None


# ---- Identity vs. value equality when removing tasks ----

def test_remove_task_removes_by_value_equality_not_by_object_identity():
    """Task is a plain dataclass, so list.remove() matches on field equality.

    Two field-identical tasks are indistinguishable to remove_task() — calling
    it with one instance can remove the *other* equal instance instead. This
    test locks in that documented behavior rather than assuming object identity.
    """
    pet = Pet(name="Mochi", species="dog")
    first = Task(description="Feed", duration_minutes=10, priority=5)
    second = Task(description="Feed", duration_minutes=10, priority=5)
    assert first == second and first is not second
    pet.add_task(first)
    pet.add_task(second)

    pet.remove_task(second)

    assert pet.task_list == [second]
    assert pet.task_list[0] is second


# ---- Empty-owner reads ----

def test_get_all_tasks_and_filter_tasks_on_an_owner_with_no_pets():
    owner = Owner()

    assert owner.get_all_tasks() == []
    assert owner.filter_tasks() == []
    assert owner.filter_tasks(completed=True, pet_name="Nobody") == []
