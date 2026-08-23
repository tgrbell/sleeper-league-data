import streamlit as st
import pandas as pd
import numpy as np
import requests

st.set_page_config(page_title="EPL Sleeper League History", layout="wide")
BASE_URL = "https://api.sleeper.app/v1"

@st.cache_data(ttl=1800)
def fetch_complete_league_data(league_ids_input: str):
    raw_ids = [x.strip() for x in league_ids_input.split(",") if x.strip()]
    visited_ids = set()
    seasons = []
    global_user_map = {}
    
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
            drafts = requests.get(f"{BASE_URL}/league/{curr_id}/drafts").json() or []
            
            for u in users:
                uid = u.get("user_id")
                display = u.get("metadata", {}).get("team_name") or u.get("display_name") or u.get("username")
                if uid and uid not in global_user_map:
                    global_user_map[uid] = display
                
            roster_totals = []
            roster_to_uid = {}
            for r in rosters:
                rid = r.get("roster_id")
                oid = r.get("owner_id")
                if not oid and r.get("co_owners"):
                    oid = r["co_owners"][0]
                
                uid = oid if oid else f"unassigned_{rid}"
                roster_to_uid[rid] = uid
                if uid not in global_user_map:
                    global_user_map[uid] = f"Team {rid}"
                
                settings = r.get("settings", {})
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
                    "User_ID": uid,
                    "Wins": wins,
                    "Draws": ties,
                    "Losses": losses,
                    "Total_Matches": wins + ties + losses,
                    "Points_For": pf,
                    "Points_Against": pa
                })
            
            # Matchups
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
                            "User_ID": roster_to_uid.get(t.get("roster_id")),
                            "Points": pts
                        })
            
            # Draft Picks
            draft_picks = []
            if drafts:
                draft_id = drafts[0].get("draft_id")
                p_res = requests.get(f"{BASE_URL}/draft/{draft_id}/picks")
                if p_res.status_code == 200:
                    for p in p_res.json():
                        p_meta = p.get("metadata", {})
                        p_name = f"{p_meta.get('first_name', '')} {p_meta.get('last_name', '')}".strip() or p_meta.get("player_name", "Unknown Player")
                        draft_picks.append({
                            "Season": str(l_info.get("season", "Unknown")),
                            "Round": p.get("round"),
                            "Pick_No": p.get("pick_no"),
                            "User_ID": p.get("picked_by"),
                            "Player": p_name,
                            "Position": p_meta.get("position", "N/A"),
                            "Club": p_meta.get("team", "N/A")
                        })
            
            seasons.append({
                "league_id": curr_id,
                "season": str(l_info.get("season", "Unknown")),
                "name": l_info.get("name", "League"),
                "status": l_info.get("status"),
                "previous_id": l_info.get("previous_league_id"),
                "roster_totals": roster_totals,
                "matchups": matchup_rows,
                "draft_picks": draft_picks
            })
            
            curr_id = l_info.get("previous_league_id")
            
    return seasons, global_user_map

# --- UI Setup ---
st.title("⚽ EPL Sleeper League History & Analytics")

league_input = st.text_input(
    "Enter Sleeper League ID (or comma-separated IDs):",
    placeholder="e.g. 104838492019482910, 958291039481029381"
)

if league_input:
    with st.spinner("Fetching full league history & draft records..."):
        seasons, user_map = fetch_complete_league_data(league_input)
        
    if not seasons:
        st.error("No league data found.")
    else:
        all_totals, all_matchups, all_drafts = [], [], []
        for s in seasons:
            all_totals.extend(s["roster_totals"])
            all_matchups.extend(s["matchups"])
            all_drafts.extend(s["draft_picks"])
            
        df_totals = pd.DataFrame(all_totals) if all_totals else pd.DataFrame(columns=["Season", "League_ID", "User_ID", "Wins", "Draws", "Losses", "Total_Matches", "Points_For", "Points_Against"])
        df_matchups = pd.DataFrame(all_matchups) if all_matchups else pd.DataFrame(columns=["Season", "Gameweek", "Matchup_ID", "Roster_ID", "User_ID", "Points"])
        df_drafts = pd.DataFrame(all_drafts) if all_drafts else pd.DataFrame(columns=["Season", "Round", "Pick_No", "User_ID", "Player", "Position", "Club"])
        
        if not df_totals.empty:
            df_totals["Manager"] = df_totals["User_ID"].map(user_map).fillna("Unknown")
        if not df_matchups.empty:
            df_matchups["Manager"] = df_matchups["User_ID"].map(user_map).fillna("Unknown")
        if not df_drafts.empty:
            df_drafts["Manager"] = df_drafts["User_ID"].map(user_map).fillna("Unknown")

        # Global Season Selector
        season_options = ["All Time"] + sorted(list({s["season"] for s in seasons}), reverse=True)
        selected_season_scope = st.selectbox("Season Scope:", season_options)
        
        # Scope filtering
        if selected_season_scope != "All Time":
            df_totals_scoped = df_totals[df_totals["Season"] == selected_season_scope]
            df_matchups_scoped = df_matchups[df_matchups["Season"] == selected_season_scope]
            df_drafts_scoped = df_drafts[df_drafts["Season"] == selected_season_scope]
        else:
            df_totals_scoped = df_totals
            df_matchups_scoped = df_matchups
            df_drafts_scoped = df_drafts

        # Build H2H pairs if matchups exist
        df_pairs = pd.DataFrame()
        if not df_matchups_scoped.empty and "Matchup_ID" in df_matchups_scoped.columns:
            merged = pd.merge(df_matchups_scoped, df_matchups_scoped, on=["Season", "Gameweek", "Matchup_ID"], suffixes=("_A", "_B"))
            df_pairs = merged[merged["Roster_ID_A"] != merged["Roster_ID_B"]].copy()
            df_pairs = df_pairs[(df_pairs["Points_A"] > 0) | (df_pairs["Points_B"] > 0)]
            if not df_pairs.empty:
                df_pairs["Win"] = (df_pairs["Points_A"] > df_pairs["Points_B"]).astype(int)
                df_pairs["Loss"] = (df_pairs["Points_A"] < df_pairs["Points_B"]).astype(int)
                df_pairs["Draw"] = (df_pairs["Points_A"] == df_pairs["Points_B"]).astype(int)
                df_pairs["Margin"] = (df_pairs["Points_A"] - df_pairs["Points_B"]).abs()

        # Navigation Tabs (Joscho Analytics Schema)
        t_draft, t_lead, t_hof, t_riv, t_rep, t_luck = st.tabs([
            "🧠 Draft & Roster Insights",
            "🏆 All-Time Leaderboard",
            "🎖️ Hall of Fame",
            "⚔️ Rivalries",
            "📜 Report Cards",
            "📊 Consistency & Luck"
        ])
        
        # --- TAB 1: DRAFT & ROSTER INSIGHTS ---
        with t_draft:
            st.subheader("Draft Insights")
            if not df_drafts_scoped.empty:
                draft_view = st.radio("View:", ["Draft Board", "Picks by Manager", "Position Tendencies"], horizontal=True)
                
                if draft_view == "Draft Board":
                    st.dataframe(df_drafts_scoped[["Season", "Round", "Pick_No", "Manager", "Player", "Position", "Club"]], use_container_width=True)
                elif draft_view == "Picks by Manager":
                    d_mgr = st.selectbox("Select Manager:", sorted(df_drafts_scoped["Manager"].unique()))
                    st.dataframe(df_drafts_scoped[df_drafts_scoped["Manager"] == d_mgr][["Season", "Round", "Pick_No", "Player", "Position", "Club"]], use_container_width=True)
                elif draft_view == "Position Tendencies":
                    tendency = df_drafts_scoped.groupby(["Manager", "Position"]).size().unstack(fill_value=0)
                    st.dataframe(tendency, use_container_width=True)
            else:
                st.info("No draft data found for this selection.")

        # --- TAB 2: LEADERBOARD ---
        with t_lead:
            st.subheader(f"Leaderboard ({selected_season_scope})")
            if not df_totals_scoped.empty and (df_totals_scoped["Total_Matches"] > 0).any():
                played = df_totals_scoped[df_totals_scoped["Total_Matches"] > 0]
                lead = played.groupby("User_ID").agg(
                    Manager=("Manager", "first"),
                    Seasons=("Season", "nunique"),
                    GP=("Total_Matches", "sum"),
                    W=("Wins", "sum"),
                    D=("Draws", "sum"),
                    L=("Losses", "sum"),
                    PF=("Points_For", "sum"),
                    PA=("Points_Against", "sum")
                ).reset_index()
                lead["Win_%"] = (lead["W"] / lead["GP"]) * 100
                lead["PPG"] = lead["PF"] / lead["GP"]
                lead["Diff"] = lead["PF"] - lead["PA"]
                lead = lead.sort_values(by=["W", "PF"], ascending=[False, False])
                
                st.dataframe(lead[["Manager", "Seasons", "GP", "W", "D", "L", "PF", "PA", "Diff", "Win_%", "PPG"]].style.format({
                    "Win_%": "{:.1f}%",
                    "PF": "{:.1f}",
                    "PA": "{:.1f}",
                    "Diff": "{:+.1f}",
                    "PPG": "{:.2f}"
                }), use_container_width=True)
            else:
                st.info("No finished league records found.")

        # --- TAB 3: HALL OF FAME ---
        with t_hof:
            st.subheader("Hall of Fame & League Records")
            valid_m = df_matchups_scoped[df_matchups_scoped["Points"] > 0]
            if not valid_m.empty:
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Highest Single GW Scores**")
                    st.dataframe(valid_m.sort_values(by="Points", ascending=False).head(10)[["Season", "Gameweek", "Manager", "Points"]].style.format({"Points": "{:.1f}"}), use_container_width=True)
                    
                    if not df_pairs.empty:
                        st.write("**Biggest Blowouts**")
                        st.dataframe(df_pairs[df_pairs["Win"] == 1].sort_values(by="Margin", ascending=False).head(5)[["Season", "Gameweek", "Manager_A", "Points_A", "Manager_B", "Points_B", "Margin"]].style.format({
                            "Points_A": "{:.1f}", "Points_B": "{:.1f}", "Margin": "{:.1f}"
                        }), use_container_width=True)
                with c2:
                    st.write("**Lowest Single GW Scores**")
                    st.dataframe(valid_m.sort_values(by="Points", ascending=True).head(10)[["Season", "Gameweek", "Manager", "Points"]].style.format({"Points": "{:.1f}"}), use_container_width=True)
                    
                    if not df_pairs.empty:
                        st.write("**Closest Matches**")
                        st.dataframe(df_pairs.sort_values(by="Margin", ascending=True).head(5)[["Season", "Gameweek", "Manager_A", "Points_A", "Manager_B", "Points_B", "Margin"]].style.format({
                            "Points_A": "{:.1f}", "Points_B": "{:.1f}", "Margin": "{:.1f}"
                        }), use_container_width=True)
            else:
                st.info("Matchup records will populate once weekly fixtures conclude.")

        # --- TAB 4: RIVALRIES ---
        with t_riv:
            st.subheader("Head-to-Head Rivalries")
            if not df_pairs.empty:
                mgrs = sorted(df_matchups_scoped["Manager"].unique())
                rc1, rc2 = st.columns(2)
                rm1 = rc1.selectbox("Manager 1:", mgrs, index=0)
                rm2 = rc2.selectbox("Manager 2:", mgrs, index=min(1, len(mgrs)-1))
                
                if rm1 != rm2:
                    h2h = df_pairs[(df_pairs["Manager_A"] == rm1) & (df_pairs["Manager_B"] == rm2)]
                    m1_w = int(h2h["Win"].sum())
                    m2_w = int(h2h["Loss"].sum())
                    dr = int(h2h["Draw"].sum())
                    
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric(f"{rm1} Wins", m1_w)
                    mc2.metric("Draws", dr)
                    mc3.metric(f"{rm2} Wins", m2_w)
                    
                    st.write("##### Matchup History")
                    st.dataframe(h2h[["Season", "Gameweek", "Points_A", "Points_B"]].rename(
                        columns={"Points_A": f"{rm1} Pts", "Points_B": f"{rm2} Pts"}
                    ).sort_values(by=["Season", "Gameweek"], ascending=[False, False]), use_container_width=True)
            else:
                st.info("Head-to-head records require completed gameweek fixtures.")

        # --- TAB 5: REPORT CARDS ---
        with t_rep:
            st.subheader("Manager Report Cards")
            if not df_totals_scoped.empty and (df_totals_scoped["Total_Matches"] > 0).any():
                played = df_totals_scoped[df_totals_scoped["Total_Matches"] > 0]
                rep = played.groupby("Manager").agg(
                    Total_Wins=("Wins", "sum"),
                    Total_Matches=("Total_Matches", "sum"),
                    Total_PF=("Points_For", "sum"),
                    PPG=("Points_For", lambda x: x.sum() / played.loc[x.index, "Total_Matches"].sum())
                ).reset_index()
                
                # Assign simple grade based on Win % & PPG percentile
                rep["Win_%"] = (rep["Total_Wins"] / rep["Total_Matches"]) * 100
                rep["Grade"] = pd.qcut(rep["Win_%"], q=min(4, len(rep)), labels=["C", "B", "A", "A+"] if len(rep) >= 4 else ["B", "A", "A+"][:len(rep)])
                st.dataframe(rep[["Manager", "Total_Matches", "Win_%", "PPG", "Grade"]].style.format({
                    "Win_%": "{:.1f}%",
                    "PPG": "{:.2f}"
                }), use_container_width=True)
            else:
                st.info("Report cards require completed season matches.")

        # --- TAB 6: CONSISTENCY & LUCK ---
        with t_luck:
            st.subheader("Consistency & Luck Index")
            valid_m = df_matchups_scoped[df_matchups_scoped["Points"] > 0]
            if not valid_m.empty and len(valid_m["Gameweek"].unique()) > 1:
                # All-Play / Expected Wins calculation
                all_play_records = []
                for (s, gw), group in valid_m.groupby(["Season", "Gameweek"]):
                    scores = group["Points"].values
                    for _, row in group.iterrows():
                        wins_against_all = (row["Points"] > scores).sum()
                        losses_against_all = (row["Points"] < scores).sum()
                        ties_against_all = (row["Points"] == scores).sum() - 1
                        all_play_records.append({
                            "User_ID": row["User_ID"],
                            "Season": s,
                            "Gameweek": gw,
                            "Expected_Wins": wins_against_all + (0.5 * ties_against_all),
                            "Expected_Games": len(scores) - 1
                        })
                        
                df_exp = pd.DataFrame(all_play_records)
                luck_summary = df_exp.groupby("User_ID").agg(
                    Exp_Wins=("Expected_Wins", "sum"),
                    Exp_Games=("Expected_Games", "sum")
                ).reset_index()
                luck_summary["All_Play_Win_%"] = (luck_summary["Exp_Wins"] / luck_summary["Exp_Games"]) * 100
                luck_summary["Manager"] = luck_summary["User_ID"].map(user_map)
                
                # Consistency (Standard Deviation of Points)
                std_df = valid_m.groupby("User_ID")["Points"].agg(Score_StdDev="std", Avg_Score="mean").reset_index()
                
                luck_table = pd.merge(luck_summary, std_df, on="User_ID")
                st.dataframe(luck_table[["Manager", "Avg_Score", "Score_StdDev", "All_Play_Win_%"]].sort_values(by="All_Play_Win_%", ascending=False).style.format({
                    "Avg_Score": "{:.2f}",
                    "Score_StdDev": "{:.2f}",
                    "All_Play_Win_%": "{:.1f}%"
                }), use_container_width=True)
            else:
                st.info("Luck & consistency metrics will calculate once multiple gameweeks are finalized.")
