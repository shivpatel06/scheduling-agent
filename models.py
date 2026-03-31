from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


# Constants 
SLOT_DURATION = 0.5  # each time slot is 30 minutes


#  Task
@dataclass
class Task:
    """A single task (assignment, project, reading, etc.) that needs scheduling."""
    id: str
    name: str
    estimated_duration: float  # total hours needed (e.g. 1.5 = three 30-min blocks)
    deadline: date
    priority: int = 1  # higher = more important, default is 1

    @property
    def num_slots(self) -> int:
        """How many 30-min slots this particular task requires."""
        import math
        return math.ceil(self.estimated_duration / SLOT_DURATION)

    def __repr__(self) -> str:
        return f"Task({self.id}, '{self.name}', {self.estimated_duration}h, due={self.deadline})"


# TimeSlot 
@dataclass(frozen=True)
class TimeSlot:
    """A single 30-minute block of time on a specific day.
    
    frozen=True makes this immutable and hashable, so it can be
    used as a dictionary key in Schedule.assignments.
    """
    date: date
    start_hour: float  # 14.5 = 2:30 PM, 9.0 = 9:00 AM
    is_available: bool = True  # False = blocked by class, meal, etc.

    @property
    def end_hour(self) -> float:
        return self.start_hour + SLOT_DURATION

    @property
    def time_label(self) -> str:
        """Human-readable time like '2:30 PM'."""
        hour = int(self.start_hour)
        minute = int((self.start_hour % 1) * 60)
        period = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        return f"{display_hour}:{minute:02d} {period}"

    def __repr__(self) -> str:
        status = "open" if self.is_available else "blocked"
        return f"TimeSlot({self.date}, {self.time_label}, {status})"


# Schedule
@dataclass
class Schedule:
    """A mapping of time slots to tasks, representing a complete schedule.
    
    The assignments dict maps each available TimeSlot to either a Task
    (meaning that task is scheduled in that slot) or None (slot is free).
    """
    assignments: Dict[TimeSlot, Optional[Task]] = field(default_factory=dict)

    def get_task_slots(self, task: Task) -> List[TimeSlot]:
        """Return all time slots assigned to a given task, sorted chronologically."""
        slots = [
            slot for slot, assigned_task in self.assignments.items()
            if assigned_task is not None and assigned_task.id == task.id
        ]
        return sorted(slots, key=lambda s: (s.date, s.start_hour))

    def daily_workload(self, target_date: date) -> float:
        """Total hours of work scheduled on a given date."""
        count = sum(
            1 for slot, task in self.assignments.items()
            if slot.date == target_date and task is not None
        )
        return count * SLOT_DURATION

    def is_before_deadline(self, task: Task) -> bool:
        """Check whether all slots for a task fall on or before its deadline."""
        slots = self.get_task_slots(task)
        if not slots:
            return False  # task not scheduled at all
        last_slot = slots[-1]
        return last_slot.date <= task.deadline

    def unscheduled_tasks(self, all_tasks: List[Task]) -> List[Task]:
        """Return tasks that have no slots assigned at all."""
        scheduled_ids = {
            task.id for task in self.assignments.values()
            if task is not None
        }
        return [t for t in all_tasks if t.id not in scheduled_ids]

    def summary(self) -> str:
        """Print a readable summary of the schedule by day."""
        from collections import defaultdict

        by_date = defaultdict(list)
        for slot, task in sorted(
            self.assignments.items(), key=lambda x: (x[0].date, x[0].start_hour)
        ):
            if task is not None:
                by_date[slot.date].append((slot, task))

        lines = []
        for d in sorted(by_date.keys()):
            lines.append(f"\n{d.strftime('%A %m/%d')}:")
            for slot, task in by_date[d]:
                lines.append(f"  {slot.time_label} - {task.name}")
            lines.append(f"  Total: {self.daily_workload(d)}h")

        return "\n".join(lines)



