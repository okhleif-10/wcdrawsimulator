# logic.py
from typing import List, Dict, Tuple, Set, Optional
import random

# ----------------------------
# ------- Core Constants -----
# ----------------------------

GROUPS = [chr(c) for c in range(ord('A'), ord('L') + 1)]  # A..L
POT_LABELS = ["pot1", "pot2", "pot3", "pot4"]

HOSTS_POT1 = [
    ("🇲🇽 Mexico", "A"),
    ("🇨🇦 Canada", "B"),
    ("🇺🇸 United States", "D"),
]
UEFA = "UEFA"
MAX_PER_CONFED = 1
MAX_UEFA = 2

# ----------------------------
# -------- Helpers --------
# ----------------------------

def set_error(state: Dict, msg: str) -> None:
    state["error"] = msg
    state["log"].append(f"❌ {msg}")

def team_already_placed(groups: Dict[str, List[Dict]], team: Dict) -> bool:
    name = team["name"]
    for g in GROUPS:
        if any(t["name"] == name for t in groups[g]):
            return True
    return False

def clear_queues(state: Dict, which: Optional[List[str]] = None) -> None:
    """Remove stale draw queues after non-incremental placements."""
    keys = which or ["p1_queue", "p2_queue", "p3_queue", "p4_queue"]
    for k in keys:
        if k in state:
            del state[k]

# ----------------------------
# -------- Core Logic --------
# ----------------------------

def confed_ok_to_add(group: List[Dict], team: Dict) -> bool:
    confeds = [t["confederation"] for t in group]
    confed = team["confederation"]
    if confed == UEFA:
        return confeds.count(UEFA) < MAX_UEFA
    else:
        return confeds.count(confed) < MAX_PER_CONFED

def first_available_group_for_pot1_after_hosts(groups_filled: Dict[str, List[Dict]]) -> Optional[str]:
    for g in GROUPS:
        if len(groups_filled[g]) == 0:
            return g
    return None

def first_available_group_with_constraints(
    groups_filled: Dict[str, List[Dict]],
    team: Dict,
    target_size: int,
    allow_fallback: bool = False
) -> Optional[str]:
    """
    Return the first alphabetical group that respects confed constraints
    and currently has `target_size` teams.
    If allow_fallback=True: fallback to any group with < target_size+1 that fits.
    """
    for g in GROUPS:
        if len(groups_filled[g]) == target_size and confed_ok_to_add(groups_filled[g], team):
            return g
    if allow_fallback:
        for g in GROUPS:
            if len(groups_filled[g]) < target_size + 1 and confed_ok_to_add(groups_filled[g], team):
                return g
    return None

# ---------- Generic candidate & matching ----------

def candidate_groups(team: Dict, groups_after: Dict[str, List[Dict]], required_size: int) -> List[str]:
    return [
        g for g in GROUPS
        if len(groups_after[g]) == required_size and confed_ok_to_add(groups_after[g], team)
    ]

def perfect_matching(
    groups_after: Dict[str, List[Dict]],
    remaining_teams: List[Dict],
    required_size: int
) -> Optional[Dict[str, str]]:
    """
    Bipartite matching: teams -> groups (of current size `required_size`).
    Returns {group -> team_name} if perfect assignment exists; else None.
    """
    # Build candidate lists
    candidates: Dict[str, List[str]] = {
        t["name"]: candidate_groups(t, groups_after, required_size) for t in remaining_teams
    }
    if any(len(v) == 0 for v in candidates.values()):
        return None

    match_team_for_group: Dict[str, str] = {}  # group -> team_name

    def try_assign(team_name: str, seen_groups: Set[str]) -> bool:
        for g in sorted(candidates[team_name]):
            if g in seen_groups:
                continue
            seen_groups.add(g)
            if g not in match_team_for_group or try_assign(match_team_for_group[g], seen_groups):
                match_team_for_group[g] = team_name
                return True
        return False

    # Heuristic: teams with fewer options first
    order = sorted(remaining_teams, key=lambda t: len(candidates[t["name"]]))
    for t in order:
        if not try_assign(t["name"], set()):
            return None
    return match_team_for_group

def find_safe_group_for_team(
    groups: Dict[str, List[Dict]],
    team: Dict,
    remaining_teams: List[Dict],
    required_size: int
) -> Optional[str]:
    """
    Choose a group for `team` such that:
      1) The group is a legal candidate now; and
      2) After placing `team` there, all `remaining_teams` can still be assigned
         via a perfect matching.
    Returns the chosen group letter, or None if none are safe.
    """
    cands = candidate_groups(team, groups, required_size)
    for g in sorted(cands):
        # Simulate placing team into g
        new_groups = {k: list(v) for k, v in groups.items()}
        new_groups[g] = list(new_groups[g]) + [team]
        # Check global feasibility for the rest
        if perfect_matching(new_groups, remaining_teams, required_size) is not None:
            return g
    return None

# ----------------------------
# --------- Pot Steps --------
# ----------------------------

def pot1(state: Dict) -> bool:
    pot = state["pots"]["pot1"]
    names = {t["name"]: t for t in pot}

    # Fixed hosts
    for name, group in HOSTS_POT1:
        if name in names and len(state["groups"][group]) == 0:
            t = names[name]
            if not team_already_placed(state["groups"], t):
                state["groups"][group].append(t)
            if t in pot:
                pot.remove(t)
            state["log"].append(f"Pot1: {t['name']} to Group {group}")

    # Remaining top seeds
    rnd = random.Random(state.get("seed"))
    rnd.shuffle(pot)
    for team in list(pot):
        if team_already_placed(state["groups"], team):
            # sanitize: if already placed somehow, just remove from pot
            state["pots"]["pot1"].remove(team)
            continue
        g = first_available_group_for_pot1_after_hosts(state["groups"])
        if g is None:
            break
        state["groups"][g].append(team)
        state["log"].append(f"Pot1: {team['name']} to Group {g}")
        state["pots"]["pot1"].remove(team)
    clear_queues(state, ["p1_queue"])  # safety
    return True

def pot2(state: Dict) -> bool:
    """
    Pot 2: For each team, pick a group that is legal *and* keeps a feasible
    completion for the remaining pot2 teams (via perfect_matching lookahead).
    """
    pot = state["pots"]["pot2"]
    rnd = random.Random(state.get("seed"))
    rnd.shuffle(pot)

    # Work through the live pot list
    while pot:
        team = pot[0]
        if team_already_placed(state["groups"], team):
            pot.remove(team)
            continue

        # Remaining teams after this one
        remaining = [t for t in pot[1:] if not team_already_placed(state["groups"], t)]

        g = find_safe_group_for_team(state["groups"], team, remaining, required_size=1)
        if g is None:
            set_error(state, f"Pot2 placement failed for {team['name']} (no safe group).")
            return False

        state["groups"][g].append(team)
        state["log"].append(f"Pot2: {team['name']} to Group {g}")
        state["pots"]["pot2"].remove(team)  # also removes from pot, since pot is same list

    clear_queues(state, ["p2_queue"])
    return True

def pot3(state: Dict) -> bool:
    """
    Pot 3: For each team, pick a group that is legal *and* keeps a feasible
    completion for the remaining pot3 teams (via perfect_matching lookahead).
    """
    pot = state["pots"]["pot3"]
    rnd = random.Random(state.get("seed"))
    rnd.shuffle(pot)

    while pot:
        team = pot[0]
        if team_already_placed(state["groups"], team):
            pot.remove(team)
            continue

        remaining = [t for t in pot[1:] if not team_already_placed(state["groups"], t)]

        g = find_safe_group_for_team(state["groups"], team, remaining, required_size=2)
        if g is None:
            set_error(state, f"Pot3 placement failed for {team['name']} (no safe group).")
            return False

        state["groups"][g].append(team)
        state["log"].append(f"Pot3: {team['name']} to Group {g}")
        state["pots"]["pot3"].remove(team)

    clear_queues(state, ["p3_queue"])
    return True

def pot4_possibilities(groups_now: Dict[str, List[Dict]], team: Dict) -> List[str]:
    return candidate_groups(team, groups_now, required_size=3)

def pot4(state: Dict) -> bool:
    """
    Pot 4: Backtracking w/ feasibility via perfect_matching for remaining.
    """
    pot = list(state["pots"]["pot4"])
    rnd = random.Random(state.get("seed"))
    rnd.shuffle(pot)

    def backtrack(
        groups_snapshot: Dict[str, List[Dict]],
        remaining: List[Dict],
        placed_sequence: List[Tuple[str, Dict]]
    ):
        if not remaining:
            return groups_snapshot, placed_sequence

        team = remaining[0]
        for g in sorted(pot4_possibilities(groups_snapshot, team)):
            new_groups = {k: list(v) for k, v in groups_snapshot.items()}
            new_groups[g] = list(new_groups[g]) + [team]
            if perfect_matching(new_groups, remaining[1:], required_size=3) is not None:
                res = backtrack(new_groups, remaining[1:], placed_sequence + [(g, team)])
                if res is not None:
                    return res
        return None

    start_groups = {k: list(v) for k, v in state["groups"].items()}
    result = backtrack(start_groups, pot, [])
    if result is None:
        set_error(state, "Pot4 placement failed to find a feasible assignment.")
        return False

    final_groups, sequence = result
    state["groups"] = final_groups
    for g, team in sequence:
        state["log"].append(f"Pot4: {team['name']} to Group {g}")
    state["pots"]["pot4"] = []
    clear_queues(state, ["p4_queue"])
    return True

# ----------------------------
# ---- Incremental Drawing ----
# ----------------------------

def draw_next_team(state: Dict):
    """
    Draw one team respecting rules; never throws.
    Uses queues but sanitizes against duplicates and stale queues.
    Adds lookahead (perfect_matching) for pot2 and pot3 so we don't
    pigeonhole future teams.
    """
    # Pot 1
    if state["pots"]["pot1"]:
        for nm, grp in HOSTS_POT1:
            if any(t["name"] == nm for t in state["pots"]["pot1"]) and len(state["groups"][grp]) == 0:
                t = next(t for t in state["pots"]["pot1"] if t["name"] == nm)
                if not team_already_placed(state["groups"], t):
                    state["groups"][grp].append(t)
                state["pots"]["pot1"].remove(t)
                state["log"].append(f"Pot1: {t['name']} to Group {grp}")
                return

        if "p1_queue" not in state or not state["p1_queue"]:
            rnd = random.Random(state.get("seed"))
            host_names = {nm for nm, _ in HOSTS_POT1}
            p1 = [t for t in state["pots"]["pot1"] if t["name"] not in host_names]
            rnd.shuffle(p1)
            state["p1_queue"] = p1

        team = state["p1_queue"].pop(0)
        if team_already_placed(state["groups"], team):
            # skip stale
            if team in state["pots"]["pot1"]:
                state["pots"]["pot1"].remove(team)
            return
        g = first_available_group_for_pot1_after_hosts(state["groups"])
        if g is None:
            state["log"].append("No slot found for Pot1 (unexpected).")
            return
        state["groups"][g].append(team)
        state["pots"]["pot1"].remove(team)
        state["log"].append(f"Pot1: {team['name']} to Group {g}")
        return

    # Pot 2
    if state["pots"]["pot2"]:
        if "p2_queue" not in state or not state["p2_queue"]:
            rnd = random.Random(state.get("seed"))
            p2 = list(state["pots"]["pot2"])
            rnd.shuffle(p2)
            state["p2_queue"] = p2

        team = state["p2_queue"].pop(0)
        if team_already_placed(state["groups"], team):
            if team in state["pots"]["pot2"]:
                state["pots"]["pot2"].remove(team)
            return

        # Remaining teams in this pot after this team
        remaining = [
            t for t in state["pots"]["pot2"]
            if t["name"] != team["name"] and not team_already_placed(state["groups"], t)
        ]

        g = find_safe_group_for_team(state["groups"], team, remaining, required_size=1)
        if g is None:
            # Cannot place this team without making the rest impossible
            msg = f"Pot2: cannot safely place {team['name']} under constraints."
            state["log"].append(msg)
            state["error"] = msg
            # put it back so the UI can decide to rerun/reset
            state["p2_queue"].insert(0, team)
            return

        state["groups"][g].append(team)
        state["pots"]["pot2"].remove(team)
        state["log"].append(f"Pot2: {team['name']} to Group {g}")
        return

    # Pot 3
    if state["pots"]["pot3"]:
        if "p3_queue" not in state or not state["p3_queue"]:
            rnd = random.Random(state.get("seed"))
            p3 = list(state["pots"]["pot3"])
            rnd.shuffle(p3)
            state["p3_queue"] = p3

        team = state["p3_queue"].pop(0)
        if team_already_placed(state["groups"], team):
            if team in state["pots"]["pot3"]:
                state["pots"]["pot3"].remove(team)
            return

        remaining = [
            t for t in state["pots"]["pot3"]
            if t["name"] != team["name"] and not team_already_placed(state["groups"], t)
        ]

        g = find_safe_group_for_team(state["groups"], team, remaining, required_size=2)
        if g is None:
            msg = f"Pot3: cannot safely place {team['name']} under constraints."
            state["log"].append(msg)
            state["error"] = msg
            state["p3_queue"].insert(0, team)
            return

        state["groups"][g].append(team)
        state["pots"]["pot3"].remove(team)
        state["log"].append(f"Pot3: {team['name']} to Group {g}")
        return

    # Pot 4
    if state["pots"]["pot4"]:
        if "p4_queue" not in state or not state["p4_queue"]:
            rnd = random.Random(state.get("seed"))
            p4 = list(state["pots"]["pot4"])
            rnd.shuffle(p4)
            state["p4_queue"] = p4

        team = state["p4_queue"].pop(0)
        if team_already_placed(state["groups"], team):
            if team in state["pots"]["pot4"]:
                state["pots"]["pot4"].remove(team)
            return

        cands = sorted(pot4_possibilities(state["groups"], team))
        for g in cands:
            new_groups = {k: list(v) for k, v in state["groups"].items()}
            new_groups[g] = list(new_groups[g]) + [team]
            remaining = list(state["pots"]["pot4"])
            remaining.remove(team)
            if perfect_matching(new_groups, remaining, required_size=3) is not None:
                state["groups"][g].append(team)
                state["pots"]["pot4"].remove(team)
                state["log"].append(f"Pot4: {team['name']} to Group {g}")
                return

        # Full backtrack fallback
        try_full = [team] + list(state.get("p4_queue", []))
        start_groups = {k: list(v) for k, v in state["groups"].items()}

        def backtrack(groups_snapshot, rem):
            if not rem:
                return groups_snapshot, []
            t = rem[0]
            for gg in sorted(pot4_possibilities(groups_snapshot, t)):
                newg = {k: list(v) for k, v in groups_snapshot.items()}
                newg[gg] = list(newg[gg]) + [t]
                if perfect_matching(newg, rem[1:], required_size=3) is not None:
                    res = backtrack(newg, rem[1:])
                    if res is not None:
                        gfinal, seq = res
                        return gfinal, [(gg, t)] + seq
            return None

        res = backtrack(start_groups, try_full)
        if res is None:
            state["log"].append(f"Pot4: Failed to place {team['name']} feasibly.")
            state["error"] = f"Pot 4 failed: no feasible assignment after drawing {team['name']}."
            state.setdefault("p4_queue", []).insert(0, team)
            return

        gfinal, seq = res
        state["groups"] = gfinal
        for gg, tt in seq:
            if tt in state["pots"]["pot4"]:
                state["pots"]["pot4"].remove(tt)
            if "p4_queue" in state and tt in state["p4_queue"]:
                state["p4_queue"].remove(tt)
            state["log"].append(f"Pot4: {tt['name']} to Group {gg}")
        clear_queues(state, ["p4_queue"])
        return

def complete_draw(state: Dict) -> bool:
    """Finish the entire draw in one go, respecting all rules. Returns True on success, False if any pot fails."""
    state.pop("error", None)  # clear last error if any
    if state["pots"]["pot1"]:
        pot1(state)
    if state["pots"]["pot2"]:
        if not pot2(state):
            return False
    if state["pots"]["pot3"]:
        if not pot3(state):
            return False
    if state["pots"]["pot4"]:
        if not pot4(state):
            return False
    return True
