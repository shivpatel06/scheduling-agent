from datetime import date
from simulator import generate_scenario
from heuristics import earliest_deadline_first, shortest_processing_time


def run_comparison(num_tasks=10, seed=42):
    start = date(2025, 3, 10)
    tasks, slots = generate_scenario(start, num_tasks=num_tasks, seed=seed)

    print(f"Scenario: {num_tasks} tasks, seed={seed}")
    print(f"Tasks:")
    for t in sorted(tasks, key=lambda t: t.deadline):
        print(f"  {t.name}: {t.estimated_duration}h, due {t.deadline}, priority {t.priority}")

    total_hours = sum(t.estimated_duration for t in tasks)
    avail = sum(1 for s in slots if s.is_available)
    print(f"\nTotal task hours: {total_hours}h")
    print(f"Available hours: {avail * 0.5}h")

    # run both heuristics
    for name, scheduler in [
        ("Earliest Deadline First", earliest_deadline_first),
        ("Shortest Processing Time", shortest_processing_time),
    ]:
        schedule = scheduler(tasks, slots)
        missed = [t for t in tasks if not schedule.is_before_deadline(t)]
        unscheduled = schedule.unscheduled_tasks(tasks)

        print(f"\n{'=' * 40}")
        print(f"{name}")
        print(f"{'=' * 40}")
        print(schedule.summary())
        print(f"\nMissed deadlines: {len(missed)} — {[t.name for t in missed]}")
        print(f"Unscheduled tasks: {len(unscheduled)} — {[t.name for t in unscheduled]}")


if __name__ == "__main__":
    run_comparison(num_tasks=20, seed=42)