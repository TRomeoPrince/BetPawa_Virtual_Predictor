from .private_rules import RULES
from .rules_engine import evaluate_league, grade_pick
from .predictor import build_prediction


def fixture(pos, home, away, ht=(1,0), ft=(2,1)):
    return {"position":pos,"home":home,"away":away,"ht_home":ht[0],"ht_away":ht[1],"ft_home":ft[0],"ft_away":ft[1]}


def run():
    # Spanish trigger: source 0-0 HT, 1-3 FT -> follow loser H1 into target.
    src = [fixture(i, f"H{i}", f"A{i}") for i in range(1,11)]
    src[0] = fixture(1,"H1","A1",(0,0),(1,3))
    tgt = [fixture(i, f"T{i}", f"Z{i}") for i in range(1,11)]
    tgt[2] = fixture(3,"H1","Z3",(1,0),(2,2))
    picks = evaluate_league(RULES["Spanish"], src, tgt)
    assert len(picks) == 1 and picks[0]["selected_team"] == "H1"
    assert grade_pick(picks[0], tgt) is True

    context = {
        "season":"test", "latest_completed_matchday":9, "next_matchday":10,
        "alignment_scope":"test", "use_previous_for_alignment":False,
        "latest_source":{k:[] for k in RULES}, "next_target":{k:[] for k in RULES},
        "current_pairs_by_league":{k:[] for k in RULES},
        "previous_pairs_by_league":{k:[] for k in RULES},
    }
    context["latest_source"]["Spanish"] = src
    context["next_target"]["Spanish"] = tgt
    context["current_pairs_by_league"]["Spanish"] = [(src,tgt)] * 5
    out = build_prediction(context)
    assert any(p["league"] == "Spanish" for p in out["predictions"])
    assert all("rule_id" not in p for p in out["predictions"])
    print("self-test passed")


if __name__ == "__main__":
    run()
