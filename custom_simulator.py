import random
from datetime import date, timedelta
from typing import List, Tuple

from models import Task, TimeSlot, SLOT_DURATION


#  Configuration
DAY_START = 8.0   # 8:00 AM
DAY_END = 22.0    # 10:00 PM

# Task duration range (in hours)
MIN_TASK_DURATION = 0.5
MAX_TASK_DURATION = 4.0
DURATION_STEP = 0.5  # tasks come in 30-min increments

# Priority range
MIN_PRIORITY = 1
MAX_PRIORITY = 3

# Fixed commitment settings
WEEKDAY_CLASSES = (2, 4)       # range of class blocks per weekday
CLASS_DURATION_SLOTS = (2, 3)  # each class is 1-1.5 hours (2-3 slots)
LUNCH_START = 12.0             # lunch block at noon
LUNCH_SLOTS = 2                # 1 hour for lunch

WEEKEND_BLOCKS = (1, 2)        # fewer fixed blocks on weekends
WEEKEND_BLOCK_SLOTS = (2, 3)   # 1-1.5 hours each


# ── Time Slot Generation ──────────────────────────────────
def generate_time_slots(
    start_date: date,
    num_days: int = 7,
    seed: int = None
) -> List[TimeSlot]:
    """Generate all 30-min time slots for a week, with random fixed commitments.
    
    Creates slots from DAY_START to DAY_END each day. On weekdays, blocks out
    random class times and a lunch period. On weekends, blocks fewer slots.
    """
    if seed is not None:
        random.seed(seed)

    slots = []

    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        is_weekday = current_date.weekday() < 5  # Mon-Fri = 0-4

        # generate all slot start times for this day
        slot_starts = []
        t = DAY_START
        while t < DAY_END:
            slot_starts.append(t)
            t += SLOT_DURATION

        # decide which slots are blocked by fixed commitments
        blocked_starts = set()

        if is_weekday:
            # block lunch
            for i in range(LUNCH_SLOTS):
                blocked_starts.add(LUNCH_START + i * SLOT_DURATION)

            # block random class periods
            num_classes = random.randint(*WEEKDAY_CLASSES)
            for _ in range(num_classes):
                duration_slots = random.randint(*CLASS_DURATION_SLOTS)
                # pick a random start that doesn't overlap lunch
                available_starts = [
                    s for s in slot_starts
                    if s not in blocked_starts
                    and s + duration_slots * SLOT_DURATION <= DAY_END
                    # make sure the full class block doesn't overlap blocked slots
                    and all(
                        s + i * SLOT_DURATION not in blocked_starts
                        for i in range(duration_slots)
                    )
                ]
                if available_starts:
                    class_start = random.choice(available_starts)
                    for i in range(duration_slots):
                        blocked_starts.add(class_start + i * SLOT_DURATION)
        else:
            # weekends: fewer fixed blocks (errands, meals, etc.)
            num_blocks = random.randint(*WEEKEND_BLOCKS)
            for _ in range(num_blocks):
                duration_slots = random.randint(*WEEKEND_BLOCK_SLOTS)
                available_starts = [
                    s for s in slot_starts
                    if s + duration_slots * SLOT_DURATION <= DAY_END
                    and all(
                        s + i * SLOT_DURATION not in blocked_starts
                        for i in range(duration_slots)
                    )
                ]
                if available_starts:
                    block_start = random.choice(available_starts)
                    for i in range(duration_slots):
                        blocked_starts.add(block_start + i * SLOT_DURATION)

        # create TimeSlot objects
        for start in slot_starts:
            slots.append(TimeSlot(
                date=current_date,
                start_hour=start,
                is_available=(start not in blocked_starts)
            ))

    return slots


# ── Task Generation ────────────────────────────────────────
def generate_tasks(
    num_tasks: int,
    start_date: date,
    num_days: int = 7,
    seed: int = None
) -> List[Task]:
    """Generate random tasks with durations, deadlines, and priorities.
    
    Deadlines are spread across the week, weighted toward later days
    to mimic real student workloads (more things due end of week).
    """
    if seed is not None:
        random.seed(seed)

    task_names = [
        "Math Homework", "Reading Response", "Lab Report", "Essay Draft",
        "Problem Set", "Quiz Study", "Research Notes", "Code Assignment",
        "Discussion Post", "Presentation Prep", "Group Project Work",
        "Exam Review", "Paper Outline", "Data Analysis", "Literature Review",
        "Bug Fixes", "Peer Review", "Journal Entry", "Practice Problems",
        "Final Project Work"
    ]

    tasks = []
    used_names = set()

    for i in range(num_tasks):
        # pick a unique name, or append a number if we run out
        available_names = [n for n in task_names if n not in used_names]
        if available_names:
            name = random.choice(available_names)
        else:
            name = f"Task {i + 1}"
        used_names.add(name)

        # random duration in 0.5-hour steps
        duration = random.choice([
            d for d in _frange(MIN_TASK_DURATION, MAX_TASK_DURATION + DURATION_STEP, DURATION_STEP)
        ])

        # deadline: weighted toward later in the week
        # use triangular distribution — mode at ~70% through the week
        deadline_offset = int(random.triangular(0, num_days - 1, num_days * 0.7))
        deadline = start_date + timedelta(days=deadline_offset)

        # random priority
        priority = random.randint(MIN_PRIORITY, MAX_PRIORITY)

        tasks.append(Task(
            id=f"task_{i + 1}",
            name=name,
            estimated_duration=duration,
            deadline=deadline,
            priority=priority
        ))

    return tasks


# Scenario Generation
def generate_scenario(
    start_date: date,
    num_days: int = 7,
    num_tasks: int = 10,
    seed: int = 42
) -> Tuple[List[Task], List[TimeSlot]]:
    """Generate a complete scenario: tasks + time slots for a week.
    
    Uses the same seed for reproducibility — both schedulers will
    see the exact same problem.
    """
    slots = generate_time_slots(start_date, num_days, seed=seed)
    tasks = generate_tasks(num_tasks, start_date, num_days, seed=seed + 1)
    return tasks, slots


# ── Custom Fixed Commitments ──────────────────────────────
def generate_custom_slots(
    start_date: date,
    num_days: int = 7,
    fixed_commitments: List[dict] = None
) -> List[TimeSlot]:
    """Generate time slots with specific fixed commitments.
    
    fixed_commitments is a list of dicts like:
        {
            "day": 0,          # 0=Monday, 1=Tuesday, ... 6=Sunday (offset from start_date)
            "start": 9.0,      # 9:00 AM
            "end": 10.5,       # 10:30 AM
            "name": "CS5100"   # optional, for your reference
        }
    
    Any slot that overlaps a commitment is marked unavailable.
    Supports recurring commitments by passing multiple entries for
    different days with the same name.
    """
    if fixed_commitments is None:
        fixed_commitments = []

    # build a set of (day_offset, start_hour) pairs that are blocked
    blocked = set()
    for commitment in fixed_commitments:
        day_offset = commitment["day"]
        start = commitment["start"]
        end = commitment["end"]
        
        t = start
        while t < end:
            blocked.add((day_offset, round(t, 2)))
            t += SLOT_DURATION

    # generate all slots
    slots = []
    for day_offset in range(num_days):
        current_date = start_date + timedelta(days=day_offset)
        t = DAY_START
        while t < DAY_END:
            is_avail = (day_offset, round(t, 2)) not in blocked
            slots.append(TimeSlot(
                date=current_date,
                start_hour=round(t, 2),
                is_available=is_avail
            ))
            t += SLOT_DURATION

    return slots


def generate_custom_scenario(
    start_date: date,
    tasks: List[Task],
    fixed_commitments: List[dict],
    num_days: int = 7
) -> Tuple[List[Task], List[TimeSlot]]:
    """Create a scenario with manually defined tasks and fixed commitments.
    
    Example usage:
        from datetime import date
        from models import Task
        
        start = date(2025, 3, 10)  # Monday
        
        my_tasks = [
            Task("hw1", "Math Homework", 3.0, date(2025, 3, 14), priority=2),
            Task("hw2", "Essay Draft", 4.0, date(2025, 3, 12), priority=3),
        ]
        
        my_commitments = [
            {"day": 0, "start": 9.5, "end": 10.75, "name": "CS5100"},  # Mon 9:30-10:45
            {"day": 0, "start": 12.0, "end": 13.0, "name": "Lunch"},   # Mon 12:00-1:00
            {"day": 2, "start": 9.5, "end": 10.75, "name": "CS5100"},  # Wed 9:30-10:45
            # ... etc
        ]
        
        tasks, slots = generate_custom_scenario(start, my_tasks, my_commitments)
    """
    slots = generate_custom_slots(start_date, num_days, fixed_commitments)
    return tasks, slots


#  Helpers
def _frange(start: float, stop: float, step: float) -> List[float]:
    """Generate a list of floats from start to stop (exclusive) by step."""
    result = []
    current = start
    while current < stop:
        result.append(round(current, 2))
        current += step
    return result


def available_slots(slots: List[TimeSlot]) -> List[TimeSlot]:
    """Filter to only available (unblocked) time slots, sorted chronologically."""
    return sorted(
        [s for s in slots if s.is_available],
        key=lambda s: (s.date, s.start_hour)
    )


# ── Quick Test ─────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import date

    start = date(2025, 3, 10)  # a Monday
    tasks, slots = generate_scenario(start, num_tasks=8, seed=42)

    total_slots = len(slots)
    blocked = sum(1 for s in slots if not s.is_available)
    avail = total_slots - blocked

    print(f"Generated {total_slots} total slots ({avail} available, {blocked} blocked)")
    print(f"Available hours: {avail * SLOT_DURATION}h\n")

    print("Tasks:")
    for t in tasks:
        print(f"  {t.name}: {t.estimated_duration}h, due {t.deadline}, priority {t.priority}")

    total_task_hours = sum(t.estimated_duration for t in tasks)
    print(f"\nTotal task hours: {total_task_hours}h")
    print(f"Utilization: {total_task_hours / (avail * SLOT_DURATION) * 100:.1f}%")



