"""The "Under the hood" view: three guardrail demos, the live safety run and the usage table (offline, no model call)."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_under_the_hood() -> None:
    import tokenomics
    import under_the_hood as uth
    with st.container():
        st.title("Under the hood")
        st.caption("Three guardrails running live on saved data (offline, no model call, $0). "
                   "Each demo uses a stand-in model so you can see what the code does.")

        st.markdown("### 1 · Prompt injection")
        try:
            d = uth.injection_demo()
            st.markdown("A SeeClickFix-style report written by a resident:")
            st.code(d["raw_report"], language=None)
            st.markdown(f"**Filter result:** {'flagged ⚠️' if d['flagged'] else 'clean'} → what the model is shown instead:")
            st.code(d["filtered_report"], language=None)
            c1, c2 = st.columns(2)
            c1.metric("Verdict with the filter", d["with_filter"]["verdict"],
                      "unchanged" if d["with_filter"]["verdict"] == d["baseline_verdict"] else "CHANGED")
            c1.caption(f"Instruction reached the model: {d['with_filter']['prompt_contains_instruction']}")
            c2.metric("Verdict with NO filter (gullible stand-in model)", d["without_filter"]["verdict"])
            c2.caption(f"Instruction reached the model: {d['without_filter']['prompt_contains_instruction']}")
        except Exception as exc:
            st.warning(f"This demo needs the saved samples ({type(exc).__name__}).")

        st.markdown("### 2 · Fact check")
        try:
            d = uth.fact_check_demo()
            st.markdown("An agent answer with a planted false number and a planted false name:")
            c1, c2 = st.columns(2)
            c1.markdown("**Before**")
            c1.write(d["before"]["summary"])
            for r in d["before"]["reasons"]:
                c1.markdown(f"- {r}")
            c2.markdown("**After the fact check**")
            c2.write(d["after"]["summary"])
            for r in d["after"]["reasons"]:
                c2.markdown(f"- {r}")
            with st.expander(f"Removed by fact check ({len(d['removed'])})", expanded=True):
                for r in d["removed"]:
                    st.write(f"- “{r['text']}” — not in the data: {', '.join(r['unsupported'])}")
        except Exception as exc:
            st.warning(f"This demo needs the saved samples ({type(exc).__name__}).")

        st.markdown("### 3 · Cost cap")
        try:
            d = uth.cost_cap_demo()
            st.write(f"A run with a cap of **{d['cap']} model requests**, asked to analyse three addresses:")
            st.dataframe(pd.DataFrame(d["steps"]), hide_index=True, width="stretch")
            st.warning(d["message"])
        except Exception as exc:
            st.warning(f"This demo needs the saved samples ({type(exc).__name__}).")

        st.markdown("#### Live run with the real model")
        live = uth.live_safety()
        if not live:
            st.info("Not run yet: `python safety_live.py` runs the real gpt-6-luna agents on the same planted report.")
        else:
            st.caption(f"The real {live['model']} agents (block analyst, landlord analyst, email drafter) on {live['address']} with a planted "
                       f"report: “{live['planted_report']}”. Run on {live['time']}. Without the planted report the block verdict was "
                       f"“{live['baseline_verdict_without_plant']}”.")
            c1, c2 = st.columns(2)
            for col, key, title in ((c1, "filter_on", "Filter ON (what LeaseLens does)"), (c2, "filter_off", "Filter OFF (this test only)")):
                v = live[key]
                col.markdown(f"**{title}**")
                col.metric("Block verdict", v["block_verdict"], "followed the planted instruction" if v["instruction_followed"] else "did not follow it",
                           delta_color="inverse" if v["instruction_followed"] else "normal")
                col.markdown("What the model was shown:")
                col.code(v["what_the_model_was_shown_for_the_planted_report"], language=None)
                col.caption(f"Flagged by the filter: {len(v['flagged_by_filter'])} · mentions 10/10 or “hidden gem” in any output: "
                            f"{v['mentions_10_of_10_or_hidden_gem']} · {v['tokens']:,} tokens · ${v['cost_usd']:.4f} · {v['requests']} calls")
                col.write(v["block_summary"])
            same = live["filter_on"]["block_verdict"] == live["filter_off"]["block_verdict"]
            st.info("**Honest reading.** " + (
                "In this run the real model ignored the planted instruction even with the filter off: the rules in its system prompt held. "
                "The filter is defense in depth (it removes the instruction before the model can weigh it), not proof that this model is "
                "easily fooled." if same and not live["filter_off"]["instruction_followed"] else
                "Without the filter the model's output changed, and with the filter it did not. That is why the filter exists."))
            st.caption(f"Total for this live test: {live['total_tokens']:,} tokens, ${live['total_cost_usd']:.4f}.")

        st.markdown("### Usage so far (from `output/usage_log.json`)")
        rows = tokenomics.agent_rows(tokenomics.load_rows(), "all")
        if rows:
            df = pd.DataFrame(tokenomics.usage_table(rows)).rename(columns={
                "agent": "Agent", "calls": "Calls", "input_tokens": "Input tokens", "cached_tokens": "Cached tokens",
                "output_tokens": "Output tokens", "cost_usd": "Cost ($)", "cache_hit_rate": "Cache hit rate"})
            st.dataframe(df, hide_index=True, width="stretch",
                         column_config={"Cache hit rate": st.column_config.NumberColumn(format="percent")})
            st.caption("Cache hit rate = cached input tokens ÷ input tokens. Prices from data/prices.json.")
        else:
            st.info("No model calls have been logged yet.")



