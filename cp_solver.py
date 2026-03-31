"""
cp_solver.py
------------
Constraint-programming scheduler using Google OR-Tools CP-SAT solver.

The model assigns tasks to 30-minute time slots while:
  - Respecting fixed commitments (blocked slots)
  - Respecting deadlines (all slots for a task must fall before its deadline)
  - Respecting a daily workload cap (default 8 hours = 16 slots)
  - Minimising a weighted objective:
        w1 * missed_deadlines  +  w2 * daily_overload  +  w3 * total_lateness
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from models import Schedule, Task, TimeSlot

# ── Objective weights (tune as needed) ────────────────────────────────────────
W_MISSED   = 100   # heavy penalty for each unscheduled task
W_OVERLOAD = 10    # penalty per slot above the daily cap
W_LATENESS = 1     # penalty per slot of lateness past deadline

DAILY_CAP_HOURS = 8          # soft cap on daily study hours
DAILY_CAP_SLOTS = int(DAILY_CAP_HOURS / 0.5)   # → 16 slots


def cp_schedule(tasks: List[Task], slots: List[TimeSlot]) -> Schedule:
    """
    Build and solve a CP-SAT model.

    Parameters
    ----------
    tasks : list of Task objects to be scheduled
    slots : list of TimeSlot objects for the week (available + blocked)

    Returns
    -------
    A Schedule object with the best assignment found within the time limit.
    """
    model = cp_model.CpModel()

    # Only consider slots that are actually available for work
    available_slots = [s for s in slots if s.is_available]

    # Collect the unique dates present in the slot list
    all_dates = sorted({s.date for s in available_slots})

    # Decision variables 
    # x[task_id][slot_index] = 1  iff  task is assigned to that slot
    x: Dict[str, Dict[int, cp_model.IntVar]] = {}
    for task in tasks:
        x[task.id] = {}
        for i, slot in enumerate(available_slots):
            x[task.id][i] = model.NewBoolVar(f"x_{task.id}_{i}")

    # Constraint 1: each task must fill exactly num_slots slots 
    # (or fewer if we allow partial scheduling — we track the shortfall instead)
    # We introduce a "scheduled_slots" variable and penalise unmet demand.
    scheduled: Dict[str, cp_model.IntVar] = {}
    for task in tasks:
        scheduled[task.id] = model.NewIntVar(0, task.num_slots, f"sched_{task.id}")
        model.Add(
            scheduled[task.id] == sum(x[task.id][i] for i in range(len(available_slots)))
        )

    # Constraint 2: each slot can be assigned to at most one task
    for i in range(len(available_slots)):
        model.Add(sum(x[task.id][i] for task in tasks) <= 1)

    #  Constraint 3: deadline enforcement
    # A slot used for a task must fall strictly before (or on) the deadline date.
    for task in tasks:
        for i, slot in enumerate(available_slots):
            # If the slot date is after the deadline, forbid assignment
            if slot.date > task.deadline:
                model.Add(x[task.id][i] == 0)

    #  Soft constraint: daily workload overload
    # For each day, count assigned slots and measure excess above the cap.
    overload_vars: List[cp_model.IntVar] = []
    for d in all_dates:
        day_indices = [i for i, s in enumerate(available_slots) if s.date == d]
        if not day_indices:
            continue
        day_slots_used = model.NewIntVar(0, len(day_indices), f"day_used_{d}")
        model.Add(
            day_slots_used == sum(
                x[task.id][i]
                for task in tasks
                for i in day_indices
            )
        )
        overload = model.NewIntVar(0, len(day_indices), f"overload_{d}")
        # overload = max(0, day_slots_used - DAILY_CAP_SLOTS)
        model.AddMaxEquality(overload, [
            day_slots_used - DAILY_CAP_SLOTS,
            model.NewConstant(0)
        ])
        overload_vars.append(overload)

    #  Objective 
    # 1. Penalty for missed slots (tasks not fully scheduled)
    missed_penalties = []
    for task in tasks:
        shortfall = model.NewIntVar(0, task.num_slots, f"shortfall_{task.id}")
        model.Add(shortfall == task.num_slots - scheduled[task.id])
        # Weight by task priority so high-priority tasks are protected
        weighted = model.NewIntVar(0, task.num_slots * task.priority * W_MISSED,
                                   f"miss_pen_{task.id}")
        model.Add(weighted == shortfall * task.priority * W_MISSED)
        missed_penalties.append(weighted)

    # 2. Overload penalty
    overload_penalty = sum(overload_vars) * W_OVERLOAD if overload_vars else 0

    # 3. Lateness penalty : penalise assigning slots to days far from the deadline
    #    (encourages front-loading urgent tasks)
    lateness_terms = []
    for task in tasks:
        for i, slot in enumerate(available_slots):
            # days remaining until deadline when this slot occurs
            days_until = (task.deadline - slot.date).days
            # lateness = negative slack → how late the slot is (0 if before deadline)
            # We use "days_until" inverted: earlier slots cost less
            # penalty = max(0, -days_until) = 0 always (deadline already enforced above)
            # Instead penalise slots that are very close to the deadline:
            # closer to deadline → higher urgency cost if not scheduled early
            slot_lateness = max(0, -days_until)  # always 0 here; kept for extension
            if slot_lateness > 0:
                lateness_terms.append(x[task.id][i] * slot_lateness * W_LATENESS)

    total_lateness = sum(lateness_terms) if lateness_terms else 0

    # Combine into single minimisation objective
    model.Minimize(sum(missed_penalties) + overload_penalty + total_lateness)

    #  Solve 
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0   # time limit for replanning use
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)

    # ── Extract solution ───────────────────────────────────────────────────────
    assignments: Dict[TimeSlot, Optional[Task]] = {}

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Build a lookup: slot → task (or None)
        task_map = {task.id: task for task in tasks}
        for i, slot in enumerate(available_slots):
            assigned_task = None
            for task in tasks:
                if solver.Value(x[task.id][i]) == 1:
                    assigned_task = task
                    break
            assignments[slot] = assigned_task
    else:
        # No feasible solution found — return an empty schedule
        for slot in available_slots:
            assignments[slot] = None

    return Schedule(assignments=assignments)


def cp_replan(
    tasks: List[Task],
    slots: List[TimeSlot],
    current_date: date,
    completed_task_ids: List[str],
) -> Schedule:
    """
    Replan from current_date onwards after some tasks completed late or early.

    Parameters
    ----------
    tasks              : ALL original tasks (completed ones will be filtered out)
    slots              : ALL original slots for the week
    current_date       : today; slots before this date are ignored
    completed_task_ids : IDs of tasks already finished (exclude from replanning)

    Returns
    -------
    A new Schedule covering only the remaining slots and tasks.
    """
    # Filter out past slots and completed tasks
    remaining_slots = [s for s in slots if s.date >= current_date]
    remaining_tasks = [t for t in tasks if t.id not in completed_task_ids]

    if not remaining_tasks or not remaining_slots:
        return Schedule(assignments={})

    return cp_schedule(remaining_tasks, remaining_slots)