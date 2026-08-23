import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="EPL Sleeper League History", layout="wide")

BASE_URL = "https://api.sleeper.app/v1"

@st.cache_data(ttl=3600)
def fetch_league_history(current_league_id: str):
    """Recursively walks backwards via previous_league_id to gather all seasons & matchups."""
    seasons_meta = []
    league_id = str(current_league_id).strip()
    
    # 1. Traverse all linked seasons
    while league_id and league_id != "None" and league_id != "0":
        l_res = requests.get(f"{BASE_URL}/league/{league_id}")
        if l_res.status_code != 200:
            break
        league_json = l_res.json()
        if not league_json or "league_id" not in league_json:
            break
            
        u_res = requests.get(f"{BASE_URL}/league/{league_id}/users")
        r_res = requests.get(f"{BASE_URL}/league/{league_id}/rosters")
        
        users = u_res.json() if u_res.status_code == 200 else []
        rosters = r_res.json() if r_res.status_code == 200 else []
        
        user_map = {}
        for u in users:
            name = u.get("metadata", {}).get("team_name") or u.get("display_name") or u.get("username")
            user_map[u["user_id"]] = name

        roster_to_manager = {}
        for r in rosters:
            r_id = r.get("roster_id")
            owner_id = r.get("owner_id")
            if not owner_id and r.get("co_owners"):
                owner_id = r["co_owners"][0]
            roster_to_manager[r_id] = user_map.get(owner_id, f"Team {r_id}")

        seasons_meta.append({
            "season": str(league_json.get("season", "Unknown")),
            "league_id": league_id,
            "name": league_json.get("name", "League"),
            "roster_map": roster_to_manager
        })
        
        league_id = league_json.get("previous_league_id")

    # 2. Extract Matchup Details for all seasons (GW 1 to 38)
    matchup_rows = []
    for s in seasons_meta:
        s_id = s["league_id"]
        s_year = s["season"]
        r_map = s["roster_map"]
        
        for gw in range(1, 39):
            m_res = requests.get(f"{BASE_URL}/league/{s_id}/matchups/{gw}")
            if m_res.status_code != 200:
                continue
            matchups = m_res.json()
            if not matchups:
                continue

            for t in matchups:
                m_id = t.get("matchup_id")
                pts = t.get("points")
                if pts is None:
                    pts = sum(t.get("starters_points", [])) if t.get("starters_points") else 0.0
                
                # Keep records that were actually scheduled into a matchup
                if m_id is not None:
                    matchup_rows.append({
                        "Season": s_year,
                        "Gameweek": gw,
                        "Matchup_ID": m_id,
                        "Roster_ID": t.get("roster_id"),
                        "Manager": r_map.get(t.get("roster_id"), f"Team {t.get('roster_id')}"),
                        "Points": float(pts)
                    })

    return seasons_meta, pd.DataFrame(matchup_rows)


def build_h2h_results(df_matchups):
    """Pairs opponents within the same Season, GW, and Matchup_ID to compute W/D/L records."""
    if df_matchups.empty:
        return pd.DataFrame()
    
    # Self-join to pair Team A with Team B
    merged = pd.merge(
        df_matchups, 
        df_matchups, 
        on=["Season", "Gameweek", "Matchup_ID"], 
        suffixes=("_A", "_B")
    )
    pairs = merged[merged["Roster_ID_A"] != merged["Roster_ID_B"]].copy()
    
    # Filter out empty unplayed games (both 0 points)
    pairs = pairs[(pairs["Points_A"] > 0) | (pairs["Points_B"] > 0)]
    
    pairs["Win"] = (pairs["Points_A"] > pairs["Points_B"]).astype(int)
    pairs["Loss"] = (pairs["Points_A"] < pairs["Points_B"]).astype(int)
    pairs["Draw"] = (pairs["Points_A"] == pairs["Points_B"]).astype(int)
    pairs["Margin"] = (pairs["Points_A"] - pairs["Points_B"]).abs()
    
    return pairs

# --- UI Setup ---
st.title("⚽ EPL Sleeper League History & All-Time Analytics")

league_id_input = st.text_input("Enter your Sleeper League ID (Current or Past Season):", placeholder="e.g. 104838492019482910")

if league_id_input:
    with st.spinner("Compiling multi-season history from Sleeper..."):
        seasons, df_matchups = fetch_league_history(league_id_input.strip())
        
    if not seasons:
        st.error("League ID not found. Ensure the ID is typed correctly.")
    else:
        st.sidebar.title("League Summary")
        st.sidebar.write(f"**Name:** {seasons[0]['name']}")
        st.sidebar.write(f"**Seasons Found:** {', '.join([s['season'] for s in seasons])}")
        
        if df_matchups.empty:
            st.warning("Found the league structure, but no completed matchups with scores were found across linked seasons.")
        else:
            df_pairs = build_h2h_results(df_matchups)
            
            tab_standings, tab_h2h, tab_records, tab_seasons = st.tabs([
                "📊 All-Time Standings", 
                "⚔️ Head-to-Head Matrix", 
                "🏆 Records & Hall of Fame",
                "📅 Season Breakdown"
            ])
            
            # --- TAB 1: ALL-TIME STANDINGS ---
            with tab_standings:
                st.subheader("All-Time League Table")
                if not df_pairs.empty:
                    standings = df_pairs.groupby("Manager_A").agg(
                        Matches=("Win", "count"),
                        Wins=("Win", "sum"),
                        Draws=("Draw", "sum"),
                        Losses=("Loss", "sum"),
                        Points_For=("Points_A", "sum"),
                        Points_Against=("Points_B", "sum"),
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
                    st.info("No paired head-to-head match results found.")

            # --- TAB 2: H2H MATRIX ---
            with tab_h2h:
                st.subheader("Head-to-Head Rivalry Breakdown")
                managers = sorted(df_matchups["Manager"].unique())
                col_m1, col_m2 = st.columns(2)
                m1 = col_m1.selectbox("Select Manager 1:", managers, index=0)
                m2 = col_m2.selectbox("Select Manager 2:", managers, index=min(1, len(managers)-1))
                
                if m1 and m2:
                    if m1 == m2:
                        st.info("Please select two different managers.")
                    else:
                        h2h = df_pairs[(df_pairs["Manager_A"] == m1) & (df_pairs["Manager_B"] == m2)]
                        m1_wins = h2h["Win"].sum()
                        m2_wins = h2h["Loss"].sum()
                        draws = h2h["Draw"].sum()
                        
                        m_col1, m_col2, m_col3 = st.columns(3)
                        m_col1.metric(f"{m1} Wins", int(m1_wins))
                        m_col2.metric("Draws", int(draws))
                        m_col3.metric(f"{m2} Wins", int(m2_wins))
                        
                        if not h2h.empty:
                            st.write("##### Match Log")
                            st.dataframe(h2h[["Season", "Gameweek", "Points_A", "Points_B"]].rename(
                                columns={"Points_A": f"{m1} Pts", "Points_B": f"{m2} Pts"}
                            ).sort_values(by=["Season", "Gameweek"], ascending=[False, False]), use_container_width=True)

            # --- TAB 3: RECORDS & HALL OF FAME ---
            with tab_records:
                st.subheader("League Records & Extremes")
                r_col1, r_col2 = st.columns(2)
                
                with r_col1:
                    st.write("**Top 10 Highest Single Gameweek Scores**")
                    top_gw = df_matchups.sort_values(by="Points", ascending=False).head(10)
                    st.dataframe(top_gw[["Season", "Gameweek", "Manager", "Points"]].style.format({"Points": "{:.1f}"}), use_container_width=True)
                    
                    if not df_pairs.empty:
                        st.write("**Largest Blowouts (Margin of Victory)**")
                        blowouts = df_pairs[df_pairs["Win"] == 1].sort_values(by="Margin", ascending=False).head(5)
                        st.dataframe(blowouts[["Season", "Gameweek", "Manager_A", "Points_A", "Manager_B", "Points_B", "Margin"]].rename(
                            columns={"Manager_A": "Winner", "Points_A": "Winner Pts", "Manager_B": "Loser", "Points_B": "Loser Pts"}
                        ).style.format({"Winner Pts": "{:.1f}", "Loser Pts": "{:.1f}", "Margin": "{:.1f}"}), use_container_width=True)

                with r_col2:
                    st.write("**Top 10 Lowest Gameweek Scores (Active)**")
                    low_gw = df_matchups[df_matchups["Points"] > 0].sort_values(by="Points", ascending=True).head(10)
                    st.dataframe(low_gw[["Season", "Gameweek", "Manager", "Points"]].style.format({"Points": "{:.1f}"}), use_container_width=True)
                    
                    if not df_pairs.empty:
                        st.write("**Narrowest Matches**")
                        closest = df_pairs[(df_pairs["Win"] == 1) | (df_pairs["Draw"] == 1)].sort_values(by="Margin", ascending=True).head(5)
                        st.dataframe(closest[["Season", "Gameweek", "Manager_A", "Points_A", "Manager_B", "Points_B", "Margin"]].rename(
                            columns={"Manager_A": "Team A", "Points_A": "Pts A", "Manager_B": "Team B", "Points_B": "Pts B"}
                        ).style.format({"Pts A": "{:.1f}", "Pts B": "{:.1f}", "Margin": "{:.1f}"}), use_container_width=True)

            # --- TAB 4: SEASON BREAKDOWN ---
            with tab_seasons:
                available_seasons = sorted(df_matchups["Season"].unique(), reverse=True)
                selected_s = st.selectbox("Select Season:", available_seasons)
                
                s_df = df_pairs[df_pairs["Season"] == selected_s]
                if not s_df.empty:
                    s_table = s_df.groupby("Manager_A").agg(
                        GP=("Win", "count"),
                        W=("Win", "sum"),
                        D=("Draw", "sum"),
                        L=("Loss", "sum"),
                        PF=("Points_A", "sum"),
                        PA=("Points_B", "sum")
                    ).reset_index()
                    s_table["Win_%"] = (s_table["W"] / s_table["GP"]) * 100
                    s_table = s_table.rename(columns={"Manager_A": "Manager"}).sort_values(by=["W", "PF"], ascending=[False, False])
                    
                    st.dataframe(s_table.style.format({
                        "Win_%": "{:.1f}%",
                        "PF": "{:.1f}",
                        "PA": "{:.1f}"
                    }), use_container_width=True)
