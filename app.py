from flask import Flask, render_template, request, jsonify
from ortools.sat.python import cp_model
import json
import subprocess
import io
import sys
import math

app = Flask(__name__)

class SolutionCounter(cp_model.CpSolverSolutionCallback):
    def __init__(self, limit, game, teams, num_teams, num_weeks):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.__solution_count = 0
        self.__solution_limit = limit
        self.__game = game
        self.__teams = teams
        self.__num_teams = num_teams
        self.__num_weeks = num_weeks
        self.__solutions = []

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
            # Store the solution
            self.__solutions.append(schedule)
            if self.__solution_count >= self.__solution_limit:
                self.StopSearch()

    def solution_count(self):
        return self.__solution_count
    
    def solutions(self):
        return self.__solutions

def generate_schedule(teams, num_weeks, use_divisions, division_teams=None, fixed_matchups=None):
    num_teams = len(teams)
    
    # Validate inputs
    if num_teams % 2 != 0:
        return {
            'status': 'ERROR',
            'message': 'Number of teams must be even',
            'solution_count': 0,
            'solutions': []
        }
    
    if num_weeks < num_teams - 1:
        return {
            'status': 'ERROR',
            'message': f'Season too short. Need at least {num_teams - 1} weeks for each team to play each other once.',
            'solution_count': 0,
            'solutions': []
        }
    
    # Create team indices
    team_indices = {team: i for i, team in enumerate(teams)}
    
    # Set up divisions if used
    divisions = []
    if use_divisions and division_teams:
        for division in division_teams:
            divisions.append([team_indices[team] for team in division])
    
    model = cp_model.CpModel()

    # Create binary variables for each possible game in each week
    game = {}
    for w in range(num_weeks):
        for i in range(num_teams):
            for j in range(num_teams):
                if i != j:
                    game[(w, i, j)] = model.NewBoolVar(f'game_w{w}_{teams[i]}_at_{teams[j]}')

    # (1) Each team plays exactly one game per week
    for w in range(num_weeks):
        for t in range(num_teams):
            model.Add(
                sum(game[(w, t, j)] for j in range(num_teams) if j != t) +
                sum(game[(w, i, t)] for i in range(num_teams) if i != t)
                == 1
            )

    # (2) Home/away balance
    # For even-week seasons, each team has equal home and away games
    # For odd-week seasons, teams have at most 1 difference between home and away games
    min_home_games = (num_weeks - 1) // 2
    max_home_games = math.ceil(num_weeks / 2)
    
    for t in range(num_teams):
        home_games = sum(game[(w, i, t)] for w in range(num_weeks) for i in range(num_teams) if i != t)
        model.Add(home_games >= min_home_games)
        model.Add(home_games <= max_home_games)
        
        away_games = sum(game[(w, t, j)] for w in range(num_weeks) for j in range(num_teams) if j != t)
        model.Add(away_games >= min_home_games)
        model.Add(away_games <= max_home_games)

    # (3) No team can have 3+ consecutive home/away games
    for t in range(num_teams):
        for w in range(num_weeks - 2):
            model.Add(
                sum(game[(w+i, j, t)] for i in range(3) for j in range(num_teams) if j != t) <= 2
            )
            model.Add(
                sum(game[(w+i, t, j)] for i in range(3) for j in range(num_teams) if j != t) <= 2
            )

    # (4) No team can play the same opponent within 4 weeks
    for i in range(num_teams):
        for j in range(num_teams):
            if i != j:
                for w in range(num_weeks - 4):
                    for gap in range(1, 5):
                        if w + gap < num_weeks:
                            model.Add(
                                game[(w, i, j)] + game[(w, j, i)] +
                                game[(w + gap, i, j)] + game[(w + gap, j, i)] <= 1
                            )
    
    # (5) Add scheduling rules based on divisions and season length
    if use_divisions and divisions:
        # With divisions: 
        # - Teams play all divisional opponents home and away
        # - Teams play all non-divisional opponents at least once
        for div in divisions:
            # Divisional matchups: each pair in the same division plays home and away
            for idx1 in range(len(div)):
                for idx2 in range(idx1 + 1, len(div)):
                    i = div[idx1]
                    j = div[idx2]
                    model.Add(sum(game[(w, i, j)] for w in range(num_weeks)) == 1)
                    model.Add(sum(game[(w, j, i)] for w in range(num_weeks)) == 1)
        
        # Inter-divisional matchups
        for div1_idx in range(len(divisions)):
            for div2_idx in range(div1_idx + 1, len(divisions)):
                for i in divisions[div1_idx]:
                    for j in divisions[div2_idx]:
                        # Each team plays each team from other divisions at least once
                        model.Add(sum(game[(w, i, j)] + game[(w, j, i)] for w in range(num_weeks)) >= 1)
                        
                        # For 14-week seasons, allow up to 2 games between inter-division teams
                        if num_weeks >= 14:
                            model.Add(sum(game[(w, i, j)] + game[(w, j, i)] for w in range(num_weeks)) <= 2)
                        else:
                            # For 13-week seasons, exactly 1 game between inter-division teams
                            model.Add(sum(game[(w, i, j)] + game[(w, j, i)] for w in range(num_weeks)) == 1)
    else:
        # Without divisions:
        # - Each team plays every other team at least once
        # - If a team plays an opponent twice, it must be home and away
        for i in range(num_teams):
            for j in range(num_teams):
                if i != j:
                    # Each team plays each other team at least once
                    model.Add(sum(game[(w, i, j)] + game[(w, j, i)] for w in range(num_weeks)) >= 1)
                    
                    # If a team plays an opponent twice, it must be once home and once away
                    # First, create a variable to track if they play twice
                    plays_twice = model.NewBoolVar(f'plays_twice_{i}_{j}')
                    
                    # Link the plays_twice variable to the condition
                    model.Add(sum(game[(w, i, j)] + game[(w, j, i)] for w in range(num_weeks)) >= 2).OnlyEnforceIf(plays_twice)
                    model.Add(sum(game[(w, i, j)] + game[(w, j, i)] for w in range(num_weeks)) <= 1).OnlyEnforceIf(plays_twice.Not())
                    
                    # If they play twice, ensure it's once home and once away
                    model.Add(sum(game[(w, i, j)] for w in range(num_weeks)) == 1).OnlyEnforceIf(plays_twice)
                    model.Add(sum(game[(w, j, i)] for w in range(num_weeks)) == 1).OnlyEnforceIf(plays_twice)
                    
                    # For 14-week seasons, allow up to 2 games between any teams
                    if num_weeks >= 14:
                        model.Add(sum(game[(w, i, j)] + game[(w, j, i)] for w in range(num_weeks)) <= 2)

    # (6) Add fixed matchups if provided
    if fixed_matchups:
        for matchup in fixed_matchups:
            week = matchup['week'] - 1  # Convert to 0-indexed
            team1 = team_indices[matchup['team1']]
            team2 = team_indices[matchup['team2']]
            
            if matchup['direction'] == 'either':
                # Either team1@team2 or team2@team1
                model.Add(game[(week, team1, team2)] + game[(week, team2, team1)] == 1)
            elif matchup['direction'] == 'team1_away':
                # team1 is away, team2 is home
                model.Add(game[(week, team1, team2)] == 1)
            elif matchup['direction'] == 'team2_away':
                # team2 is away, team1 is home
                model.Add(game[(week, team2, team1)] == 1)

    # Solve the model
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 120.0

    # Find solutions
    solution_limit = 50
    solution_counter = SolutionCounter(solution_limit, game, teams, num_teams, num_weeks)
    status = solver.SearchForAllSolutions(model, solution_counter)

    return {
        'status': solver.StatusName(status),
        'solution_count': solution_counter.solution_count(),
        'solutions': solution_counter.solutions()
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    teams = data['teams']
    num_weeks = int(data['num_weeks'])
    use_divisions = data['use_divisions']
    division_teams = data.get('division_teams', None)
    fixed_matchups = data.get('fixed_matchups', [])
    
    result = generate_schedule(teams, num_weeks, use_divisions, division_teams, fixed_matchups)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True) 
