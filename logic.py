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
    """Remove stale draw queues after a full reset."""
    keys = which or ["p1_queue", "p2_queue", "p3_queue", "p4_queue"]
    for k in keys:
        if k in state:
            del state[k]

def group_has_uefa(group: List[Dict]) -> bool:
    return any(t["confederation"] == UEFA for t in group)

def groups_without_uefa(groups: Dict[str, List[Dict]]) -> List[str]:
    """Return all group letters that currently have no UEFA team."""
    return [g for g in GROUPS if not group_has_uefa(groups[g])]

def count_uefa_teams(teams: List[Dict]) -> int:
    return sum(1 for t in teams if t["confederation"] == UEFA)

def uefa_requirement_enabled(state: Dict) -> bool:
    """
    For Option 1 (DEFAULT_POTS): True -> every group must have at least one UEFA.
    For Option 2 (PO_POT4): False -> no such requirement.
    Default to True if not set.
    """
    return state.get("require_uefa_in_every_group", True)

# ----------------------------
# --- Global UEFA feasibility
# ----------------------------

def uefa_coverage_still_possible(
    state: Dict,
    groups_after: Dict[str, List[Dict]],
    remaining_current_pot: List[Dict],
    current_pot_label: str,
) -> bool:
    """
    Global check for the "every group must have a UEFA" requirement.

    If that requirement is disabled (Option 2 / PO_POT4), this returns True
    immediately.

    Otherwise (Option 1), for every group that currently has NO UEFA team, there
    must exist at least one *remaining* UEFA team (from current pot + all later
    pots) that could legally be added to that group at some point:

        - The group must not already be full (len < 4),
        - confed_ok_to_add(group, that_UEFA_team) must be True.
    """
    if not uefa_requirement_enabled(state):
        return True

    # Collect all remaining UEFA teams in current + later pots
    all_remaining_uefa: List[Dict] = []
    for t in remaining_current_pot:
        if t["confederation"] == UEFA:
            all_remaining_uefa.append(t)

    idx = POT_LABELS.index(current_pot_label)
    for p in POT_LABELS[idx + 1:]:
        for t in state["pots"].get(p, []):
            if t["confederation"] == UEFA:
                all_remaining_uefa.append(t)

    missing_groups = [g for g in GROUPS if not group_has_uefa(groups_after[g])]

    # Quick necessary condition: can't have more UEFA-less groups than total remaining UEFA
    if len(missing_groups) > len(all_remaining_uefa):
        return False

    # For each UEFA-less group, confirm there exists at least one remaining UEFA
    # that could actually be added there (group not full, and confed-ok)
    for g in missing_groups:
        grp = groups_after[g]
        if len(grp) >= 4:
            # Already full with 0 UEFA: impossible to fix
            return False

        ok_for_this_group = False
        for t in all_remaining_uefa:
            if confed_ok_to_add(grp, t):
                ok_for_this_group = True
                break

        if not ok_for_this_group:
            return False

    return True


# ----------------------------
# -------- Core Logic --------
# ----------------------------

def confed_ok_to_add(group: List[Dict], team: Dict) -> bool:
    """Per-group confed rules: UEFA ≤ 2; all others ≤ 1."""
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
    Bipartite matching: teams -> groups (of current size `required_size`).
    Returns {group -> team_name} if perfect assignment exists; else None.
    This checks only group-size + confederation constraints (no UEFA-coverage rule).
    """
    candidates: Dict[str, List[str]] = {
        t["name"]: candidate_groups(t, groups_after, required_size) for t in remaining_teams
    }
    if any(len(v) == 0 for v in candidates.values()):
        return None

    match_team_for_group: Dict[str, str] = {}  # group -> team_name

    def try_assign(team_name: str, seen_groups: Set[str]) -> bool:
        for g in sorted(candidates[team_name]):  # alphabetical; no RNG
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
    Pick any group (A→L) that is legal now *and* leaves the remaining teams
    feasible (via perfect_matching).
    """
    cands = candidate_groups(team, groups, required_size)
    for g in sorted(cands):
        new_groups = {k: list(v) for k, v in groups.items()}
        new_groups[g] = list(new_groups[g]) + [team]
        if perfect_matching(new_groups, remaining_teams, required_size) is not None:
            return g
    return None

def find_safe_group_for_pot2_uefa(
    state: Dict,
    team: Dict,
    remaining_teams: List[Dict]
) -> Optional[str]:
    """
    Helper for Pot 2 UEFA teams (incremental mode):
    - Must be confed-legal and allow a perfect matching for remaining Pot 2 teams.
    - Must keep it possible to cover all UEFA-less groups using:
          remaining Pot 2 UEFA + UEFA from later pots (3 and 4),
      but only if the UEFA-per-group requirement is enabled.
    """
    assert team["confederation"] == UEFA

    cands = candidate_groups(team, state["groups"], required_size=1)
    for g in sorted(cands):
        # Simulate putting this team in group g
        new_groups = {k: list(v) for k, v in state["groups"].items()}
        new_groups[g] = list(new_groups[g]) + [team]

        # Confed/size feasibility for the rest of Pot 2
        if perfect_matching(new_groups, remaining_teams, required_size=1) is None:
            continue

        # Global UEFA coverage feasibility from this point on
        if not uefa_coverage_still_possible(state, new_groups, remaining_teams, "pot2"):
            continue

        return g

    return None

def pot4_possibilities(groups_now: Dict[str, List[Dict]], team: Dict) -> List[str]:
    return candidate_groups(team, groups_now, required_size=3)

# ----------------------------
# ---- Incremental Drawing ----
# ----------------------------

def draw_next_team(state: Dict):
    """
    Draw one team respecting all rules; never throws.
    This is the *single* source of truth for the draw logic.
    Both:
      - The "Draw next team" button, and
      - The "Complete draw" button
    use *this* function, so for a given seed the outcome is identical.
    """

    # Use a single persistent RNG per draw, seeded once from state["seed"].
    # This guarantees that calling Draw Next vs Complete Draw from any point
    # will consume the same random sequence.
    if "_rng" not in state or state.get("_rng_seed") != state.get("seed"):
        state["_rng"] = random.Random(state.get("seed"))
        state["_rng_seed"] = state.get("seed")

    # ---------------- Pot 1 ----------------
    if state["pots"]["pot1"]:
        # Place hosts first in fixed groups
        for nm, grp in HOSTS_POT1:
            if any(t["name"] == nm for t in state["pots"]["pot1"]) and len(state["groups"][grp]) == 0:
                t = next(t for t in state["pots"]["pot1"] if t["name"] == nm)
                if not team_already_placed(state["groups"], t):
                    state["groups"][grp].append(t)
                state["pots"]["pot1"].remove(t)
                state["log"].append(f"Pot1: {t['name']} to Group {grp}")
                return

        # Non-hosts: fixed shuffle → queue → A→L into first empty group
        if "p1_queue" not in state or not state["p1_queue"]:
            rnd = state["_rng"]
            host_names = {nm for nm, _ in HOSTS_POT1}
            p1 = [t for t in state["pots"]["pot1"] if t["name"] not in host_names]
            rnd.shuffle(p1)
            state["p1_queue"] = p1

        team = state["p1_queue"].pop(0)
        if team_already_placed(state["groups"], team):
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

    # ---------------- Pot 2 ----------------
    if state["pots"]["pot2"]:
        # Compute once when Pot 2 starts: how many UEFA-less groups
        # MUST be fixed by Pot 2, given how many UEFA are still available
        # in Pots 3 and 4 (this supports both distributions),
        # but only if UEFA-every-group requirement is enabled.
        if "must_fill_from_pot2" not in state:
            if not uefa_requirement_enabled(state):
                state["must_fill_from_pot2"] = 0
            else:
                uefa_less_start = groups_without_uefa(state["groups"])
                uefa_in_pot3 = count_uefa_teams(state["pots"]["pot3"])
                uefa_in_pot4 = count_uefa_teams(state["pots"]["pot4"])
                # Pots 3+4 together can fix at most (uefa_in_pot3 + uefa_in_pot4) UEFA-less groups,
                # so Pot 2 MUST fix any surplus above that.
                state["must_fill_from_pot2"] = max(
                    0, len(uefa_less_start) - (uefa_in_pot3 + uefa_in_pot4)
                )

        if "p2_queue" not in state or not state["p2_queue"]:
            rnd = state["_rng"]
            p2 = list(state["pots"]["pot2"])
            rnd.shuffle(p2)
            state["p2_queue"] = p2

        team = state["p2_queue"].pop(0)
        if team_already_placed(state["groups"], team):
            if team in state["pots"]["pot2"]:
                state["pots"]["pot2"].remove(team)
            return

        remaining = [
            t for t in state["pots"]["pot2"]
            if t["name"] != team["name"] and not team_already_placed(state["groups"], t)
        ]

        # --- UEFA team in Pot 2 ---
        if team["confederation"] == UEFA:
            cands = candidate_groups(team, state["groups"], required_size=1)
            uefa_less_now = set(groups_without_uefa(state["groups"]))
            preferred = [g for g in cands if g in uefa_less_now]

            chosen = None

            # If Pot 2 still *owes* some UEFA-less groups, try to fill them first.
            if state["must_fill_from_pot2"] > 0 and preferred:
                for g in sorted(preferred):
                    new_groups = {k: list(v) for k, v in state["groups"].items()}
                    new_groups[g] = list(new_groups[g]) + [team]
                    if perfect_matching(new_groups, remaining, required_size=1) is not None and \
                       uefa_coverage_still_possible(state, new_groups, remaining, "pot2"):
                        chosen = g
                        state["must_fill_from_pot2"] -= 1
                        break

            # If we couldn't (or don't *need* to), fall back to generic safe UEFA placement.
            if chosen is None:
                chosen = find_safe_group_for_pot2_uefa(state, team, remaining)

            if chosen is None:
                msg = f"Pot2: cannot safely place {team['name']} under constraints."
                state["log"].append(msg)
                state["error"] = msg
                state["p2_queue"].insert(0, team)
                return

            g = chosen

        # --- Non-UEFA team in Pot 2 ---
        else:
            g = find_safe_group_for_team(state["groups"], team, remaining, required_size=1)
            if g is None:
                msg = f"Pot2: cannot safely place {team['name']} under constraints."
                state["log"].append(msg)
                state["error"] = msg
                state["p2_queue"].insert(0, team)
                return

        state["groups"][g].append(team)
        state["pots"]["pot2"].remove(team)
        state["log"].append(f"Pot2: {team['name']} to Group {g}")
        return

    # ---------------- Pot 3 ----------------
    if state["pots"]["pot3"]:
        if "p3_queue" not in state or not state["p3_queue"]:
            rnd = state["_rng"]
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

        uefa_req = uefa_requirement_enabled(state)

        # UEFA in Pot 3
        if team["confederation"] == UEFA:
            # If UEFA-per-group requirement is disabled (Option 2),
            # we place it in the first confed-legal group alphabetically.
            if not uefa_req:
                cands = candidate_groups(team, state["groups"], required_size=2)
                if not cands:
                    msg = f"Pot3: no confed-legal group for {team['name']}."
                    state["log"].append(msg)
                    state["error"] = msg
                    state["p3_queue"].insert(0, team)
                    return
                g = sorted(cands)[0]
            else:
                # UEFA-per-group requirement enabled (Option 1): strong logic
                cands = candidate_groups(team, state["groups"], required_size=2)
                uefa_less = set(groups_without_uefa(state["groups"]))
                preferred = [g for g in cands if g in uefa_less]

                chosen = None

                # 1) Try UEFA-less groups safely
                for g in sorted(preferred):
                    new_groups = {k: list(v) for k, v in state["groups"].items()}
                    new_groups[g] = list(new_groups[g]) + [team]

                    if perfect_matching(new_groups, remaining, required_size=2) is None:
                        continue

                    if not uefa_coverage_still_possible(state, new_groups, remaining, "pot3"):
                        continue

                    chosen = g
                    break

                # 2) Otherwise, any safe group (UEFA may go on top of an existing UEFA)
                if chosen is None:
                    for g in sorted(cands):
                        new_groups = {k: list(v) for k, v in state["groups"].items()}
                        new_groups[g] = list(new_groups[g]) + [team]

                        if perfect_matching(new_groups, remaining, required_size=2) is None:
                            continue

                        if not uefa_coverage_still_possible(state, new_groups, remaining, "pot3"):
                            continue

                        chosen = g
                        break

                if chosen is None:
                    msg = f"Pot3: cannot safely place {team['name']} under constraints."
                    state["log"].append(msg)
                    state["error"] = msg
                    state["p3_queue"].insert(0, team)
                    return

                g = chosen

        # Non-UEFA in Pot 3
        else:
            all_cands = candidate_groups(team, state["groups"], required_size=2)
            if not all_cands:
                msg = f"Pot3: no confed-legal group for {team['name']}."
                state["log"].append(msg)
                state["error"] = msg
                state["p3_queue"].insert(0, team)
                return

            if not uefa_req:
                # Option 2 (PO_POT4): no "UEFA in every group" requirement.
                # We still need to avoid painting ourselves into a corner,
                # so use the same perfect-matching-based safety check as elsewhere.
                g = find_safe_group_for_team(
                    state["groups"],
                    team,
                    remaining,
                    required_size=2,
                )
                if g is None:
                    msg = f"Pot3: cannot safely place {team['name']} under constraints."
                    state["log"].append(msg)
                    state["error"] = msg
                    state["p3_queue"].insert(0, team)
                    return
            else:
                # UEFA-per-group requirement enabled (Option 1): protect UEFA-less groups.
                uefa_less = set(groups_without_uefa(state["groups"]))
                uefa_in_pot4 = count_uefa_teams(state["pots"]["pot4"])

                # If Pot 4 has 0 UEFA, non-UEFA cannot go into UEFA-less groups.
                if uefa_in_pot4 == 0:
                    allowed_cands = [gg for gg in all_cands if gg not in uefa_less]

                    chosen = None
                    for gg in sorted(allowed_cands):
                        new_groups = {k: list(v) for k, v in state["groups"].items()}
                        new_groups[gg] = list(new_groups[gg]) + [team]

                        if perfect_matching(new_groups, remaining, required_size=2) is None:
                            continue

                        if not uefa_coverage_still_possible(state, new_groups, remaining, "pot3"):
                            continue

                        chosen = gg
                        break

                    if chosen is None:
                        msg = (
                            f"Pot3: cannot place {team['name']} without using a UEFA-less group "
                            f"(which must be reserved for UEFA when Pot 4 has no UEFA)."
                        )
                        state["log"].append(msg)
                        state["error"] = msg
                        state["p3_queue"].insert(0, team)
                        return

                    g = chosen

                else:
                    # Pot 4 has UEFA available: prefer groups that already have a UEFA,
                    # but allow UEFA-less groups when globally safe.
                    ordered_cands = sorted(
                        all_cands,
                        key=lambda gg: (gg in uefa_less, gg)
                    )

                    chosen = None
                    for gg in ordered_cands:
                        new_groups = {k: list(v) for k, v in state["groups"].items()}
                        new_groups[gg] = list(new_groups[gg]) + [team]

                        if perfect_matching(new_groups, remaining, required_size=2) is None:
                            continue

                        if not uefa_coverage_still_possible(state, new_groups, remaining, "pot3"):
                            continue

                        chosen = gg
                        break

                    if chosen is None:
                        msg = f"Pot3: cannot safely place {team['name']} under constraints."
                        state["log"].append(msg)
                        state["error"] = msg
                        state["p3_queue"].insert(0, team)
                        return

                    g = chosen

        state["groups"][g].append(team)
        state["pots"]["pot3"].remove(team)
        state["log"].append(f"Pot3: {team['name']} to Group {g}")
        return

    # ---------------- Pot 4 ----------------
    if state["pots"]["pot4"]:
        if "p4_queue" not in state or not state["p4_queue"]:
            rnd = state["_rng"]
            p4 = list(state["pots"]["pot4"])
            rnd.shuffle(p4)
            state["p4_queue"] = p4

        team = state["p4_queue"].pop(0)
        if team_already_placed(state["groups"], team):
            if team in state["pots"]["pot4"]:
                state["pots"]["pot4"].remove(team)
            return

        # Try local feasible placement first
        cands = sorted(pot4_possibilities(state["groups"], team))
        for g in cands:
            new_groups = {k: list(v) for k, v in state["groups"].items()}
            new_groups[g] = list(new_groups[g]) + [team]

            remaining = list(state["pots"]["pot4"])
            remaining.remove(team)

            # 1) Confed + group-size feasibility
            if perfect_matching(new_groups, remaining, required_size=3) is None:
                continue

            # 2) Final UEFA coverage feasibility (Pot 4 is last pot, but this is a no-op
            #    when the UEFA-per-group requirement is disabled).
            if not uefa_coverage_still_possible(state, new_groups, remaining, "pot4"):
                continue

            state["groups"][g].append(team)
            state["pots"]["pot4"].remove(team)
            state["log"].append(f"Pot4: {team['name']} to Group {g}")
            return

        # Full backtrack fallback including queued teams
        try_full = [team] + list(state.get("p4_queue", []))
        start_groups = {k: list(v) for k, v in state["groups"].items()}

        def backtrack(groups_snapshot, rem):
            if not rem:
                return groups_snapshot, []
            t = rem[0]
            for gg in sorted(pot4_possibilities(groups_snapshot, t)):
                newg = {k: list(v) for k, v in groups_snapshot.items()}
                newg[gg] = list(newg[gg]) + [t]

                remaining = rem[1:]

                if perfect_matching(newg, remaining, required_size=3) is None:
                    continue

                if not uefa_coverage_still_possible(state, newg, remaining, "pot4"):
                    continue

                res = backtrack(newg, remaining)
                if res is not None:
                    gfinal, seq = res
                    return gfinal, [(gg, t)] + seq
            return None

        res = backtrack(start_groups, try_full)
        if res is None:
            msg = f"Pot4 failed: no feasible assignment after drawing {team['name']}."
            state["log"].append(msg)
            state["error"] = msg
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
    """
    Finish the entire draw using the *same* stepwise logic as draw_next_team.
    That guarantees that:
      - Using a given seed & pots,
      - Hitting "Complete draw" or clicking "Draw next team" 48 times
      will produce the exact same sequence.
    """
    state.pop("error", None)

    max_steps = 4 * len(GROUPS) + 20  # 48 teams + a little slack
    for _ in range(max_steps):
        # All pots empty -> done
        if all(not state["pots"][p] for p in POT_LABELS):
            return True

        draw_next_team(state)

        if "error" in state:
            # Let the UI handle popup & auto-retry using this error msg
            return False

    set_error(state, "Draw step limit exceeded; possible logic bug.")
    return False
