import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="EPL Sleeper League History", layout="wide")

BASE_URL = "https://api.sleeper.app/v1"

@st.cache_data(ttl=3600)
def fetch_league_chain(initial_league_id: str):
    """Walks backwards through previous_league_id to gather all historical seasons."""
    seasons = []
    league_id = str(initial_league_id).strip()
    
    while league_id and league_id != "None":
        url = f"{BASE_URL}/league/{league_id}"
        res = requests.get(url)
        if res.status_code != 200:
            break
        league_json = res.json()
        if not league_json or "league_id" not in league_json:
            break
            
        users_res = requests.get(f"{BASE_URL}/league/{league_id}/users")
        rosters_res = requests.get(f"{BASE_URL}/league/{league_id}/rosters")
        
        users = users_res.json() if users_res.status_code == 200 else []
        rosters = rosters_res.json() if rosters_res.status_code == 200 else []
        
        user_map = {}
        for u in users:
            name = u.get("metadata", {}).get("team_name") or u.get("display_name") or u.get("username")
            user_map[u["user_id"]] = name

        seasons.append({
            "season": league_json.get("season", "Unknown"),
            "league_id": league_id,
            "name": league_json.get("name", "League"),
            "users": user_map,
            "rosters": rosters,
            "total_rosters": len(rosters)
        })
        
        league_id = league_json.get("previous_league_id")
        
    return seasons

@st.cache_data(ttl=3600)
def get_matchup_history(seasons):
    """Compiles all weekly matchup scores across seasons."""
    records = []
    for s in seasons:
        season_year = s["season"]
        league_id = s["league_id"]
        
        roster_to_user = {}
        for r in s["rosters"]:
            r_id = r.get("roster_id")
            owner_id = r.get("owner_id")
            if not owner_id and r.get("co_owners"):
                owner_id = r["co_owners"][0]
            
            manager_name = s["users"].get(owner_id, f"Team {r_id}")
            roster_to_user[r_id] = manager_name
        
        # Pull gameweeks 1 through 38
        for gw in range(1, 39):
            m_res = requests.get(f"{BASE_URL}/league/{league_id}/matchups/{gw}")
            if m_res.status_code != 200:
                continue
            
            matchups = m_res.json()
            if not matchups:
                continue

            for team in matchups:
                points = team.get("points")
                # Include any matchup entry where points exist
                if points is not None and points >= 0:
                    records.append({
                        "Season": str(season_year),
                        "Gameweek": gw,
                        "Roster ID": team.get("roster_id"),
                        "Manager": roster_to_user.get(team.get("roster_id"), f"Team {team.get('roster_id')}"),
                        "Matchup ID": team.get("matchup_id"),
                        "Points": float(points)
                    })
    return pd.DataFrame(records)

# --- UI ---
st.title("⚽ EPL Sleeper League History & Analytics")

league_id_input = st.text_input("Enter your Sleeper League ID:", placeholder="e.g. 104838492019482910")

if league_id_input:
    with st.spinner("Fetching data from Sleeper API..."):
        seasons_data = fetch_league_chain(league_id_input)
        
    if not seasons_data:
        st.error(f"Could not find any league data for ID: `{league_id_input}`. Check that the ID is valid.")
    else:
        st.success(f"Connected to **{seasons_data[0]['name']}** ({len(seasons_data)} season(s) found: {', '.join([s['season'] for s in seasons_data])})")
        
        df_matchups = get_matchup_history(seasons_data)
        
        if df_matchups.empty:
            st.warning("Found league info, but no played matchup points were recorded yet for any gameweek.")
        else:
            tab_standings, tab_records, tab_h2h = st.tabs(["All-Time Standings", "Records & Bests", "Raw Data"])
            
            with tab_standings:
                st.subheader("All-Time Performance Summary")
                summary = df_matchups[df_matchups["Points"] > 0].groupby("Manager").agg(
                    Total_Points=("Points", "sum"),
                    Avg_Points_Per_GW=("Points", "mean"),
                    Matches_Played=("Points", "count"),
                    High_Score=("Points", "max"),
                    Low_Score=("Points", "min")
                ).sort_values(by="Total_Points", ascending=False).reset_index()
                
                st.dataframe(summary.style.format({
                    "Total_Points": "{:.1f}",
                    "Avg_Points_Per_GW": "{:.2f}",
                    "High_Score": "{:.1f}",
                    "Low_Score": "{:.1f}"
                }), use_container_width=True)
                    
            with tab_records:
                st.subheader("High Scores & Records")
                col1, col2 = st.columns(2)
                valid_scores = df_matchups[df_matchups["Points"] > 0]
                
                if not valid_scores.empty:
                    top_scores = valid_scores.sort_values(by="Points", ascending=False).head(5)
                    lowest_scores = valid_scores.sort_values(by="Points", ascending=True).head(5)
                    
                    with col1:
                        st.write("**Top 5 Single Gameweek Scores**")
                        st.table(top_scores[["Season", "Gameweek", "Manager", "Points"]])
                    with col2:
                        st.write("**Lowest 5 Single Gameweek Scores**")
                        st.table(lowest_scores[["Season", "Gameweek", "Manager", "Points"]])

            with tab_h2h:
                st.subheader("Raw Matchup History")
                st.dataframe(df_matchups, use_container_width=True)
