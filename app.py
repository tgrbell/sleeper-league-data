import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="EPL Sleeper League History", layout="wide")
BASE_URL = "https://api.sleeper.app/v1"

@st.cache_data(ttl=1800)
def fetch_full_league_data(league_ids_input: str):
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
            
            # Map user names
            user_map = {}
            for u in users:
                display = u.get("metadata", {}).get("team_name") or u.get("display_name") or u.get("username")
                user_map[u["user_id"]] = display
                
            roster_totals = []
            roster_map = {}
            for r in rosters:
                rid = r.get("roster_id")
                oid = r.get("owner_id")
                if not oid and r.get("co_owners"):
                    oid = r["co_owners"][0]
                m_name = user_map.get(oid, f"Team {rid}")
                roster_map[rid] = m_name
                
                settings = r.get("settings", {})
                # Fetch lifetime season totals directly from roster
                fpts = settings.get("fpts", 0)
                fpts_dec = settings.get("fpts_decimal", 0)
                pf = float(f"{fpts}.{fpts_dec}") if fpts_dec else float(fpts)
                
                fpts_a = settings.get("fpts_against", 0)
                fpts_a_dec = settings.get("fpts_against_decimal", 0)
                pa = float(f"{fpts_a}.{fpts_a_dec}") if fpts_a_dec else float(fpts_a)
                
                wins = settings.get("wins", 0)
                ties = settings.get("ties", 0)
                losses = settings.get("losses", 0)
                
                roster_totals.append({
                    "Season": str(l_info.get("season", "Unknown")),
                    "League_ID": curr_id,
                    "Manager": m_name,
                    "Wins": wins,
                    "Draws": ties,
                    "Losses": losses,
                    "Total_Matches": wins + ties + losses,
                    "Points_For": pf,
                    "Points_Against": pa
                })
            
            # Weekly Matchups (for detailed records)
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
                    if pts is None or pts == 0:
                        if t.get("starters_points"):
                            pts = sum(t["starters_points"])
                    pts = float(pts) if pts is not None else 0.0
                    
                    if m_id is not None:
                        matchup_rows.append({
                            "Season": str(l_info.get("season", "Unknown")),
                            "Gameweek": gw,
                            "Matchup_ID": m_id,
                            "Roster_ID": t.get("roster_id"),
                            "Manager": roster_map.get(t.get("roster_id"), f"Team {t.get('roster_id')}"),
                            "Points": pts
                        })
            
            seasons.append({
                "league_id": curr_id,
                "season": str(l_info.get("season", "Unknown")),
                "name": l_info.get("name", "League"),
                "status": l_info.get("status"),
                "previous_id": l_info.get("previous_league_id"),
                "roster_totals": roster_totals,
                "matchups": matchup_rows
            })
            
            curr_id = l_info.get("previous_league_id")
            
    return seasons

st.title("⚽ EPL Sleeper League History & All-Time Table")

league_input = st.text_input(
    "Enter Sleeper League ID (or comma-separated IDs):",
    placeholder="e.g. 104838492019482910, 958291039481029381"
)

if league_input:
    with st.spinner("Fetching full league archives..."):
        seasons = fetch_full_league_data(league_input)
        
    if not seasons:
        st.error("No league found with that ID.")
    else:
        # Collect data
        all_totals = []
        all_matchups = []
        for s in seasons:
            all_totals.extend(s["roster_totals"])
            all_matchups.extend(s["matchups"])
            
        df_totals = pd.DataFrame(all_totals)
        df_matchups = pd.DataFrame(all_matchups)
        
        # Sidebar
        st.sidebar.title("Archives Found")
        for s in seasons:
            st.sidebar.markdown(f"**{s['season']}**: {s['name']} (`{s['status']}`)")
            
        tab_standings, tab_seasons, tab_matchups = st.tabs([
            "📊 All-Time Career Standings", 
            "📅 Past Season Archives", 
            "⚔️ Matchup Records"
        ])
        
        # --- TAB 1: ALL-TIME STANDINGS (PULLS FROM HISTORICAL ROSTER TOTALS) ---
        with tab_standings:
            st.subheader("All-Time Career Standings")
            # Only include seasons where games were played
            played_totals = df_totals[df_totals["Total_Matches"] > 0]
            
            if not played_totals.empty:
                career = played_totals.groupby("Manager").agg(
                    Seasons=("Season", "nunique"),
                    Matches=("Total_Matches", "sum"),
                    Wins=("Wins", "sum"),
                    Draws=("Draws", "sum"),
                    Losses=("Losses", "sum"),
                    Points_For=("Points_For", "sum"),
                    Points_Against=("Points_Against", "sum")
                ).reset_index()
                
                career["Win_%"] = (career["Wins"] / career["Matches"]) * 100
                career["PPG"] = career["Points_For"] / career["Matches"]
                career["Diff"] = career["Points_For"] - career["Points_Against"]
                career = career.sort_values(by=["Wins", "Points_For"], ascending=[False, False])
                
                st.dataframe(career.style.format({
                    "Win_%": "{:.1f}%",
                    "Points_For": "{:.1f}",
                    "Points_Against": "{:.1f}",
                    "Diff": "{:+.1f}",
                    "PPG": "{:.2f}"
                }), use_container_width=True)
            else:
                st.info("No completed historical seasons detected yet across the linked IDs.")
                
        # --- TAB 2: PAST SEASON TABLES ---
        with tab_seasons:
            st.subheader("Final Tables by Season")
            if not df_totals.empty:
                season_list = sorted(df_totals["Season"].unique(), reverse=True)
                selected_season = st.selectbox("Select Season:", season_list)
                
                s_df = df_totals[df_totals["Season"] == selected_season].copy()
                s_df["Win_%"] = (s_df["Wins"] / s_df["Total_Matches"].replace(0, 1)) * 100
                s_df["Diff"] = s_df["Points_For"] - s_df["Points_Against"]
                
                st.dataframe(s_df[["Manager", "Total_Matches", "Wins", "Draws", "Losses", "Points_For", "Points_Against", "Diff", "Win_%"]].sort_values(
                    by=["Wins", "Points_For"], ascending=[False, False]
                ).style.format({
                    "Win_%": "{:.1f}%",
                    "Points_For": "{:.1f}",
                    "Points_Against": "{:.1f}",
                    "Diff": "{:+.1f}"
                }), use_container_width=True)

        # --- TAB 3: MATCHUP RECORDS ---
        with tab_matchups:
            st.subheader("Weekly High Scores & Margins")
            active_m = df_matchups[df_matchups["Points"] > 0]
            if not active_m.empty:
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Top Gameweek Scores**")
                    st.dataframe(active_m.sort_values(by="Points", ascending=False).head(10)[["Season", "Gameweek", "Manager", "Points"]].style.format({"Points": "{:.1f}"}), use_container_width=True)
                with c2:
                    st.write("**Lowest Active Gameweek Scores**")
                    st.dataframe(active_m.sort_values(by="Points", ascending=True).head(10)[["Season", "Gameweek", "Manager", "Points"]].style.format({"Points": "{:.1f}"}), use_container_width=True)
            else:
                st.info("Individual weekly fixture histories will unlock on Tuesday once Gameweek 1 scores are locked.")
