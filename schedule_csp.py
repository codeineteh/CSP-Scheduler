from ortools.sat.python import cp_model

def main():
    # Teams and division assignments
    teams = ["tej", "austin", "Brandon", "jared", "reed", 
             "Will", "Jackson", "Chase", "Aiden", "Connors"]
    num_teams = len(teams)
    num_weeks = 14

    # Divisions: west indices 0-4, east indices 5-9.
    west = [0, 1, 2, 3, 4]
    east = [5, 6, 7, 8, 9]

    model = cp_model.CpModel()

    # Create binary variables for each possible game in each week.
    # game[(w, i, j)] == 1 means in week w, team i plays as visitor and team j is home.
    game = {}
    for w in range(num_weeks):
        for i in range(num_teams):
            for j in range(num_teams):
                if i != j:
                    game[(w, i, j)] = model.NewBoolVar(f'game_w{w}_{teams[i]}_at_{teams[j]}')

    # (1) Each team plays exactly one game per week (either as visitor or home).
    for w in range(num_weeks):
        for t in range(num_teams):
            model.Add(
                sum(game[(w, t, j)] for j in range(num_teams) if j != t) +
                sum(game[(w, i, t)] for i in range(num_teams) if i != t)
                == 1
            )

    # (2) Divisional matchups: each pair in the same division must play twice –
    # one game with one team as visitor and one game with the roles reversed.
    # West division:
    for idx1 in range(len(west)):
        for idx2 in range(idx1 + 1, len(west)):
            i = west[idx1]
            j = west[idx2]
            model.Add(sum(game[(w, i, j)] for w in range(num_weeks)) == 1)
            model.Add(sum(game[(w, j, i)] for w in range(num_weeks)) == 1)
    # East division:
    for idx1 in range(len(east)):
        for idx2 in range(idx1 + 1, len(east)):
            i = east[idx1]
            j = east[idx2]
            model.Add(sum(game[(w, i, j)] for w in range(num_weeks)) == 1)
            model.Add(sum(game[(w, j, i)] for w in range(num_weeks)) == 1)

    # (3) Inter-divisional matchups:
    # Each pair (i in west, j in east) must play at least once and at most twice.
    for i in west:
        for j in east:
            inter_games = sum(game[(w, i, j)] + game[(w, j, i)] for w in range(num_weeks))
            model.Add(inter_games >= 1)
            model.Add(inter_games <= 2)

    # (4) Home/away balance: Each team must have exactly 7 home games and 7 away games.
    for t in range(num_teams):
        model.Add(sum(game[(w, i, t)] for w in range(num_weeks) for i in range(num_teams) if i != t) == 7)
        model.Add(sum(game[(w, t, j)] for w in range(num_weeks) for j in range(num_teams) if j != t) == 7)

    # (5) Total inter-divisional games per team: Each team must have 6 inter-division games.
    for t in west:
        model.Add(sum(game[(w, t, j)] + game[(w, j, t)]
                      for w in range(num_weeks) for j in east) == 6)
    for t in east:
        model.Add(sum(game[(w, t, j)] + game[(w, j, t)]
                      for w in range(num_weeks) for j in west) == 6)

    # (6) Week 7 forced matchups (note: week 7 is w = 6 in 0-indexed weeks).
    # Each forced pair appears (in one of the two possible home/away orders).
    # tej vs Will
    model.Add(game[(6, 0, 5)] + game[(6, 5, 0)] == 1)
    # Aiden vs Jared (Aiden is index 8, Jared is index 3)
    model.Add(game[(6, 8, 3)] + game[(6, 3, 8)] == 1)
    # Austin vs Brandon (indices 1 and 2)
    model.Add(game[(6, 1, 2)] + game[(6, 2, 1)] == 1)
    # Jackson vs Chase (indices 6 and 7)
    model.Add(game[(6, 6, 7)] + game[(6, 7, 6)] == 1)
    # Connors vs Reed (Connors is 9, Reed is 4)
    model.Add(game[(6, 9, 4)] + game[(6, 4, 9)] == 1)

    # (7) No team can have 3 or more consecutive home games or away games
    for t in range(num_teams):
        for w in range(num_weeks - 2):  # Check consecutive weeks (w, w+1, w+2)
            # No 3 consecutive home games
            model.Add(
                sum(game[(w+i, j, t)] for i in range(3) for j in range(num_teams) if j != t) <= 2
            )
            # No 3 consecutive away games
            model.Add(
                sum(game[(w+i, t, j)] for i in range(3) for j in range(num_teams) if j != t) <= 2
            )

    # (8) No team can play the same opponent within 4 weeks
    for i in range(num_teams):
        for j in range(num_teams):
            if i != j:
                for w in range(num_weeks - 4):
                    # If teams i and j play in week w (in either direction),
                    # they cannot play in weeks w+1, w+2, w+3, or w+4
                    for gap in range(1, 5):  # 1 to 4 weeks gap
                        if w + gap < num_weeks:
                            # If they play in week w
                            model.Add(
                                game[(w, i, j)] + game[(w, j, i)] +
                                game[(w + gap, i, j)] + game[(w + gap, j, i)] <= 1
                            )

    # Solve the model
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 120.0  # adjust if needed

    # To count solutions
    solution_limit = 100  # Set how many solutions you want to find before stopping
    solution_counter = SolutionCounter(solution_limit, game, teams, num_teams, num_weeks)
    status = solver.SearchForAllSolutions(model, solution_counter)

    print(f"\nNumber of valid solutions found: {solution_counter.solution_count()}")

    # To get and display one solution
    status = solver.Solve(model)

    if status == cp_model.FEASIBLE or status == cp_model.OPTIMAL:
        # Build schedule: for each week, list games as (visitor, home).
        schedule = {}
        for w in range(num_weeks):
            schedule[w + 1] = []
            for i in range(num_teams):
                for j in range(num_teams):
                    if i != j and solver.Value(game[(w, i, j)]) == 1:
                        schedule[w + 1].append((teams[i], teams[j]))
        # Print the schedule week-by-week.
        print("Schedule:")
        for w in range(1, num_weeks + 1):
            print(f"Week {w}:")
            for match in schedule[w]:
                print(f"  {match[0]} vs {match[1]}")
            print("")

        # Error checking: count home games, away games, and matchup frequencies.
        home_count = {team: 0 for team in teams}
        away_count = {team: 0 for team in teams}
        matchup_counts = {team: {opponent: 0 for opponent in teams if opponent != team} for team in teams}
        for w in range(1, num_weeks + 1):
            for match in schedule[w]:
                away_team, home_team = match
                away_count[away_team] += 1
                home_count[home_team] += 1
                matchup_counts[away_team][home_team] += 1
                matchup_counts[home_team][away_team] += 1

        print("Home games count:")
        for team in teams:
            print(f"  {team}: {home_count[team]}")
        print("\nAway games count:")
        for team in teams:
            print(f"  {team}: {away_count[team]}")
        print("\nMatchup counts:")
        for team in teams:
            print(f"  {team}: {matchup_counts[team]}")

        # Verify no 3+ consecutive home/away games
        print("\nChecking for consecutive home/away games:")
        for team in teams:
            team_idx = teams.index(team)
            consecutive_home = 0
            consecutive_away = 0
            max_consecutive_home = 0
            max_consecutive_away = 0
            
            for w in range(1, num_weeks + 1):
                # Check if team is home this week
                is_home = any(match[1] == team for match in schedule[w])
                # Check if team is away this week
                is_away = any(match[0] == team for match in schedule[w])
                
                if is_home:
                    consecutive_home += 1
                    consecutive_away = 0
                elif is_away:
                    consecutive_away += 1
                    consecutive_home = 0
                
                max_consecutive_home = max(max_consecutive_home, consecutive_home)
                max_consecutive_away = max(max_consecutive_away, consecutive_away)
            
            print(f"  {team}: Max consecutive home games: {max_consecutive_home}, Max consecutive away games: {max_consecutive_away}")

        # Verify minimum gap between rematches
        print("\nChecking for minimum gap between rematches:")
        for team in teams:
            for opponent in teams:
                if team != opponent:
                    # Find all weeks where these teams play
                    matchup_weeks = []
                    for w in range(1, num_weeks + 1):
                        if any((match[0] == team and match[1] == opponent) or 
                               (match[0] == opponent and match[1] == team) 
                               for match in schedule[w]):
                            matchup_weeks.append(w)
                    
                    # Check gaps between matchups
                    if len(matchup_weeks) > 1:
                        min_gap = min(matchup_weeks[i] - matchup_weeks[i-1] for i in range(1, len(matchup_weeks)))
                        if min_gap < 5:
                            print(f"  Warning: {team} vs {opponent} play with only {min_gap} weeks gap (weeks {matchup_weeks})")
                        else:
                            print(f"  {team} vs {opponent} play with minimum gap of {min_gap} weeks (weeks {matchup_weeks})")
    else:
        print("No solution found.")

# Modify the SolutionCounter class to validate the 4-week gap constraint
class SolutionCounter(cp_model.CpSolverSolutionCallback):
    def __init__(self, limit, game, teams, num_teams, num_weeks):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.__solution_count = 0
        self.__solution_limit = limit
        self.__game = game
        self.__teams = teams
        self.__num_teams = num_teams
        self.__num_weeks = num_weeks

    def on_solution_callback(self):
        # Build the schedule from the solution
        schedule = {}
        for w in range(self.__num_weeks):
            schedule[w + 1] = []
            for i in range(self.__num_teams):
                for j in range(self.__num_teams):
                    if i != j and self.Value(self.__game[(w, i, j)]) == 1:
                        schedule[w + 1].append((self.__teams[i], self.__teams[j]))
        
        # Check for rematches within 4 weeks
        valid_solution = True
        for team in self.__teams:
            for opponent in self.__teams:
                if team != opponent:
                    # Find all weeks where these teams play
                    matchup_weeks = []
                    for w in range(1, self.__num_weeks + 1):
                        if any((match[0] == team and match[1] == opponent) or 
                               (match[0] == opponent and match[1] == team) 
                               for match in schedule[w]):
                            matchup_weeks.append(w)
                    
                    # Check gaps between matchups
                    if len(matchup_weeks) > 1:
                        min_gap = min(matchup_weeks[i] - matchup_weeks[i-1] for i in range(1, len(matchup_weeks)))
                        if min_gap < 5:
                            valid_solution = False
                            break
            if not valid_solution:
                break
        
        if valid_solution:
            self.__solution_count += 1
            print(f'Valid solution {self.__solution_count} found.')
            if self.__solution_count >= self.__solution_limit:
                self.StopSearch()

    def solution_count(self):
        return self.__solution_count

if __name__ == '__main__':
    main()
