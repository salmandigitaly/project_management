# Time Tracking Module Documentation

Based on the `time_tracking.py` module, this document outlines the full workflow and API capabilities available for time tracking in the project management system.

## 1. Core Workflow

The system is designed to support both individual developer tracking and management oversight.

### A. Developer Workflow (Individual Contributor)

1. **Start Work (Clock In)**

   * **Action**: Developer starts working on a specific Issue.
   * **System Check**: Checks if there is already an active timer. If yes, it blocks the request (enforcing one task at a time).
   * **Result**: Timer starts ticking from `UTC Now`.
2. **Stop Work (Clock Out)**

   * **Action**: Developer finishes their session.
   * **Result**: System calculates the duration (`Clock Out - Clock In`) and saves the total seconds.
3. **Manual Entry (Correction)**

   * **Action**: If a developer forgot to use the timer, they can manually add an entry (e.g., "I worked 2 hours on Issue #123").
4. **Daily Review**

   * **Action**: Developer checks their daily summary.
   * **Result**: Sees total hours worked today, breakdown by issue, and an overtime indicator if > 8 hours.

### B. Manager Workflow (Oversight)

1. **Live Monitoring**

   * **Action**: Check who is working right now.
   * **Result**: Returns a list of all active timers (Who is doing What).
2. **Variance Analysis**

   * **Action**: Compare Estimates vs. Actuals.
   * **Result**: Reports showing which issues went over budget (Positive Variance) or were completed faster than expected (Negative Variance).
3. **Project Summary**

   * **Action**: High-level view of project health.
   * **Result**: Total hours burned vs. Total hours estimated for the entire project.

---

## 2. API Functionality Breakdown

### Base Route: `/time`

#### **A. Basic Tracking Operations**

1. **`/entries` (GET)**

   * **What it does**: Lists historical time logs based on filters.
   * **How it works**: Fetches records from the database where the `project_id`, `issue_id`, or `user_id` matches. It populates the User and Issue names for easy reading.
   * **Inputs**: `project_id` (required), optional `issue_id`, optional `user_id`.
2. **`/clock-in` (POST)**

   * **What it does**: Starts a timer for a specific task.
   * **How it works**:
     1. Checks if the user already has a `TimeEntry` where `clock_out` is missing (Active Session).
     2. If active, returns an error: "You already have an active session."
     3. If clear, creates a new entry with `clock_in = NOW`.
   * **Inputs**: `project_id`, `issue_id`.
3. **`/clock-out` (POST)**

   * **What it does**: Stops a currently running timer.
   * **How it works**:
     1. Finds the specific entry by ID.
     2. Sets `clock_out = NOW`.
     3. Calculates `seconds = clock_out - clock_in`.
   * **Inputs**: `time_entry_id`.
4. **`/add` (POST)**

   * **What it does**: Allows manually logging a completed block of time.
   * **How it works**: Creates an entry where `clock_in` and `clock_out` are essentially the same timestamp, but sets the `seconds` field directly to the user-provided value.
   * **Inputs**: `project_id`, `issue_id`, `seconds`.
5. **`/entries/{id}` (PUT)**

   * **What it does**: Updates an existing entry (e.g., to fix a mistake).
   * **How it works**: Allows changing start/end times or duration. Recalculates duration if times change. Restricted to the entry owner or Admin.
   * **Inputs**: `clock_in`, `clock_out`, `seconds`.
6. **`/entries/{id}` (DELETE)**

   * **What it does**: Deletes an entry.
   * **How it works**: Permanently removes the record. Restricted to the entry owner or Admin.

#### **B. Reports & Analytics (For Managers)**

1. **`/reports/employee` (GET)**

   * **What it does**: Shows how much time each employee has contributed.
   * **How it works**: Groups all time entries by User ID. Sums up `seconds`. Also provides a sub-list of which Issues they worked on.
   * **Key Data**: Total hours worked per person, Efficiency breakdown.
2. **`/reports/issue` (GET)**

   * **What it does**: Compare "Planned" vs "Actual" time for tasks.
   * **How it works**:
     1. Aggregates time entries by Issue ID.
     2. Compares total time spent vs `issue.estimated_hours`.
     3. Calculates **Variance**: `Actual - Estimated`.
   * **Key Data**: "Variance Hours" (Positive = Over budget, Negative = Under budget).
3. **`/reports/project` (GET)**

   * **What it does**: High-level project health check.
   * **How it works**: Sums up all estimates and all actuals for the entire project. Counts active sessions and unique employees.
   * **Key Data**: `total_estimated_hours`, `total_actual_hours`, `issues_count`.

#### **C. Real-time & Dashboard**

1. **`/active` (GET)**

   * **What it does**: Live view of who is working right now.
   * **How it works**: Queries for any `TimeEntry` where `clock_out` is `Null`. Calculates how long they have been working (`Now - clock_in`).
   * **Key Data**: List of users currently online and their task name.
2. **`/my-summary` (GET)**

   * **What it does**: Daily dashboard for the logged-in user.
   * **How it works**:
     1. Filters entries for "Today" (00:00 to 23:59).
     2. Sums total hours.
     3. Checks if an active session exists.
     4. Flags **Overtime** if total > 8 hours.
   * **Key Data**: `total_hours`, `overtime` (boolean), `active_session` details.

---

## 3. Key Technical Features

1. **Permission Gating**: Every request validates that the user actually has access to the requested `project_id` via `PermissionService`.
2. **Concurrency Control**: The system actively prevents a single user from having multiple "Clock In" sessions simultaneously.
3. **Automatic Calculation**: Users don't need to calculate duration; the system derives `seconds` from the timestamps automatically.
4. **Overtime Flagging**: The daily summary endpoint includes logic to flag days where work exceeded 8 hours.
