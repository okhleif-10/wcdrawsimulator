# app.py
import json
from typing import List, Dict
from copy import deepcopy
import streamlit as st
import time

import logic as L  # use the pure-logic module

# ----------------------------
# ------- UI Utilities -------
# ----------------------------

# Reuse constants from logic
GROUPS = L.GROUPS
POT_LABELS = L.POT_LABELS


def init_session_state():
    """
    Initialize state exactly once and seed default pots so we never hit KeyError ('pot1').
    """
    if "initialized" not in st.session_state:
        st.session_state.pots_source_key = "Ranking Based (default)"   # which preset we're using
        st.session_state.pots = deepcopy(DEFAULT_POTS)            # seed defaults
        st.session_state.groups = {g: [] for g in GROUPS}
        st.session_state.draw_order = {p: [] for p in POT_LABELS}
        st.session_state.queue = []  # list of tuples (pot_label, team_index_in_pot_snapshot)
        st.session_state.log = []
        st.session_state.seed = None
        st.session_state.initialized = True
        if "pots_baseline" not in st.session_state:
            st.session_state.pots_baseline = deepcopy(st.session_state.pots)

    # Safety guard in case someone cleared pots elsewhere
    for key in POT_LABELS:
        st.session_state.pots.setdefault(key, [])


def reset_state(pots):
    # Deep-copy to avoid mutating caller/defaults
    st.session_state.pots = deepcopy(pots)
    st.session_state.groups = {g: [] for g in GROUPS}
    st.session_state.draw_order = {p: [] for p in POT_LABELS}
    st.session_state.queue = []
    st.session_state.log = []


def soft_reset_to_baseline():
    """Reset the draw back to the last configured pots (baseline), preserving the seed toggle."""
    reset_state(st.session_state.pots_baseline)
    st.success("Draw reset to last configured pots.")


def render_title():
    # --- World Cup logo ---
    st.markdown(
        """
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;margin-bottom:20px;">
            <img src="https://upload.wikimedia.org/wikipedia/en/1/17/2026_FIFA_World_Cup_emblem.svg"
                 alt="World Cup 2026 Logo" style="width:140px;height:auto;margin-bottom:10px;">
            <h1 style="margin:0;">World Cup 2026 Draw Simulator</h1>
            <span style="opacity:0.7;">(Groups A–L • 12 groups × 4 teams)</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_groups_table(groups):
    # MOBILE-FRIENDLY CSS (forces alphabetical stacking on small screens)
    st.markdown("""
        <style>
        /* Mobile layout override */
        @media (max-width: 768px) {
            .wc-group-col {
                width: 100% !important;
                display: block !important;
            }
        }
        </style>
    """, unsafe_allow_html=True)

    # Desktop: 4 columns (same as before)
    cols = st.columns(4)

    for idx, g in enumerate(GROUPS):
        # Wrap each column in a class we override on mobile
        with cols[idx % 4]:
            st.markdown(
                f"<div class='wc-group-col'>",
                unsafe_allow_html=True
            )

            st.markdown(f"### Group {g}")
            teams = groups[g]
            rows = teams + [{"name": "—", "confederation": "—", "pot": "—"}] * (4 - len(teams))

            style = (
                "border:1px solid #e5e7eb;border-radius:14px;"
                "padding:8px 10px;margin-bottom:12px;background:#fff;"
                "box-shadow:0 1px 2px rgba(0,0,0,.04);"
            )
            st.markdown(f"<div style='{style}'>", unsafe_allow_html=True)

            for t in rows:
                slot = f"{t['name']} ({t['confederation']})" if t['name'] != "—" else "—"
                st.markdown(f"- {slot}")

            st.markdown("</div></div>", unsafe_allow_html=True)



def show_failure_and_autoretry(msg: str, seconds: int = 3):
    """Show a full-screen popup and auto-reset + rerun after N seconds."""
    st.markdown(
        f"""
        <style>
        .wc-overlay {{ position: fixed; inset: 0; background: rgba(0,0,0,.6);
          z-index: 9999; display: flex; align-items: center; justify-content: center; }}
        .wc-card {{ background: #fff; border-radius: 20px; padding: 28px 36px; max-width: 560px;
          box-shadow: 0 15px 50px rgba(0,0,0,.3); text-align: center; }}
        .wc-card h2 {{ margin: 0 0 8px; font-size: 1.75rem; }}
        .wc-card p {{ margin: 0; opacity: .85; }}
        </style>
        <div class="wc-overlay">
          <div class="wc-card">
            <h2>❌ Draw Failed</h2>
            <p>{msg}</p>
            <p>Auto-retrying in <strong id="wc-count">{seconds}</strong>s…</p>
          </div>
        </div>
        <script>
          (function(){{
            let n = {seconds};
            const el = document.getElementById("wc-count");
            const tick = () => {{
              n = Math.max(0, n-1);
              if (el) el.textContent = n;
              if (n > 0) setTimeout(tick, 1000);
            }};
            tick();
          }})();
        </script>
        """,
        unsafe_allow_html=True,
    )
    time.sleep(seconds)
    try:
        if "pots_baseline" in st.session_state:
            reset_state(st.session_state.pots_baseline)
        else:
            soft_reset_to_baseline()
    except Exception:
        pass
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


def render_pots(pots):
    st.markdown("---")
    st.markdown("## Pots (remaining)")
    # Display all four pots in one row
    pot_cols = st.columns(4)

    for i, pot_label in enumerate(POT_LABELS):
        with pot_cols[i]:
            st.markdown(f"<h4 style='margin-bottom:4px'>{pot_label.upper()}</h4>", unsafe_allow_html=True)
            if pots.get(pot_label):
                for t in pots[pot_label]:
                    st.markdown(
                        f"<div style='padding:4px 6px;margin:2px 0;border-radius:6px;"
                        f"background:#ffffff;border:1px solid #eee;'>"
                        f"<strong>{t['name']}</strong> "
                        f"<span style='opacity:0.7'>({t['confederation']})</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    "<span style='opacity:0.6;font-style:italic;'>Empty</span>",
                    unsafe_allow_html=True,
                )


def parse_pot_string(pot_text: str, pot_num: int) -> List[Dict]:
    """
    Parse a multiline string like:
        🇲🇽 Mexico, CONCACAF
        🇺🇸 United States, CONCACAF
    into a list of {name, confederation, pot}.
    Blank lines are ignored.
    """
    teams = []
    for line in pot_text.strip().splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            st.warning(
                f"Skipping invalid line in Pot {pot_num}: "
                f"'{line}' (expected 'Name, Confederation')"
            )
            continue
        name, confed = parts[0], parts[1]
        teams.append({"name": name, "confederation": confed, "pot": pot_num})
    return teams


def ui_controls():
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        if st.button("🎲 Draw next team", use_container_width=True):
            try:
                L.draw_next_team(st.session_state)
                # if logic flagged a failure, show popup + auto-rerun
                if st.session_state.get("error"):
                    msg = st.session_state.pop("error")
                    show_failure_and_autoretry(msg)
            except Exception as e:
                # hard failure: surface and auto-rerun
                st.session_state["error"] = f"{e}"
                show_failure_and_autoretry(str(e))
    with c2:
        if st.button("🏁 Complete the draw", use_container_width=True):
            ok = L.complete_draw(st.session_state)
            if not ok or "error" in st.session_state:
                show_failure_and_autoretry(
                    st.session_state.pop("error", "A constraint couldn’t be fulfilled.")
                )

    with c3:
        if st.button("🔁 Reset draw", use_container_width=True):
            soft_reset_to_baseline()


# ----------------------------
# ---------- App Data --------
# ----------------------------

PO_POT4 = {
    "pot1": [
        {"name": "🇲🇽 Mexico", "confederation": "CONCACAF", "pot": 1},
        {"name": "🇨🇦 Canada", "confederation": "CONCACAF", "pot": 1},
        {"name": "🇺🇸 United States", "confederation": "CONCACAF", "pot": 1},
        {"name": "🇧🇷 Brazil", "confederation": "CONMEBOL", "pot": 1},
        {"name": "🇦🇷 Argentina", "confederation": "CONMEBOL", "pot": 1},
        {"name": "🇫🇷 France", "confederation": "UEFA", "pot": 1},
        {"name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 England", "confederation": "UEFA", "pot": 1},
        {"name": "🇪🇸 Spain", "confederation": "UEFA", "pot": 1},
        {"name": "🇵🇹 Portugal", "confederation": "UEFA", "pot": 1},
        {"name": "🇳🇱 Netherlands", "confederation": "UEFA", "pot": 1},
        {"name": "🇧🇪 Belgium", "confederation": "UEFA", "pot": 1},
        {"name": "🇩🇪 Germany", "confederation": "UEFA", "pot": 1},
    ],
    "pot2": [
        {"name": "🇭🇷 Croatia", "confederation": "UEFA", "pot": 2},
        {"name": "🇲🇦 Morocco", "confederation": "CAF", "pot": 2},
        {"name": "🇨🇴 Colombia", "confederation": "CONMEBOL", "pot": 2},
        {"name": "🇺🇾 Uruguay", "confederation": "CONMEBOL", "pot": 2},
        {"name": "🇯🇵 Japan", "confederation": "AFC", "pot": 2},
        {"name": "🇪🇨 Ecuador", "confederation": "CONMEBOL", "pot": 2},
        {"name": "🇨🇭 Switzerland", "confederation": "UEFA", "pot": 2},
        {"name": "🇸🇳 Senegal", "confederation": "CAF", "pot": 2},
        {"name": "🇮🇷 Iran", "confederation": "AFC", "pot": 2},
        {"name": "🇩🇰 Denmark", "confederation": "UEFA", "pot": 2},
        {"name": "🇰🇷 South Korea", "confederation": "AFC", "pot": 2},
        {"name": "🇦🇹 Austria", "confederation": "UEFA", "pot": 2},
    ],
    "pot3": [
        {"name": "🇦🇺 Australia", "confederation": "AFC", "pot": 3},
        {"name": "🇵🇦 Panama", "confederation": "CONCACAF", "pot": 3},
        {"name": "🇳🇴 Norway", "confederation": "UEFA", "pot": 3},
        {"name": "🇪🇬 Egypt", "confederation": "CAF", "pot": 3},
        {"name": "🇩🇿 Algeria", "confederation": "CAF", "pot": 3},
        {"name": "🇵🇾 Paraguay", "confederation": "CONMEBOL", "pot": 3},
        {"name": "🇨🇮 Ivory Coast", "confederation": "CAF", "pot": 3},
        {"name": "🇹🇳 Tunisia", "confederation": "CAF", "pot": 3},
        {"name": "🇶🇦 Qatar", "confederation": "AFC", "pot": 3},
        {"name": "🇺🇿 Uzbekistan", "confederation": "AFC", "pot": 3},
        {"name": "🇸🇦 Saudi Arabia", "confederation": "AFC", "pot": 3},
        {"name": "🇿🇦 South Africa", "confederation": "CAF", "pot": 3},
    ],
    "pot4": [
        {"name": "🇯🇴 Jordan", "confederation": "AFC", "pot": 4},
        {"name": "🇨🇻 Cape Verde", "confederation": "CAF", "pot": 4},
        {"name": "🇯🇲 Jamaica", "confederation": "CONCACAF", "pot": 4},
        {"name": "🇬🇭 Ghana", "confederation": "CAF", "pot": 4},
        {"name": "🇭🇹 Haiti", "confederation": "CONCACAF", "pot": 4},
        {"name": "🇳🇿 New Zealand", "confederation": "OFC", "pot": 4},
        {"name": "🇮🇹 Italy", "confederation": "UEFA", "pot": 4},
        {"name": "🇹🇷 Turkey", "confederation": "UEFA", "pot": 4},
        {"name": "🇺🇦 Ukraine", "confederation": "UEFA", "pot": 4},
        {"name": "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland", "confederation": "UEFA", "pot": 4},
        {"name": "🇧🇴 Bolivia", "confederation": "CONMEBOL", "pot": 4},
        {"name": "🇳🇬 Nigeria", "confederation": "CAF", "pot": 4},
    ],
}

DEFAULT_POTS = {
    "pot1": [
        {"name": "🇲🇽 Mexico", "confederation": "CONCACAF", "pot": 1},
        {"name": "🇨🇦 Canada", "confederation": "CONCACAF", "pot": 1},
        {"name": "🇺🇸 United States", "confederation": "CONCACAF", "pot": 1},
        {"name": "🇧🇷 Brazil", "confederation": "CONMEBOL", "pot": 1},
        {"name": "🇦🇷 Argentina", "confederation": "CONMEBOL", "pot": 1},
        {"name": "🇫🇷 France", "confederation": "UEFA", "pot": 1},
        {"name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 England", "confederation": "UEFA", "pot": 1},
        {"name": "🇪🇸 Spain", "confederation": "UEFA", "pot": 1},
        {"name": "🇵🇹 Portugal", "confederation": "UEFA", "pot": 1},
        {"name": "🇳🇱 Netherlands", "confederation": "UEFA", "pot": 1},
        {"name": "🇧🇪 Belgium", "confederation": "UEFA", "pot": 1},
        {"name": "🇮🇹 Italy", "confederation": "UEFA", "pot": 1},
    ],
    "pot2": [
        {"name": "🇩🇪 Germany", "confederation": "UEFA", "pot": 2},
        {"name": "🇭🇷 Croatia", "confederation": "UEFA", "pot": 2},
        {"name": "🇲🇦 Morocco", "confederation": "CAF", "pot": 2},
        {"name": "🇨🇴 Colombia", "confederation": "CONMEBOL", "pot": 2},
        {"name": "🇺🇾 Uruguay", "confederation": "CONMEBOL", "pot": 2},
        {"name": "🇨🇭 Switzerland", "confederation": "UEFA", "pot": 2},
        {"name": "🇯🇵 Japan", "confederation": "AFC", "pot": 2},
        {"name": "🇸🇳 Senegal", "confederation": "CAF", "pot": 2},
        {"name": "🇩🇰 Denmark", "confederation": "UEFA", "pot": 2},
        {"name": "🇮🇷 Iran", "confederation": "AFC", "pot": 2},
        {"name": "🇰🇷 South Korea", "confederation": "AFC", "pot": 2},
        {"name": "🇦🇹 Austria", "confederation": "UEFA", "pot": 2},
    ],
    "pot3": [
        {"name": "🇪🇨 Ecuador", "confederation": "CONMEBOL", "pot": 3},
        {"name": "🇦🇺 Australia", "confederation": "AFC", "pot": 3},
        {"name": "🇹🇷 Turkey", "confederation": "UEFA", "pot": 3},
        {"name": "🇺🇦 Ukraine", "confederation": "UEFA", "pot": 3},
        {"name": "🇳🇴 Norway", "confederation": "UEFA", "pot": 3},
        {"name": "🇵🇦 Panama", "confederation": "CONCACAF", "pot": 3},
        {"name": "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland", "confederation": "UEFA", "pot": 3},
        {"name": "🇪🇬 Egypt", "confederation": "CAF", "pot": 3},
        {"name": "🇩🇿 Algeria", "confederation": "CAF", "pot": 3},
        {"name": "🇳🇬 Nigeria", "confederation": "CAF", "pot": 3},
        {"name": "🇵🇾 Paraguay", "confederation": "CONMEBOL", "pot": 3},
        {"name": "🇹🇳 Tunisia", "confederation": "CAF", "pot": 3},
    ],
    "pot4": [
        {"name": "🇨🇮 Ivory Coast", "confederation": "CAF", "pot": 4},
        {"name": "🇶🇦 Qatar", "confederation": "AFC", "pot": 4},
        {"name": "🇺🇿 Uzbekistan", "confederation": "AFC", "pot": 4},
        {"name": "🇸🇦 Saudi Arabia", "confederation": "AFC", "pot": 4},
        {"name": "🇮🇶 Iraq", "confederation": "AFC", "pot": 4},
        {"name": "🇿🇦 South Africa", "confederation": "CAF", "pot": 4},
        {"name": "🇯🇴 Jordan", "confederation": "AFC", "pot": 4},
        {"name": "🇨🇻 Cape Verde", "confederation": "CAF", "pot": 4},
        {"name": "🇯🇲 Jamaica", "confederation": "CONCACAF", "pot": 4},
        {"name": "🇬🇭 Ghana", "confederation": "CAF", "pot": 4},
        {"name": "🇭🇹 Haiti", "confederation": "CONCACAF", "pot": 4},
        {"name": "🇳🇿 New Zealand", "confederation": "OFC", "pot": 4},
    ],
}

# ---- Chooseable pot sources ----
POT_SOURCES = {
    "Ranking Based (default)": "DEFAULT_POTS",
    "Playoff Based (option)": "PO_POT4",
}


# ----------------------------
# ---------- Main App --------
# ----------------------------

def main():
    st.set_page_config(page_title="World Cup 2026 Draw Simulator", layout="wide")
    init_session_state()
    render_title()

    # Sidebar controls
    with st.sidebar:
        st.markdown("### Settings")
        seed = st.number_input("Random seed (optional)", value=0, step=1)
        seed_toggle = st.checkbox("Use seed", value=False)
        st.session_state.seed = seed if seed_toggle else None

        st.markdown("### Pots Setup")

        # --- Source picker ---
        st.session_state.pots_source_key = st.radio(
            "Choose a starting set",
            list(POT_SOURCES.keys()),
            index=list(POT_SOURCES.keys()).index(
                st.session_state.get("pots_source_key", "Ranking Based (default)")
            ),
        )

        # Resolve the actual dict object for the selection
        selected_source_name = POT_SOURCES[st.session_state.pots_source_key]  # "DEFAULT_POTS" or "LATEST_POTS"
        selected_pots_obj = DEFAULT_POTS if selected_source_name == "DEFAULT_POTS" else PO_POT4

        # Button to immediately load the selected source into the app state
        if st.button("📦 Use selected pots"):
            reset_state(selected_pots_obj)
            st.session_state.pots_baseline = deepcopy(selected_pots_obj)
            st.success(f"Loaded {st.session_state.pots_source_key}.")

        # Pre-fill each pot's textarea from the *currently selected* source
        default_pot_texts = {
            1: "\n".join([f"{t['name']}, {t['confederation']}" for t in selected_pots_obj["pot1"]]),
            2: "\n".join([f"{t['name']}, {t['confederation']}" for t in selected_pots_obj["pot2"]]),
            3: "\n".join([f"{t['name']}, {t['confederation']}" for t in selected_pots_obj["pot3"]]),
            4: "\n".join([f"{t['name']}, {t['confederation']}" for t in selected_pots_obj["pot4"]]),
        }

        pot_inputs = {}
        for pot_num in range(1, 5):
            pot_inputs[pot_num] = st.text_area(
                f"Pot {pot_num} teams (one per line: 'Team Name, Confederation')",
                value=default_pot_texts[pot_num],
                height=180,
            )

        if st.button("Reset with these pots"):
            try:
                new_pots = {}
                ok = True
                for pot_num in range(1, 5):
                    pot_label = f"pot{pot_num}"
                    new_pots[pot_label] = parse_pot_string(pot_inputs[pot_num], pot_num)
                    if len(new_pots[pot_label]) != 12:
                        st.error(
                            f"{pot_label} has {len(new_pots[pot_label])}/12 teams. "
                            "Please provide exactly 12."
                        )
                        ok = False

                # Light validation
                if ok:
                    for p_label, teams in new_pots.items():
                        for t in teams:
                            if not {"name", "confederation", "pot"} <= t.keys():
                                st.error(f"Team in {p_label} missing fields.")
                                ok = False
                                break

                if ok:
                    reset_state(new_pots)
                    st.session_state.pots_baseline = deepcopy(new_pots)  # keep baseline in sync
                    st.success("Pots successfully updated.")
            except Exception as e:
                st.error(f"Error parsing pots: {e}")

    # Draw controls
    ui_controls()

    # Live groups table
    render_groups_table(st.session_state.groups)

    # Remaining pots
    render_pots(st.session_state.pots)

    # Log
    with st.expander("Draw log"):
        for line in st.session_state.log:
            st.write(line)


if __name__ == "__main__":
    main()
