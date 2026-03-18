# Implementation Plan: Rollover Feature

## Overview
A "Rollover" occurs when all remaining active players are eliminated in the same gameweek. Instead of the game ending, a rollover allows players to buy back in for £5 and restart the game. The key requirement is that while history is preserved, players can reuse teams they previously selected before the rollover occurred.

## Proposed Changes

### 1. Database Schema (`models.py`)
- Add a `is_rollover` boolean field to the `Gameweek` model.
- Alternatively, we could add a `rollover_count` to a global settings table, but adding it to `Gameweek` allows us to precisely identify which week the reset happened.

### 2. Logic Updates (`services.py` / `main.py`)

#### Detect Rollover Condition
- In the results processing logic, after updating all players' `is_active` status, check if `count(User.is_active == True)` is 0.
- If 0, flag the current (or next) gameweek as a `is_rollover = True` (pending admin confirmation/trigger).

#### Team Selection Logic (`check_pick_allowed` / API)
- Modify the logic that filters available teams for a user.
- Find the most recent `Gameweek` where `is_rollover == True`.
- If a rollover has occurred, the user can pick any team, provided they haven't picked it **since** the most recent rollover gameweek.
- If no rollover has occurred, the existing "one pick per team" rule applies across all history.

#### Re-entry / Reset
- Provide an admin endpoint/UI button to "Trigger Rollover".
- This action should:
    1. Mark a specific `Gameweek` as the rollover point.
    2. Set `is_active = True` for all players who have "bought back in" (this might require a new `has_paid_rollover` field on `User` or a manual admin toggle).

### 3. Frontend Updates
- **Admin Dashboard**: Add a "Trigger Rollover" section that appears when everyone is out.
- **Player Dashboard**: 
    - Display a "Rollover in progress" message if applicable.
    - Update the team selection dropdown to reflect the reset team availability.

## Tasks for Implementation

- [ ] Add `is_rollover` field to `Gameweek` model in `models.py`.
- [ ] Implement `get_latest_rollover_gw_id()` helper function.
- [ ] Update team selection validation logic to only check picks after the latest rollover.
- [ ] Add Admin API endpoint to trigger a rollover for a specific gameweek.
- [ ] Update Admin UI to show rollover trigger.
- [ ] Add "Re-activate all players" utility for rollover buy-ins.
- [ ] Add unit tests for rollover team selection logic (e.g., picking Arsenal in GW1, rollover in GW5, picking Arsenal again in GW6 should be allowed).
