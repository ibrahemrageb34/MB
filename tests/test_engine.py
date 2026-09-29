import datetime as dt
import os
import unittest

os.environ.setdefault("MBOS_TODAY", "2026-09-29")

from mbos.__main__ import load_cfg  # noqa: E402
from mbos.connectors import demo  # noqa: E402
from mbos.engine import metrics as M, prepaid, search_terms, testing  # noqa: E402
from mbos.pipeline import analyze_account, portfolio  # noqa: E402
from mbos.util import load_json, parse_tags, ROOT  # noqa: E402

CFG = load_cfg()
ACCOUNTS = load_json(ROOT / "config/accounts.example.json")


def bundle(i):
    return demo.build(ACCOUNTS[i], i)


class Metrics(unittest.TestCase):
    def test_derive(self):
        m = M.derive({**M.empty(), "spend": 1000, "impressions": 50000, "clicks": 500, "purchases": 10, "revenue": 5000})
        self.assertEqual(m["cpr"], 100)
        self.assertAlmostEqual(m["ctr"], 0.01)
        self.assertEqual(m["cpm"], 20)
        self.assertEqual(m["roas"], 5)

    def test_zero_division_safe(self):
        m = M.derive(M.empty(), "lead")
        self.assertIsNone(m["cpr"])

    def test_parse_tags(self):
        t = parse_tags("F:UGC | A:Pain | H:Question | T:T12 | v2")
        self.assertEqual(t, {"format": "UGC", "angle": "Pain", "hook": "Question", "test": "T12"})
        self.assertEqual(parse_tags("random name"), {})


class Prepaid(unittest.TestCase):
    def test_scenarios(self):
        debt = prepaid.analyze(bundle(3), CFG)
        self.assertEqual(debt["status"], "debt")
        self.assertGreater(debt["topup_recommended"], 0)
        crit = prepaid.analyze(bundle(4), CFG)
        self.assertEqual(crit["status"], "critical")
        self.assertTrue(crit["topup_now"])

    def test_spend_cap_never_below_spent(self):
        for i in range(7):
            b = bundle(i)
            w = prepaid.analyze(b, CFG)
            self.assertGreaterEqual(w["spend_cap_recommended"], b["info"]["amount_spent"])


class Scenarios(unittest.TestCase):
    """Each demo scenario must be caught by the module responsible for it."""

    @classmethod
    def setUpClass(cls):
        cls.r = [analyze_account(bundle(i), CFG) for i in range(7)]

    def test_fatigue_detected(self):
        self.assertTrue(self.r[1]["fatigue"])

    def test_cpm_spike(self):
        self.assertTrue(any(a["metric"] == "cpm" and a["level"] == "account" for a in self.r[2]["anomalies"]))

    def test_tracking_break_is_p0_for_tracking(self):
        acts = [a for a in self.r[5]["actions"] if a["priority"] == "P0" and a["owner_role"] == "tracking"]
        self.assertTrue(acts)

    def test_policy(self):
        titles = " ".join(i["title"] for i in self.r[6]["qa"])
        self.assertIn("DISAPPROVED", titles)
        self.assertIn("Learning Limited", titles)

    def test_no_scaling_when_wallet_low(self):
        for i in (3, 4):
            self.assertFalse(any(b["action"] == "scale" for b in self.r[i]["budget"]))

    def test_debt_forces_critical_health(self):
        self.assertEqual(self.r[3]["health"]["status"], "critical")

    def test_post_triage_routes(self):
        verdicts = {p["verdict"] for r in self.r for p in r["posts"]}
        self.assertTrue({"promote", "skip", "wait"} <= verdicts)

    def test_portfolio(self):
        p = portfolio(self.r, CFG)
        self.assertEqual(len(p["treasury"]["rows"]), 7)
        self.assertEqual(p["treasury"]["rows"][0]["status"], "debt")


class Testing(unittest.TestCase):
    def test_verdicts(self):
        r = CFG["testing"]
        self.assertEqual(testing._verdict({"spend": 500, "results": 6, "cpr": 80}, 100, r), "winner")
        self.assertEqual(testing._verdict({"spend": 250, "results": 0, "cpr": None}, 100, r), "loser")
        self.assertEqual(testing._verdict({"spend": 120, "results": 1, "cpr": 120}, 100, r), "learning")


class SearchTerms(unittest.TestCase):
    def test_negatives(self):
        rows = [{"search_term": "free course", "clicks": 40, "cost": 400, "conversions": 0},
                {"search_term": "buy course online", "clicks": 30, "cost": 200, "conversions": 4}]
        out = search_terms.analyze(rows, target_cpa=100)
        self.assertEqual(out["negative_candidates"][0]["term"], "free course")
        self.assertEqual(out["exact_match_candidates"][0]["term"], "buy course online")


if __name__ == "__main__":
    unittest.main()
