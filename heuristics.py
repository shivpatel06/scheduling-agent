from typing import List

from models import Task, TimeSlot, Schedule, SLOT_DURATION
from simulator import available_slots


# ── Core Greedy Assignment ─────────────────────────────────
def _greedy_schedule(sorted_tasks: List[Task], slots: List[TimeSlot]) -> Schedule:
    """Assign tasks to time slots in the order given.
    
    For each task, fill the earliest available slots until the task's
    required number of slots is met. Tasks can be split across days.
    If there aren't enough slots left, the task is partially scheduled
    or skipped entirely.
    """
    open_slots = available_slots(slots)  # sorted chronologically
    schedule = Schedule()

    # initialize all available slots as unassigned
    for slot in open_slots:
        schedule.assignments[slot] = None

    for task in sorted_tasks:
        slots_needed = task.num_slots
        slots_assigned = 0

        for slot in open_slots:
            if slots_assigned >= slots_needed:
                break
            # only use slots that haven't been claimed by a previous task
            if schedule.assignments[slot] is None:
                schedule.assignments[slot] = task
                slots_assigned += 1

    return schedule


# ── Earliest Deadline First ────────────────────────────────
def earliest_deadline_first(tasks: List[Task], slots: List[TimeSlot]) -> Schedule:
    """Schedule tasks by earliest deadline first.
    
    Prioritizes tasks that are due soonest. Among tasks with the same
    deadline, higher priority tasks go first.
    """
    sorted_tasks = sorted(tasks, key=lambda t: (t.deadline, -t.priority))
    return _greedy_schedule(sorted_tasks, slots)


# ── Shortest Processing Time ──────────────────────────────
def shortest_processing_time(tasks: List[Task], slots: List[TimeSlot]) -> Schedule:
    """Schedule tasks by shortest duration first.
    
    Prioritizes quick tasks to maximize the number of completed tasks.
    Among tasks with the same duration, earlier deadlines go first.
    """
    sorted_tasks = sorted(tasks, key=lambda t: (t.estimated_duration, t.deadline))
    return _greedy_schedule(sorted_tasks, slots)


# ── Quick Test ─────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import date
    from simulator import generate_scenario

    start = date(2025, 3, 10)
    tasks, slots = generate_scenario(start, num_tasks=8, seed=42)

    print("=" * 50)
    print("EARLIEST DEADLINE FIRST")
    print("=" * 50)
    edf_schedule = earliest_deadline_first(tasks, slots)
    print(edf_schedule.summary())

    unscheduled = edf_schedule.unscheduled_tasks(tasks)
    if unscheduled:
        print(f"\nUnscheduled: {[t.name for t in unscheduled]}")

    missed = [t for t in tasks if not edf_schedule.is_before_deadline(t)]
    print(f"Missed deadlines: {[t.name for t in missed]}")

    print("\n" + "=" * 50)
    print("SHORTEST PROCESSING TIME")
    print("=" * 50)
    spt_schedule = shortest_processing_time(tasks, slots)
    print(spt_schedule.summary())

    unscheduled = spt_schedule.unscheduled_tasks(tasks)
    if unscheduled:
        print(f"\nUnscheduled: {[t.name for t in unscheduled]}")

    missed = [t for t in tasks if not spt_schedule.is_before_deadline(t)]
    print(f"Missed deadlines: {[t.name for t in missed]}")



