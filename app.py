import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="EPL Sleeper League History", layout="wide")

BASE_URL = "https://api.sleeper.app/v1"

@st.cache_data(ttl=3600)
def fetch_league_chain(current_league_id: str):
    """Recursively walks backwards through previous_league_id to gather all seasons."""
    seasons = []
    league_id = current_league_id
    
    while league_id:
        url = f"{BASE_URL}/league/{league_id}"
        res = requests.get(url)
        if res.status_code != 200:
            break
        data = res.json()
        if not data:
            break
            
        users = requests.get(f"{BASE_URL}/league/{league_id}/users").json()
        rosters = requests.get(f"{BASE_URL}/league/{league_id}/rosters").json()
        
        user_map = {u["user_id"]: u.get("display_name", "Unknown") for u in users}
        
        seasons.append({
            "season": data.get("season"),
            "league_id": league_id,
            "name": data.get("name"),
            "users": user_map,
            "rosters": rosters
        })
        
        league_id = data.get("previous_league_id")
        
    return seasons

@st.cache_data(ttl=3600)
def get_matchup_history(seasons):
    """Compiles all weekly matchup scores across seasons."""
    records = []
    for s in seasons:
        season_year = s["season"]
        league_id = s["league_id"]
        roster_to_user = {
            r["roster_id"]: s["users"].get(r["owner_id"], f"Manager_{r['roster_id']}") 
            for r in s["rosters"] if r.get("owner_id")
        }
        
        # EPL seasons have up to 38 gameweeks
        for gw in range(1, 39):
            m_res = requests.get(f"{BASE_URL}/league/{league_id}/matchups/{gw}")
            if m_res.status_code != 200 or not m_res.json():
                continue
            
            matchups = m_res.json()
            for team in matchups:
                points = team.get("points")
                if points is not None and points > 0:
                    records.append({
                        "Season": season_year,
                        "Gameweek": gw,
                        "Roster ID": team["roster_id"],
                        "Manager": roster_to_user.get(team["roster_id"], "Unknown"),
                        "Matchup ID": team.get("matchup_id"),
                        "Points": points
                    })
    return pd.DataFrame(records)

# --- UI Layout ---
st.title("⚽ EPL Sleeper League History & Analytics")

league_id_input = st.text_input("Enter your Sleeper League ID:", placeholder="e.g. 104838492019482910")

if league_id_input:
    with st.spinner("Fetching historical league data from Sleeper API..."):
        seasons_data = fetch_league_chain(league_id_input)
        
    if not seasons_data:
        st.error("Could not find data for this League ID. Check the ID and ensure the league is public.")
    else:
        st.success(f"Loaded {len(seasons_data)} season(s) of league history!")
        
        df_matchups = get_matchup_history(seasons_data)
        
        tab_standings, tab_records, tab_h2h = st.tabs(["All-Time Standings", "Records & Bests", "Raw Data"])
        
        with tab_standings:
            st.subheader("All-Time Performance Summary")
            if not df_matchups.empty:
                summary = df_matchups.groupby("Manager").agg(
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
            else:
                st.info("No completed matchup points found.")
                
        with tab_records:
            st.subheader("High Scores & Records")
            if not df_matchups.empty:
                col1, col2 = st.columns(2)
                top_scores = df_matchups.sort_values(by="Points", ascending=False).head(5)
                lowest_scores = df_matchups[df_matchups["Points"] > 0].sort_values(by="Points", ascending=True).head(5)
                
                with col1:
                    st.write("**Top 5 Single Gameweek Scores**")
                    st.table(top_scores[["Season", "Gameweek", "Manager", "Points"]])
                with col2:
                    st.write("**Lowest 5 Single Gameweek Scores**")
                    st.table(lowest_scores[["Season", "Gameweek", "Manager", "Points"]])

        with tab_raw := tab_h2h:
            st.dataframe(df_matchups, use_container_width=True)
