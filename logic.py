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
    ("🇺🇸 United States", "B"),
    ("🇨🇦 Canada", "D"),
]
UEFA = "UEFA"
MAX_PER_CONFED = 1
MAX_UEFA = 2

# ----------------------------
# -------- Core Logic --------
# ----------------------------

def confed_ok_to_add(group: List[Dict], team: Dict) -> bool:
    """Check confederation constraints if we add this team to the group now."""
    confeds = [t["confederation"] for t in group]
    confed = team["confederation"]
    if confed == UEFA:
        return confeds.count(UEFA) < MAX_UEFA
    else:
        return confeds.count(confed) < MAX_PER_CONFED

def first_available_group_for_pot1_after_hosts(groups_filled: Dict[str, List[Dict]]) -> Optional[str]:
    """Return the first group (A..L) with no team yet (for pot1 remaining teams)."""
    for g in GROUPS:
        if len(groups_filled[g]) == 0:
            return g
    return None

def first_available_group_with_constraints(
    groups_filled: Dict[str, List[Dict]],
    team: Dict,
    target_size: int
) -> Optional[str]:
    """
    Return the first alphabetical group that respects confed constraints
    and currently has `target_size` teams.
    Fallback: any group with < target_size+1 that fits.
    """
    for g in GROUPS:
        if len(groups_filled[g]) == target_size and confed_ok_to_add(groups_filled[g], team):
            return g
    for g in GROUPS:
        if len(groups_filled[g]) < target_size + 1 and confed_ok_to_add(groups_filled[g], team):
            return g
    return None

# ---------- Generic candidate & matching ----------

def candidate_groups(team: Dict, groups_after: Dict[str, List[Dict]], required_size: int) -> List[str]:
    """
    All groups where this team could go right now, given the group must currently
    have `required_size` teams and confed constraints must hold.
    """
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
    Try to assign each team in `remaining_teams` to a distinct group that currently
    has `required_size` teams, respecting confed constraints.
    Returns {group -> team_name} if a perfect assignment exists, else None.
    """
    # Build candidate map (team_name -> candidate groups)
    candidates: Dict[str, List[str]] = {
        t["name"]: candidate_groups(t, groups_after, required_size) for t in remaining_teams
    }
    if any(len(v) == 0 for v in candidates.values()):
        return None  # immediate infeasibility

    match_team_for_group: Dict[str, str] = {}  # group -> team_name

    def try_assign(team_name: str, seen_groups: Set[str]) -> bool:
        # keep alphabetical flavor
        for g in sorted(candidates[team_name]):
            if g in seen_groups:
                continue
            seen_groups.add(g)
            if g not in match_team_for_group or try_assign(match_team_for_group[g], seen_groups):
                match_team_for_group[g] = team_name
                return True
        return False

    # iterate teams in stable order
    for t in remaining_teams:
        if not try_assign(t["name"], set()):
            return None

    return match_team_for_group

# ----------------------------
# --------- Pot Steps --------
# ----------------------------

def pot1(state: Dict):
    """Pot 1: Mexico->A, USA->B, Canada->D. Then draw remaining & place into first empty group alphabetically."""
    pot = state["pots"]["pot1"]
    names = {t["name"]: t for t in pot}

    # Place required hosts in fixed order
    for name, group in HOSTS_POT1:
        if name in names and len(state["groups"][group]) == 0:
            t = names[name]
            state["groups"][group].append(t)
            pot.remove(t)
            state["log"].append(f"Pot1: {t['name']} to Group {group}")

    # Draw remaining in random order; place into first empty group by alpha
    rnd = random.Random(state.get("seed"))
    rnd.shuffle(pot)
    for team in list(pot):
        g = first_available_group_for_pot1_after_hosts(state["groups"])
        if g is None:
            break
        state["groups"][g].append(team)
        state["log"].append(f"Pot1: {team['name']} to Group {g}")
        state["pots"]["pot1"].remove(team)

def pot2(state: Dict):
    """Pot 2: draw random; place each into the first alphabetical legal group (UEFA≤2, others≤1) that has exactly 1 team."""
    pot = state["pots"]["pot2"]
    rnd = random.Random(state.get("seed"))
    rnd.shuffle(pot)
    for team in list(pot):
        g = first_available_group_with_constraints(state["groups"], team, target_size=1)
        if g is None:
            raise RuntimeError(f"Pot2 placement failed for {team['name']} (no legal group).")
        state["groups"][g].append(team)
        state["log"].append(f"Pot2: {team['name']} to Group {g}")
        state["pots"]["pot2"].remove(team)

def pot3(state: Dict):
    """
    Pot 3: draw random; place into first alphabetical legal group (UEFA≤2, others≤1).
    If a team can't be placed greedily, solve the rest of pot 3 with a perfect matching.
    """
    pot = state["pots"]["pot3"]
    rnd = random.Random(state.get("seed"))
    rnd.shuffle(pot)
    for _ in range(len(pot)):
        team = pot[0]  # always re-check the current first
        g = first_available_group_with_constraints(state["groups"], team, target_size=2)
        if g is not None:
            state["groups"][g].append(team)
            state["log"].append(f"Pot3: {team['name']} to Group {g}")
            state["pots"]["pot3"].remove(team)
            continue

        # fallback: try a global perfect matching for ALL remaining pot3 (including this team)
        remaining = list(state["pots"]["pot3"])  # includes `team`
        mapping = perfect_matching(state["groups"], remaining, required_size=2)
        if mapping is None:
            raise RuntimeError(f"Pot3 placement failed for {team['name']}.")

        # Commit entire matching in one shot
        name_to_team = {t["name"]: t for t in remaining}
        for gg, tname in mapping.items():
            tt = name_to_team[tname]
            state["groups"][gg].append(tt)
            state["log"].append(f"Pot3: {tt['name']} to Group {gg}")
            if tt in state["pots"]["pot3"]:
                state["pots"]["pot3"].remove(tt)
        break  # everything placed via matching

def pot4_possibilities(groups_now: Dict[str, List[Dict]], team: Dict) -> List[str]:
    """All feasible groups for a given pot4 team right now."""
    return candidate_groups(team, groups_now, required_size=3)

def pot4(state: Dict):
    """
    Pot 4: constraints as pot3, PLUS global feasibility/backtracking to guarantee a completion.
    Uses perfect_matching(...) for feasibility checks.
    """
    pot = list(state["pots"]["pot4"])  # work on a copy for safe backtracking
    rnd = random.Random(state.get("seed"))
    rnd.shuffle(pot)

    def backtrack(groups_snapshot: Dict[str, List[Dict]], remaining: List[Dict], placed_sequence: List[Tuple[str, Dict]]):
        if not remaining:
            return groups_snapshot, placed_sequence

        team = remaining[0]
        candidates = sorted(pot4_possibilities(groups_snapshot, team))
        for g in candidates:
            new_groups = {k: list(v) for k, v in groups_snapshot.items()}
            new_groups[g] = list(new_groups[g]) + [team]
            # Feasibility for the rest via unified matcher
            if perfect_matching(new_groups, remaining[1:], required_size=3) is not None:
                res = backtrack(new_groups, remaining[1:], placed_sequence + [(g, team)])
                if res is not None:
                    return res
        return None

    # Kick off backtracking
    start_groups = {k: list(v) for k, v in state["groups"].items()}
    result = backtrack(start_groups, pot, [])
    if result is None:
        raise RuntimeError("Pot4 placement failed to find a feasible assignment.")
    final_groups, sequence = result

    # Commit to state
    state["groups"] = final_groups
    for g, team in sequence:
        state["log"].append(f"Pot4: {team['name']} to Group {g}")
    state["pots"]["pot4"] = []

# ----------------------------
# ---- Incremental Drawing ----
# ----------------------------

def draw_next_team(state: Dict):
    """
    Draw exactly one team following the rules. Mutates `state` in-place.
    Expects a dict-like `state` with keys: "pots", "groups", "log", and optionally "seed".
    """
    # Pot 1
    if state["pots"]["pot1"]:
        # Place hosts strictly in order: 🇲🇽 -> A, 🇺🇸 -> B, 🇨🇦 -> D
        for nm, grp in HOSTS_POT1:
            if any(t["name"] == nm for t in state["pots"]["pot1"]) and len(state["groups"][grp]) == 0:
                t = next(t for t in state["pots"]["pot1"] if t["name"] == nm)
                state["groups"][grp].append(t)
                state["pots"]["pot1"].remove(t)
                state["log"].append(f"Pot1: {t['name']} to Group {grp}")
                return

        # else draw one random and put into first empty group
        if "p1_queue" not in state or not state["p1_queue"]:
            rnd = random.Random(state.get("seed"))
            host_names = {nm for nm, _ in HOSTS_POT1}
            p1 = [t for t in state["pots"]["pot1"] if t["name"] not in host_names]
            rnd.shuffle(p1)
            state["p1_queue"] = p1

        team = state["p1_queue"].pop(0)
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
        g = first_available_group_with_constraints(state["groups"], team, target_size=1)
        if g is None:
            state["p2_queue"].insert(0, team)
            state["log"].append(f"Pot2: no legal slot yet for {team['name']} — try another draw or change seed.")
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
        g = first_available_group_with_constraints(state["groups"], team, target_size=2)
        if g is None:
            # fallback: global matching for remaining (including this drawn team)
            remaining = [team] + list(state["p3_queue"])
            mapping = perfect_matching(state["groups"], remaining, required_size=2)
            if mapping is None:
                state["log"].append(f"Pot3: failed to place {team['name']}.")
                state["p3_queue"].insert(0, team)
                return

            name_to_team = {t["name"]: t for t in remaining}
            for gg, tname in mapping.items():
                tt = name_to_team[tname]
                state["groups"][gg].append(tt)
                if tt in state["pots"]["pot3"]:
                    state["pots"]["pot3"].remove(tt)
                if "p3_queue" in state and tt in state["p3_queue"]:
                    state["p3_queue"].remove(tt)
                state["log"].append(f"Pot3: {tt['name']} to Group {gg}")
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

        # Full backtrack fallback over remaining
        try_full = [team] + list(state.get("p4_queue", []))
        start_groups = {k: list(v) for k, v in state["groups"].items()}

        def backtrack(groups_snapshot, rem):
            if not rem:
                return groups_snapshot, []
            t = rem[0]
            cands2 = sorted(pot4_possibilities(groups_snapshot, t))
            for gg in cands2:
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
            state.setdefault("p4_queue", []).insert(0, team)
            return

        gfinal, seq = res
        state["groups"] = gfinal
        for gg, tt in seq:
            if tt in state["pots"]["pot4"]:
                state["pots"]["pot4"].remove(tt)
            if tt is not team and "p4_queue" in state and tt in state["p4_queue"]:
                state["p4_queue"].remove(tt)
            state["log"].append(f"Pot4: {tt['name']} to Group {gg}")

def complete_draw(state: Dict):
    """Finish the entire draw in one go, respecting all rules."""
    if state["pots"]["pot1"]:
        pot1(state)
    if state["pots"]["pot2"]:
        pot2(state)
    if state["pots"]["pot3"]:
        pot3(state)
    if state["pots"]["pot4"]:
        pot4(state)
