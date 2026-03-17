"""
dashboard.py
~~~~~~~~~~~~
Streamlit dashboard for viewing competitive intelligence briefs.

Run: streamlit run src/dashboard.py --server.port 8501
"""

from __future__ import annotations

import httpx
import streamlit as st

API_BASE = "http://localhost:8010"

st.set_page_config(
    page_title="Competitive Intelligence Dashboard",
    page_icon="🕵️",
    layout="wide",
)

st.title("🕵️ Competitive Intelligence Dashboard")
st.caption("Powered by LangGraph Swarm + FastMCP Browser Agents")

# ── Sidebar: Run New Analysis ───────────────────────────────────────────────────
with st.sidebar:
    st.header("Run Analysis")
    competitors_input = st.text_area(
        "Competitor domains (one per line)",
        value="competitor-a.com\ncompetitor-b.io",
        height=100,
    )
    focus_areas = st.multiselect(
        "Focus areas",
        ["product", "pricing", "hiring", "patents"],
        default=["product", "pricing", "hiring"],
    )

    if st.button("🚀 Run Intelligence Analysis", type="primary"):
        competitors = [c.strip() for c in competitors_input.strip().split("\n") if c.strip()]

        with st.spinner("Swarm agents running..."):
            try:
                response = httpx.post(
                    f"{API_BASE}/run",
                    json={"competitors": competitors, "focus_areas": focus_areas},
                    timeout=300.0,
                )
                if response.status_code == 200:
                    st.session_state["latest_result"] = response.json()
                    st.success("Analysis complete!")
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"Failed to connect to API: {e}")

# ── Main Content ──────────────────────────────────────────────────────────────

# Load past runs
try:
    runs_resp = httpx.get(f"{API_BASE}/results", timeout=5.0)
    past_runs = runs_resp.json().get("runs", []) if runs_resp.status_code == 200 else []
except Exception:
    past_runs = []

# Display latest result
if "latest_result" in st.session_state:
    result = st.session_state["latest_result"]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Competitors Analyzed", len(result.get("competitors", [])))
    with col2:
        st.metric("Agent Messages", result.get("message_count", 0))
    with col3:
        st.metric("Session ID", result.get("session_id", "")[:8] + "...")

    st.divider()

    # Intelligence Brief
    st.subheader("📋 Intelligence Brief")
    brief = result.get("brief", "")
    if brief:
        st.markdown(brief)
    else:
        st.info("No brief generated yet.")

    # Agent Conversation
    with st.expander("🤖 Agent Conversation Trace", expanded=False):
        for msg in result.get("agent_messages", []):
            agent = msg.get("agent", "unknown")
            content = msg.get("content", "")

            agent_colors = {
                "ProductAgent": "🟦",
                "PricingAgent": "🟩",
                "HiringAgent": "🟨",
                "PatentAgent": "🟧",
                "SynthesisAgent": "🟪",
            }
            emoji = agent_colors.get(agent, "⬜")

            with st.chat_message("assistant"):
                st.caption(f"{emoji} **{agent}**")
                st.markdown(content[:500] + ("..." if len(content) > 500 else ""))

elif past_runs:
    st.info("Select a past run from the history below, or run a new analysis.")

    # Past runs table
    st.subheader("📚 Past Intelligence Runs")
    for run in past_runs[:10]:
        with st.expander(f"Session: {run['session_id'][:8]}... — {', '.join(run.get('competitors', []))}"):
            if st.button(f"Load results", key=run["session_id"]):
                try:
                    resp = httpx.get(f"{API_BASE}/results/{run['session_id']}", timeout=10.0)
                    if resp.status_code == 200:
                        st.session_state["latest_result"] = resp.json()
                        st.rerun()
                except Exception as e:
                    st.error(str(e))

else:
    st.info("👆 Enter competitor domains and click **Run Intelligence Analysis** to get started.")
    st.markdown("""
    ### What this does:
    1. **ProductAgent** monitors competitor product pages for changes
    2. **PricingAgent** analyzes pricing tiers and detects enterprise signals
    3. **HiringAgent** scans job postings for strategic hiring patterns
    4. **PatentAgent** searches USPTO for recent patent filings
    5. **SynthesisAgent** connects all signals into an intelligence brief

    Agents hand off to each other autonomously based on what they find.
    """)
