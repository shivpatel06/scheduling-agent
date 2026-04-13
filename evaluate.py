"""
evaluate.py
-----------
Evaluation framework for the AI Scheduling Agent.
 
Compares three schedulers:
  1. Earliest Deadline First (EDF)  — greedy baseline
  2. Shortest Processing Time (SPT) — greedy baseline
  3. CP-SAT solver                  — constraint-programming approach
 
Metrics computed for each scheduler on each scenario:
  - missed_deadlines     : number of tasks not fully scheduled before deadline
  - total_lateness       : sum of days each task is scheduled past its deadline
  - max_daily_workload   : heaviest single day (hours)
  - avg_daily_workload   : average hours per working day
  - utilisation          : fraction of available slots used
  - schedule_disruption  : (replanning only) fraction of slots changed vs original
 
Run this file directly to see a full comparison table:
  python evaluate.py
"""
 
from __future__ import annotations
 
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
 
from models import Schedule, Task, TimeSlot
from heuristics import earliest_deadline_first, shortest_processing_time
from cp_solver import cp_schedule, cp_replan
from simulator import generate_scenario
 
 
# Metric dataclass
 
@dataclass
class ScheduleMetrics:
    scheduler_name: str
    missed_deadlines: int = 0
    total_lateness_days: float = 0.0
    max_daily_workload_hours: float = 0.0
    avg_daily_workload_hours: float = 0.0
    utilisation: float = 0.0
    schedule_disruption: float = 0.0   # only meaningful for replanning
 
 
# Core metric computation
 
def compute_metrics(
    schedule: Schedule,
    tasks: List[Task],
    scheduler_name: str,
    original_schedule: Optional[Schedule] = None,
) -> ScheduleMetrics:
    """
    Compute evaluation metrics for a given schedule.
 
    Parameters
    ----------
    schedule          : the schedule to evaluate
    tasks             : all tasks that were to be scheduled
    scheduler_name    : label for display
    original_schedule : if provided, compute disruption vs this baseline
    """
    metrics = ScheduleMetrics(scheduler_name=scheduler_name)
 
    task_map = {task.id: task for task in tasks}
 
    # slots assigned per task
    task_slots: Dict[str, List[TimeSlot]] = {t.id: [] for t in tasks}
    for slot, task in schedule.assignments.items():
        if task is not None:
            task_slots[task.id].append(slot)
 
    # missed deadlines & lateness
    for task in tasks:
        assigned = task_slots[task.id]
        slots_needed = task.num_slots
 
        # A task is "missed" if it didn't get all its required slots
        if len(assigned) < slots_needed:
            metrics.missed_deadlines += 1
 
        # Lateness: if any assigned slot falls after the deadline
        for slot in assigned:
            if slot.date > task.deadline:
                late_days = (slot.date - task.deadline).days
                metrics.total_lateness_days += late_days
 
    # daily workload
    daily_slots: Dict[date, int] = {}
    for slot, task in schedule.assignments.items():
        if task is not None:
            daily_slots[slot.date] = daily_slots.get(slot.date, 0) + 1
 
    if daily_slots:
        daily_hours = {d: count * 0.5 for d, count in daily_slots.items()}
        metrics.max_daily_workload_hours = max(daily_hours.values())
        metrics.avg_daily_workload_hours = sum(daily_hours.values()) / len(daily_hours)
 
    # utilisation
    total_slots = len([s for s in schedule.assignments if s.is_available])
    used_slots  = sum(1 for t in schedule.assignments.values() if t is not None)
    metrics.utilisation = used_slots / total_slots if total_slots > 0 else 0.0
 
    # schedule disruption (replanning metric)
    if original_schedule is not None:
        changed = 0
        total   = 0
        orig_assignments = original_schedule.assignments
        for slot, new_task in schedule.assignments.items():
            orig_task = orig_assignments.get(slot)
            if orig_task != new_task:
                changed += 1
            total += 1
        metrics.schedule_disruption = changed / total if total > 0 else 0.0
 
    return metrics
 
 
# Scenario runner
 
def run_scenario(
    tasks: List[Task],
    slots: List[TimeSlot],
    scenario_label: str,
) -> List[ScheduleMetrics]:
    """Run all three schedulers on a scenario and return their metrics."""
    results = []
 
    # 1. EDF
    edf_schedule = earliest_deadline_first(tasks, slots)
    results.append(compute_metrics(edf_schedule, tasks, "EDF"))
 
    # 2. SPT
    spt_schedule = shortest_processing_time(tasks, slots)
    results.append(compute_metrics(spt_schedule, tasks, "SPT"))
 
    # 3. CP solver
    cp_sched = cp_schedule(tasks, slots)
    results.append(compute_metrics(cp_sched, tasks, "CP-SAT"))
 
    return results
 
 
def run_replanning_scenario(
    tasks: List[Task],
    slots: List[TimeSlot],
    disruption_day: int = 2,   # 0-indexed day of week where disruption occurs
) -> Tuple[ScheduleMetrics, ScheduleMetrics]:
    """
    Simulate a disruption: on disruption_day, one task takes longer than expected.
    Measure how much the CP solver's replan differs from its original plan.
 
    Returns
    -------
    (original_metrics, replan_metrics)
    """
    all_dates = sorted({s.date for s in slots if s.is_available})
 
    # Original plan
    original = cp_schedule(tasks, slots)
    original_metrics = compute_metrics(original, tasks, "CP-SAT (original)")
 
    if disruption_day >= len(all_dates):
        return original_metrics, original_metrics
 
    current_date = all_dates[disruption_day]
 
    # Simulate: mark tasks completed before disruption_day as done
    completed_ids = []
    for slot, task in original.assignments.items():
        if task is not None and slot.date < current_date:
            if task.id not in completed_ids:
                completed_ids.append(task.id)
 
    # Only evaluate replan against tasks that still need to be done
    remaining_tasks = [t for t in tasks if t.id not in completed_ids]
 
    # Replan from current_date with remaining tasks
    replan = cp_replan(tasks, slots, current_date, completed_ids)
    replan_metrics = compute_metrics(replan, remaining_tasks, "CP-SAT (replan)",
                                     original_schedule=original)
 
    return original_metrics, replan_metrics
 
 
# Pretty-print helpers
 
def print_metrics_table(results: List[ScheduleMetrics], title: str = "") -> None:
    """Print a formatted comparison table."""
    if title:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
 
    header = f"{'Scheduler':<18} {'Missed':>8} {'Lateness':>10} {'MaxDay(h)':>10} {'AvgDay(h)':>10} {'Util%':>7}"
    print(header)
    print("-" * 65)
    for m in results:
        print(
            f"{m.scheduler_name:<18} "
            f"{m.missed_deadlines:>8} "
            f"{m.total_lateness_days:>10.1f} "
            f"{m.max_daily_workload_hours:>10.1f} "
            f"{m.avg_daily_workload_hours:>10.1f} "
            f"{m.utilisation*100:>6.1f}%"
        )
 
    # Highlight winner per metric
    print()
    if results:
        best_missed  = min(results, key=lambda r: r.missed_deadlines)
        best_late    = min(results, key=lambda r: r.total_lateness_days)
        best_maxday  = min(results, key=lambda r: r.max_daily_workload_hours)
        print(f"  ✓ Fewest missed deadlines : {best_missed.scheduler_name}")
        print(f"  ✓ Least total lateness    : {best_late.scheduler_name}")
        print(f"  ✓ Most balanced days      : {best_maxday.scheduler_name}")
 
 
def print_disruption_table(orig: ScheduleMetrics, replan: ScheduleMetrics) -> None:
    print(f"\n{'='*60}")
    print("  Replanning Evaluation")
    print(f"{'='*60}")
    print(f"  Missed deadlines  — before: {orig.missed_deadlines}  after: {replan.missed_deadlines}")
    print(f"  Max daily load    — before: {orig.max_daily_workload_hours:.1f}h  after: {replan.max_daily_workload_hours:.1f}h")
    print(f"  Schedule disruption (% slots changed): {replan.schedule_disruption*100:.1f}%")
 
 
# Main
 
if __name__ == "__main__":
    print("\nAI Scheduling Agent — Evaluation")
    print("Comparing EDF, SPT, and CP-SAT across multiple scenarios\n")
 
    from datetime import date
    start = date.today()
 
    # Scenario 1: light load (seed 42)
    tasks1, slots1 = generate_scenario(num_tasks=8, seed=42, start_date=start)
    results1 = run_scenario(tasks1, slots1, "Scenario 1")
    print_metrics_table(results1, "Scenario 1: 8 tasks (seed=42)")
 
    # Scenario 2: moderate load (seed 99)
    tasks2, slots2 = generate_scenario(num_tasks=12, seed=99, start_date=start)
    results2 = run_scenario(tasks2, slots2, "Scenario 2")
    print_metrics_table(results2, "Scenario 2: 12 tasks (seed=99)")
 
    # Scenario 3: heavy / stressed load (seed 7)
    tasks3, slots3 = generate_scenario(num_tasks=18, seed=7, start_date=start)
    results3 = run_scenario(tasks3, slots3, "Scenario 3")
    print_metrics_table(results3, "Scenario 3: 18 tasks, high load (seed=7)")

    #scenario 4: over-constrained load
    tasks4, slots4 = generate_scenario(num_tasks=25, seed=13, start_date=start)
    results4 = run_scenario(tasks4, slots4, "Scenario 4")
    print_metrics_table(results4, "Scenario 4: 25 tasks, over-constrained (seed=13)")
 
    # Replanning evaluation: multiple seeds and disruption days
    replanning_seeds = [42, 99, 7, 21]
    disruption_days = [1, 2, 3]
    num_tasks = 12

    replan_results = []

    for seed in replanning_seeds:
        tasks, slots = generate_scenario(num_tasks=num_tasks, seed=seed, start_date=start)
        for day in disruption_days:
            orig_m, replan_m = run_replanning_scenario(tasks, slots, disruption_day=day)
            replan_results.append({
                'seed': seed,
                'disruption_day': day,
                'missed_before': orig_m.missed_deadlines,
                'missed_after': replan_m.missed_deadlines,
                'max_load_before': orig_m.max_daily_workload_hours,
                'max_load_after': replan_m.max_daily_workload_hours,
                'disruption_pct': replan_m.schedule_disruption * 100
            })

    # Print replanning summary table
    print(f"\n{'='*80}")
    print("  Replanning Evaluation Summary (12 tasks)")
    print(f"{'='*80}")
    header = f"{'Seed':>6} {'Day':>4} {'Missed':>8} {'Missed':>8} {'MaxLoad':>8} {'MaxLoad':>8} {'Disrupt':>8}"
    subheader = f"{'':6} {'':4} {'Before':>8} {'After':>8} {'Before(h)':>8} {'After(h)':>8} {'%':>8}"
    print(header)
    print(subheader)
    print("-" * 80)

    total_missed_before = 0
    total_missed_after = 0
    total_disruption = 0
    count = 0

    for r in replan_results:
        print(
            f"{r['seed']:>6} "
            f"{r['disruption_day']:>4} "
            f"{r['missed_before']:>8} "
            f"{r['missed_after']:>8} "
            f"{r['max_load_before']:>8.1f} "
            f"{r['max_load_after']:>8.1f} "
            f"{r['disruption_pct']:>7.1f}%"
        )
        total_missed_before += r['missed_before']
        total_missed_after += r['missed_after']
        total_disruption += r['disruption_pct']
        count += 1

    print("-" * 80)
    avg_missed_before = total_missed_before / count if count > 0 else 0
    avg_missed_after = total_missed_after / count if count > 0 else 0
    avg_disruption = total_disruption / count if count > 0 else 0
    print(
        f"{'AVERAGE':>11} "
        f"{avg_missed_before:>8.1f} "
        f"{avg_missed_after:>8.1f} "
        f"{'':8} "
        f"{'':8} "
        f"{avg_disruption:>7.1f}%"
    )

    print("\nDone.\n")