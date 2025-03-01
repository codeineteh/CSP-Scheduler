from flask import Flask, render_template, request, jsonify
from ortools.sat.python import cp_model
import json
import subprocess
import io
import sys

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

def generate_schedule(west_teams, east_teams, fixed_matchups):
    teams = west_teams + east_teams
    num_teams = len(teams)
    num_weeks = 14

    # Create team indices
    team_indices = {team: i for i, team in enumerate(teams)}
    west = [team_indices[team] for team in west_teams]
    east = [team_indices[team] for team in east_teams]

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

    # (2) Divisional matchups
    for idx1 in range(len(west)):
        for idx2 in range(idx1 + 1, len(west)):
            i = west[idx1]
            j = west[idx2]
            model.Add(sum(game[(w, i, j)] for w in range(num_weeks)) == 1)
            model.Add(sum(game[(w, j, i)] for w in range(num_weeks)) == 1)
    
    for idx1 in range(len(east)):
        for idx2 in range(idx1 + 1, len(east)):
            i = east[idx1]
            j = east[idx2]
            model.Add(sum(game[(w, i, j)] for w in range(num_weeks)) == 1)
            model.Add(sum(game[(w, j, i)] for w in range(num_weeks)) == 1)

    # (3) Inter-divisional matchups
    for i in west:
        for j in east:
            inter_games = sum(game[(w, i, j)] + game[(w, j, i)] for w in range(num_weeks))
            model.Add(inter_games >= 1)
            model.Add(inter_games <= 2)

    # (4) Home/away balance
    for t in range(num_teams):
        model.Add(sum(game[(w, i, t)] for w in range(num_weeks) for i in range(num_teams) if i != t) == 7)
        model.Add(sum(game[(w, t, j)] for w in range(num_weeks) for j in range(num_teams) if j != t) == 7)

    # (5) Add fixed matchups
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

    # (6) No team can have 3+ consecutive home/away games
    for t in range(num_teams):
        for w in range(num_weeks - 2):
            model.Add(
                sum(game[(w+i, j, t)] for i in range(3) for j in range(num_teams) if j != t) <= 2
            )
            model.Add(
                sum(game[(w+i, t, j)] for i in range(3) for j in range(num_teams) if j != t) <= 2
            )

    # (7) No team can play the same opponent within 4 weeks
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
    # Capture the output of schedule_csp.py
    old_stdout = sys.stdout
    new_stdout = io.StringIO()
    sys.stdout = new_stdout
    
    # Import and run the main function
    from schedule_csp import main
    main()
    
    # Restore stdout and get the output
    sys.stdout = old_stdout
    output = new_stdout.getvalue()
    
    return render_template('index.html', output=output)

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    west_teams = data['west_teams']
    east_teams = data['east_teams']
    fixed_matchups = data['fixed_matchups']
    
    result = generate_schedule(west_teams, east_teams, fixed_matchups)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True) 
