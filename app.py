import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="EPL Sleeper League History", layout="wide")
BASE_URL = "https://api.sleeper.app/v1"

@st.cache_data(ttl=3600)
def fetch_league_history(league_ids_input: str):
    """Walks the previous_league_id chain and extracts completed matchups and current rosters."""
    raw_ids = [x.strip() for x in league_ids_input.split(",") if x.strip()]
    visited_ids = set()
    seasons = []
    
    for initial_id in raw_ids:
        curr_id = initial_id
        while curr_id and curr_id not in visited_ids and curr_id != "0" and curr_id.lower() != "none":
            visited_ids.add(curr_id)
            res = requests.get(f"{BASE_URL}/league/{curr_id}")
            if res.status_code != 200:
                break
            l_info = res.json()
            if not l_info or "league_id" not in l_info:
                break
                
            users = requests.get(f"{BASE_URL}/league/{curr_id}/users").json() or []
            rosters = requests.get(f"{BASE_URL}/league/{curr_id}/rosters").json() or []
            
            user_map = {}
            for u in users:
                display = u.get("metadata", {}).get("team_name") or u.get("display_name") or u.get("username")
                user_map[u["user_id"]] = display
                
            roster_map = {}
            for r in rosters:
                rid = r.get("roster_id")
                oid = r.get("owner_id")
                if not oid and r.get("co_owners"):
                    oid = r["co_owners"][0]
                roster_map[rid] = user_map.get(oid, f"Team {rid}")
            
            # Scan Gameweeks 1-38
            matchup_rows = []
            for gw in range(1, 39):
                m_res = requests.get(f"{BASE_URL}/league/{curr_id}/matchups/{gw}")
                if m_res.status_code != 200:
                    continue
                matchups = m_res.json()
                if not matchups:
                    continue
                    
                for t in matchups:
                    m_id = t.get("matchup_id")
                    pts = t.get("points")
                    
                    if m_id is not None:
                        matchup_rows.append({
                            "Season": str(l_info.get("season", "Unknown")),
                            "Gameweek": gw,
                            "Matchup_ID": m_id,
                            "Roster_ID": t.get("roster_id"),
                            "Manager": roster_map.get(t.get("roster_id"), f"Team {t.get('roster_id')}"),
                            "Points": float(pts) if pts is not None else 0.0,
                            "Starters": t.get("starters", [])
                        })
            
            seasons.append({
                "league_id": curr_id,
                "season": str(l_info.get("season", "Unknown")),
                "name": l_info.get("name", "League"),
                "status": l_info.get("status"),
                "previous_id": l_info.get("previous_league_id"),
                "matchups": matchup_rows
            })
            
            curr_id = l_info.get("previous_league_id")
            
    return seasons

# --- UI Setup ---
st.title("⚽ EPL Sleeper League History & Analytics")

league_input = st.text_input(
    "Enter Sleeper League ID (paste multiple separated by commas if past years are unlinked):",
    placeholder="e.g. 104838492019482910"
)

if league_input:
    with st.spinner("Compiling league data from Sleeper..."):
        seasons = fetch_league_history(league_input)
        
    if not seasons:
        st.error("No valid league data found. Please check your League ID.")
    else:
        all_matchups = []
        for s in seasons:
            all_matchups.extend(s["matchups"])
            
        df_matchups = pd.DataFrame(all_matchups)
        
        # Sidebar Details
        st.sidebar.title("Connected Seasons")
        for s in seasons:
            st.sidebar.markdown(f"- **{s['season']}**: {s['name']} (`{s['status']}`)")
            if s["previous_id"]:
                st.sidebar.caption(f"↳ Linked prev ID: `{s['previous_id']}`")
        
        if df_matchups.empty:
            st.warning("No matchup schedules or data found for this league.")
        else:
            # Pair matchups
            merged = pd.merge(df_matchups, df_matchups, on=["Season", "Gameweek", "Matchup_ID"], suffixes=("_A", "_B"))
            df_pairs = merged[merged["Roster_ID_A"] != merged["Roster_ID_B"]].copy()
            
            # Differentiate completed matches vs active/unfinalized matches
            df_completed_pairs = df_pairs[(df_pairs["Points_A"] > 0) | (df_pairs["Points_B"] > 0)].copy()
            df_completed_pairs["Win"] = (df_completed_pairs["Points_A"] > df_completed_pairs["Points_B"]).astype(int)
            df_completed_pairs["Loss"] = (df_completed_pairs["Points_A"] < df_completed_pairs["Points_B"]).astype(int)
            df_completed_pairs["Draw"] = (df_completed_pairs["Points_A"] == df_completed_pairs["Points_B"]).astype(int)
            df_completed_pairs["Margin"] = (df_completed_pairs["Points_A"] - df_completed_pairs["Points_B"]).abs()

            tab_current, tab_standings, tab_h2h, tab_records = st.tabs([
                "📋 Active Gameweek",
                "📊 All-Time Standings", 
                "⚔️ Head-to-Head Matrix", 
                "🏆 Records & Bests"
            ])
            
            # --- TAB 1: ACTIVE / SCHEDULED GAMEWEEK ---
            with tab_current:
                current_season = seasons[0]["season"]
                curr_season_df = df_matchups[df_matchups["Season"] == current_season]
                
                if not curr_season_df.empty:
                    # Find highest active GW
                    active_gw = curr_season_df["Gameweek"].max()
                    st.subheader(f"Gameweek {active_gw} Matchups ({current_season})")
                    st.info("ℹ️ Note: Sleeper updates and finalizes official fantasy points once all Premier League fixtures for the gameweek have completed.")
                    
                    gw_pairs = df_pairs[(df_pairs["Season"] == current_season) & (df_pairs["Gameweek"] == active_gw)]
                    seen = set()
                    
                    for _, row in gw_pairs.iterrows():
                        key = tuple(sorted([row["Manager_A"], row["Manager_B"]]))
                        if key not in seen:
                            seen.add(key)
                            c1, c2, c3 = st.columns([4, 1, 4])
                            c1.markdown(f"### {row['Manager_A']}")
                            c1.caption(f"Starters Active: {len(row['Starters_A'])}")
                            c2.markdown("### VS")
                            c3.markdown(f"### {row['Manager_B']}")
                            c3.caption(f"Starters Active: {len(row['Starters_B'])}")
                            st.divider()
                else:
                    st.info("No current season fixtures found.")

            # --- TAB 2: ALL-TIME STANDINGS ---
            with tab_standings:
                st.subheader("All-Time Performance Summary")
                if not df_completed_pairs.empty:
                    standings = df_completed_pairs.groupby("Manager_A").agg(
                        Matches=("Win", "count"),
                        Wins=("Win", "sum"),
                        Draws=("Draw", "sum"),
                        Losses=("Loss", "sum"),
                        Points_For=("Points_A", "sum"),
                        Points_Against=("Points_B", "sum")
                    ).reset_index()
                    
                    standings["Win_%"] = (standings["Wins"] / standings["Matches"]) * 100
                    standings["PPG"] = standings["Points_For"] / standings["Matches"]
                    standings["Diff"] = standings["Points_For"] - standings["Points_Against"]
                    standings = standings.rename(columns={"Manager_A": "Manager"}).sort_values(by=["Wins", "Points_For"], ascending=[False, False])
                    
                    st.dataframe(standings.style.format({
                        "Win_%": "{:.1f}%",
                        "Points_For": "{:.1f}",
                        "Points_Against": "{:.1f}",
                        "Diff": "{:+.1f}",
                        "PPG": "{:.2f}"
                    }), use_container_width=True)
                else:
                    st.info("All-time standings will begin populating as soon as the first gameweek of fixtures finalizes.")

            # --- TAB 3: H2H MATRIX ---
            with tab_h2h:
                st.subheader("Historical Head-to-Head Records")
                if not df_completed_pairs.empty:
                    managers = sorted(df_matchups["Manager"].unique())
                    c1, c2 = st.columns(2)
                    m1 = c1.selectbox("Select Manager 1:", managers, index=0)
                    m2 = c2.selectbox("Select Manager 2:", managers, index=min(1, len(managers)-1))
                    
                    if m1 != m2:
                        h2h = df_completed_pairs[(df_completed_pairs["Manager_A"] == m1) & (df_completed_pairs["Manager_B"] == m2)]
                        mc1, mc2, mc3 = st.columns(3)
                        mc1.metric(f"{m1} Wins", int(h2h["Win"].sum()))
                        mc2.metric("Draws", int(h2h["Draw"].sum()))
                        mc3.metric(f"{m2} Wins", int(h2h["Loss"].sum()))
                        
                        if not h2h.empty:
                            st.write("##### Past Meetings")
                            st.dataframe(h2h[["Season", "Gameweek", "Points_A", "Points_B"]].rename(
                                columns={"Points_A": f"{m1} Pts", "Points_B": f"{m2} Pts"}
                            ).sort_values(by=["Season", "Gameweek"], ascending=[False, False]), use_container_width=True)
                else:
                    st.info("Historical head-to-head records require finalized gameweek results.")

            # --- TAB 4: RECORDS & BESTS ---
            with tab_records:
                st.subheader("High Scores & Records")
                completed_matchups = df_matchups[df_matchups["Points"] > 0]
                if not completed_matchups.empty:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Top 10 High Scores (Single GW)**")
                        st.dataframe(completed_matchups.sort_values(by="Points", ascending=False).head(10)[["Season", "Gameweek", "Manager", "Points"]].style.format({"Points": "{:.1f}"}), use_container_width=True)
                    with col2:
                        st.write("**Lowest Scores (Single GW)**")
                        st.dataframe(completed_matchups.sort_values(by="Points", ascending=True).head(10)[["Season", "Gameweek", "Manager", "Points"]].style.format({"Points": "{:.1f}"}), use_container_width=True)
                else:
                    st.info("Records will display once weekly scores are calculated and locked.")
