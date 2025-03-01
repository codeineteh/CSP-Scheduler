# CSP-Scheduler
Fantasy Sports Customise Schedule Maker
A constraint satisfaction problem (CSP) solver for creating optimal sports league schedules.
Big hosts for leagues do not allow customization in schedules and we want to change that.


## Problem Description
This scheduler creates a 14-week schedule for 10 teams split into 2 divisions (East and West) with the following constraints:
- Each team plays exactly 7 home games and 7 away games
- Each team plays exactly 1 home game and 1 away game vs each divisional opponent
- Each team plays all teams in the other division at least once and at most twice
- No team can have 3 or more consecutive home or away games
- No team can play the same opponent within 4 weeks
- User can input their own matchups

## Usage

1. Install the requirements:
   ```
   pip install -r requirements.txt
   ```

2. Run the scheduler:
   ```
   python app.py
   ```

## Output

The program will:
1. Count the number of valid solutions
2. Display all valid schedules
3. Verify all constraints are met

